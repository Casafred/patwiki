"""HimmPat MCP adapter.

HimmPat exposes several MCP services.  This module maps those service/tool
contracts into PatWiki's provider-neutral patent connector contract; the
generic MCP protocol implementation remains in ``mcp_transport``.
"""
from __future__ import annotations

from datetime import date, datetime, timezone
import hashlib
import json
import re
from typing import Any, Mapping
from urllib.parse import urlparse

from app.integrations.contracts import (
    CanonicalPatentQuery,
    ConnectorCapabilities,
    ConnectorError,
    ConnectorHealth,
    PatentConnector,
    ProviderIdentifier,
    ProviderLegalEvent,
    ProviderPatentRecord,
    SearchPage,
)
from app.integrations.mcp_transport import McpTransport, redact_payload


DEFAULT_SERVICES = {
    "discovery": "product_patent_discovery",
    "dossier": "product_patent_dossier",
    "legal": "product_legal_ownership_risk",
    "monitoring": "product_patent_monitoring",
}

READ_ONLY_TOOLS = {
    "discovery": {
        "query_patent_ids_by_query_expression_with_info", "search_similar_patents_by_public_number_with_info",
        "new_search_similar_patents_by_text_with_info", "get_filter_results_by_query_expression",
        "search_patent_by_patent_numbers", "search_patent_by_image", "retrieval_element_extraction",
        "ai_word_extend", "get_ipc_default", "ai_ipc_words_match", "build_query",
        "generate_query_expressions_from_technical_solution", "get_classification_info", "get_extended_info_from_keyword",
    },
    "dossier": {
        "get_patent_publication_by_patent_ids", "get_patent_record_fields_by_patent_ids",
        "get_patent_family_by_patent_id", "get_patent_citations_by_patent_id", "get_patent_citation_data_by_patent_id",
        "get_abstract_and_figures_by_patent_ids", "get_claims_by_patent_id", "get_description_by_patent_id",
        "get_figures_by_patent_ids", "get_pdf_by_patent_ids", "get_patent_ai_tech_info",
    },
    "legal": {"get_patent_legal_status_by_patent_ids", "get_legal_details_by_patent_id",
              "get_reexamination_by_patent_id", "get_invalidation_by_patent_id", "invention_patent_stability"},
    "monitoring": {"get_litigation_by_plaintiff_or_defendant", "monitor_latest_hit_patents", "monitor_latest_legal_state",
                   "monitor_latest_reassignment", "monitor_latest_license", "monitor_latest_pledge",
                   "monitor_latest_preservation", "monitor_latest_reexamination", "monitor_latest_invalid", "monitor_expiring_soon"},
}
DOSSIER_UPDATE_FIELDS = {
    "publication_number", "application_number", "title", "abstract", "applicant", "assignee", "inventor",
    "agent", "filing_date", "publication_date", "country", "ipc_all", "priority_number", "priority_date",
    "claims", "description_full", "technical_problem", "technical_solution", "technical_effect",
}


def _text_field(value: Any, keys: tuple[str, ...]) -> str | None:
    if isinstance(value, str):
        return value.strip() or None
    if isinstance(value, Mapping):
        for key in keys:
            if key in value:
                text = _text_field(value[key], keys)
                if text:
                    return text
    if isinstance(value, list):
        parts = [_text_field(item, keys) for item in value]
        return "\n\n".join(part for part in parts if part) or None
    return None


def _path(value: Any, path: str | None, default: Any = None) -> Any:
    if not path:
        return default
    current = value
    for token in [item for item in re.split(r"\.|\[|\]", str(path)) if item]:
        if isinstance(current, Mapping):
            if token not in current:
                return default
            current = current[token]
        elif isinstance(current, list) and token.isdigit() and int(token) < len(current):
            current = current[int(token)]
        else:
            return default
    return current


def _date(value: Any) -> date | None:
    if value in (None, ""):
        return None
    text = str(value).strip()
    if len(text) == 8 and text.isdigit():
        text = f"{text[:4]}-{text[4:6]}-{text[6:]}"
    try:
        return date.fromisoformat(text[:10])
    except ValueError:
        return None


def _string(value: Any) -> str | None:
    if value in (None, ""):
        return None
    return str(value)


def _people(value: Any, keys: tuple[str, ...]) -> str | None:
    if isinstance(value, str):
        return value
    if not isinstance(value, list):
        return None
    names = []
    for item in value:
        if isinstance(item, str):
            names.append(item)
            continue
        if isinstance(item, Mapping):
            name = next((item.get(key) for key in keys if item.get(key)), None)
            if name:
                names.append(str(name))
    return "、".join(dict.fromkeys(names)) or None


def _jurisdiction(number: str | None, fallback: str | None = None) -> str | None:
    if fallback:
        return str(fallback).upper()
    match = re.match(r"^([A-Za-z]{2,3})", number or "")
    return match.group(1).upper() if match else None


def _status(state: Any, stc: Any) -> str:
    state_value = str(state or "").upper()
    stc_value = str(stc or "").upper()
    if state_value == "N" or stc_value in {"CE", "EL", "EF", "WA", "RV", "NI", "PCT-NE"}:
        return "expired"
    if stc_value in {"GR", "AR", "IN"} or state_value == "I":
        return "granted"
    if stc_value in {"RJ"}:
        return "rejected"
    if stc_value in {"WD", "AB", "AT"}:
        return "abandoned"
    if stc_value in {"SE"}:
        return "examining"
    if state_value in {"P", "PCT-I"} or stc_value in {"PB", "PCT-IN"}:
        return "pending"
    return "unknown"


class HimmPatMcpAdapter(PatentConnector):
    """Read-only HimmPat MCP adapter used by the shared sync pipeline."""

    def __init__(self, config: dict[str, Any] | None = None, *, endpoint: str | None = None, credential_ref: str | None = None, transport: McpTransport | None = None):
        self.config = config or {}
        base_url = endpoint or self.config.get("endpoint") or "https://himmpat.com"
        services = dict(DEFAULT_SERVICES)
        explicit_services = self.config.get("services") or {}
        services.update(explicit_services)
        self.services = services
        # Older settings saved a complete dossier endpoint. A refresh invokes
        # several services, so derive the MCP host and retain the service path.
        parsed = urlparse(str(base_url))
        is_service_endpoint = "/api/service/" in parsed.path.lower() and "/mcp/" in parsed.path.lower()
        transport_endpoint = f"{parsed.scheme}://{parsed.netloc}" if is_service_endpoint else str(base_url)
        self.transport = transport or McpTransport(
            transport_endpoint,
            credential_ref=credential_ref or self.config.get("credential_ref"),
            credential_value=(self.config.get("credential_value") or (self.config.get("auth") or {}).get("credential_value")),
            service_path_template=str(self.config.get("service_path_template", "/api/service/himmuc_api/mcp/{service_name}")),
            protocol_version=str(self.config.get("protocol_version", "2025-06-18")),
            timeout_seconds=float(self.config.get("timeout_seconds", 30)),
            retry_config=dict(self.config.get("retry") or {}),
        )

    def close(self) -> None:
        self.transport.close()

    def capabilities(self) -> ConnectorCapabilities:
        return ConnectorCapabilities(
            search=True,
            fetch_patent=True,
            legal_events=bool(self.config.get("enrich_legal_status", False)),
            cursor_pagination=True,
            updated_since=False,
            webhooks=False,
        )

    def healthcheck(self) -> ConnectorHealth:
        services = self._configured_services("health_services", [self.services["discovery"]])
        discovered = self.transport.discover(services)
        return ConnectorHealth(status="ok", message=f"HimmPat MCP 已连接，发现 {sum(item['tool_count'] for item in discovered['services'])} 个工具")

    def discover_tools(self) -> dict[str, Any]:
        services = self._configured_services("discovery_services", list(dict.fromkeys(self.services.values())))
        return self.transport.discover(services)

    def search(self, query: CanonicalPatentQuery, cursor: str | None, limit: int) -> SearchPage:
        expression = (query.expression or query.extra.get("query_expression") or "").strip()
        if not expression and query.applicant:
            expression = f"{query.applicant}/pa"
        if not expression:
            raise ConnectorError("HimmPat 检索需要 expression 或 applicant", error_code="missing_query")
        page_number = max(1, int(cursor or 1))
        size = max(1, min(100, int(limit)))
        arguments: dict[str, Any] = {
            "queryExpression": expression,
            "size": size,
            "page": page_number,
        }
        if query.jurisdiction:
            arguments["authority"] = [query.jurisdiction.upper()]
        for key in ("mergeBy", "sort", "order", "authority"):
            if key in query.extra and query.extra[key] not in (None, ""):
                arguments[key] = query.extra[key]
        data, envelope = self._call("discovery", "query_patent_ids_by_query_expression_with_info", arguments)
        patents = data.get("patents", []) if isinstance(data, Mapping) else []
        if not isinstance(patents, list):
            raise ConnectorError("HimmPat 检索结果不是数组", error_code="invalid_response_shape")
        records = [self._summary_record(item) for item in patents if isinstance(item, Mapping) and item.get("id")]
        include_legal = bool(self.config.get("enrich_legal_status", False) or query.extra.get("include_legal"))
        if include_legal and records:
            records = self._enrich_legal(records)
        total = int(data.get("total", 0) or 0) if isinstance(data, Mapping) else 0
        next_cursor = str(page_number + 1) if records and (total <= 0 or page_number * size < total) else None
        return SearchPage(
            records=tuple(records),
            next_cursor=next_cursor,
            watermark=datetime.now(timezone.utc).replace(tzinfo=None),
            source_version="himmpat-mcp",
        )

    def fetch_patent(self, identifier: ProviderIdentifier) -> ProviderPatentRecord:
        return self.fetch_patent_fields(identifier, set(self.config.get("enrich_dossier_fields") or []))

    def fetch_patent_fields(self, identifier: ProviderIdentifier, requested_fields: set[str]) -> ProviderPatentRecord:
        matching_method = "AP" if identifier.identifier_type.casefold() in {"application", "ap"} else "PN"
        data, _ = self._call("discovery", "search_patent_by_patent_numbers", {
            "matchingMethod": [matching_method],
            "patentList": [identifier.raw_value],
        })
        ids = data.get(identifier.raw_value) if isinstance(data, Mapping) else None
        if not ids and isinstance(data, Mapping):
            ids = next(iter(data.values()), None)
        if not isinstance(ids, list) or not ids:
            raise ConnectorError("HimmPat 未找到对应专利", error_code="patent_not_found")
        patent_id = str(ids[0])
        dossier_data, dossier_envelope = self._call("dossier", "get_patent_publication_by_patent_ids", {"ids": [patent_id]})
        item = dossier_data.get(patent_id) if isinstance(dossier_data, Mapping) else None
        if not isinstance(item, Mapping):
            raise ConnectorError("HimmPat 著录项响应无效", error_code="invalid_response_shape")
        record = self._dossier_record(patent_id, item, dossier_envelope)
        # Only selected fields trigger the larger, potentially billable tools.
        extra = set(requested_fields)
        if extra:
            record = self._enrich_dossier(record, patent_id, extra)
        if self.config.get("enrich_legal_on_fetch", False) or self.config.get("enrich_legal_status", False) or extra.intersection({"legal_status", "grant_date"}):
            record = self._enrich_legal([record])[0]
        return record

    def _call(self, service_key: str, tool_name: str, arguments: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
        return self._call_by_service_name(self.services[service_key], tool_name, arguments)

    def _summary_record(self, item: Mapping[str, Any]) -> ProviderPatentRecord:
        patent_id = str(item["id"])
        publication = _string(item.get("pn"))
        application = _string(item.get("ap"))
        jurisdiction = _jurisdiction(publication, item.get("pnc"))
        identifiers = self._identifiers(publication, application, jurisdiction)
        fields = {
            key: value for key, value in {
                "publication_number": publication,
                "application_number": application,
                "title": _string(item.get("ti")),
                "abstract": _string(item.get("ab")),
                "applicant": _people(item.get("as"), ("pa", "as")),
                "filing_date": _date(item.get("apd")),
                "publication_date": _date(item.get("pd")),
                "country": jurisdiction,
            }.items() if value is not None
        }
        return ProviderPatentRecord(
            external_record_id=patent_id,
            identifiers=tuple(identifiers),
            fields=fields,
            source_version="himmpat-mcp",
            raw_payload=dict(redact_payload(item)),
        )

    def _dossier_record(self, patent_id: str, item: Mapping[str, Any], envelope: Mapping[str, Any]) -> ProviderPatentRecord:
        app_ref = item.get("applicationReferenceModel") or {}
        pub_ref = item.get("publicationReferenceModel") or {}
        title = item.get("inventionTitleModel") or {}
        abstract = item.get("abstractModel") or {}
        parties = item.get("partiesModel") or {}
        publication = _string(pub_ref.get("pn"))
        application = _string(app_ref.get("ap"))
        jurisdiction = _jurisdiction(publication, pub_ref.get("pnc") or app_ref.get("apc"))
        fields = {
            key: value for key, value in {
                "publication_number": publication,
                "application_number": application,
                "title": _string(title.get("tio") or title.get("tic") or title.get("tie")),
                "abstract": _string(abstract.get("abc") or abstract.get("abe") or abstract.get("abo")),
                "applicant": _people(parties.get("applicant"), ("pa", "as")),
                "assignee": _people(parties.get("assignee"), ("as", "pa")),
                "inventor": _people(parties.get("inventor"), ("in",)),
                "filing_date": _date(app_ref.get("apd")),
                "publication_date": _date(pub_ref.get("pd") or pub_ref.get("pdf")),
                "country": jurisdiction,
                "ipc_all": item.get("classificationModel", {}).get("ic") if isinstance(item.get("classificationModel"), Mapping) else None,
                "priority_number": _string(_path(item, "priorityReferenceModel.ap")) or _string(_path(item, "priorityModel.ap")),
                "priority_date": _date(_path(item, "priorityReferenceModel.apd")) or _date(_path(item, "priorityModel.apd")),
                "agent": _people(parties.get("agent") or parties.get("representative"), ("ag", "pa", "as")),
            }.items() if value is not None
        }
        return ProviderPatentRecord(
            external_record_id=patent_id,
            identifiers=tuple(self._identifiers(publication, application, jurisdiction)),
            fields=fields,
            source_version="himmpat-mcp",
            raw_payload=dict(redact_payload(envelope)),
        )

    def _enrich_dossier(self, record: ProviderPatentRecord, patent_id: str, fields: set[str]) -> ProviderPatentRecord:
        """Fetch optional dossier resources and keep their raw evidence."""
        calls = {
            "claims": ("get_claims_by_patent_id", {"id": patent_id}),
            "description_full": ("get_description_by_patent_id", {"id": patent_id}),
            "technical": ("get_patent_ai_tech_info", {"ids": [patent_id]}),
            "family_members": ("get_patent_family_by_patent_id", {"id": patent_id}),
            "cited_patents": ("get_patent_citations_by_patent_id", {"id": patent_id}),
        }
        values = dict(record.fields)
        evidence = dict(record.raw_payload)
        if fields.intersection({"agent", "priority_number", "priority_date"}):
            data, envelope = self._call("dossier", "get_patent_record_fields_by_patent_ids", {"ids": [patent_id]})
            detail = data.get(patent_id)
            evidence["get_patent_record_fields_by_patent_ids"] = envelope
            if isinstance(detail, Mapping):
                values.update(self._dossier_record(patent_id, detail, envelope).fields)
        if fields.intersection({"technical_problem", "technical_solution", "technical_effect"}):
            fields = fields | {"technical"}
        for field in sorted(fields):
            spec = calls.get(field)
            if not spec:
                continue
            tool, args = spec
            if "id" in args:
                args = self._single_patent_arguments(tool, patent_id)
            data, envelope = self._call("dossier", tool, args)
            evidence[tool] = envelope
            value: Any = data.get(patent_id, data.get("items", data)) if isinstance(data, Mapping) else data
            if field == "technical" and isinstance(value, Mapping):
                aliases = {
                    "technical_problem": ("technical_problem", "technicalProblem", "problem"),
                    "technical_solution": ("technical_solution", "technicalSolution", "technicalMeans", "solution"),
                    "technical_effect": ("technical_effect", "technicalEffect", "effect"),
                }
                for key, keys in aliases.items():
                    text = _text_field(value, keys)
                    if text:
                        values[key] = text
            elif field in {"claims", "description_full"}:
                keys = ("claims", "claim", "claimsText", "clc", "clo", "cle", "text", "content", "value") if field == "claims" else ("description", "description_full", "descriptionText", "dec", "deo", "dee", "text", "content", "value")
                text = _text_field(value, keys)
                if text:
                    values[field] = text
                elif value not in (None, "", [], {}):
                    raise ConnectorError(f"{tool} 返回的全文结构无法识别", error_code="unsupported_provider_shape")
            # Family/citation structures remain in evidence until reviewed;
            # opaque provider objects must not become local patent identities.
        return ProviderPatentRecord(record.external_record_id, record.identifiers, values, record.legal_events, record.source_updated_at, record.source_version, evidence)

    def _single_patent_arguments(self, tool_name: str, patent_id: str) -> dict[str, Any]:
        catalog = getattr(self, "_dossier_catalog", None)
        if catalog is None:
            catalog = self.transport.discover([self.services["dossier"]])
            self._dossier_catalog = catalog
        for service in catalog.get("services", []):
            for tool in service.get("tools", []):
                if tool.get("name") != tool_name:
                    continue
                props = (tool.get("inputSchema") or {}).get("properties") or {}
                for key in ("patentId", "patent_id", "id", "ids"):
                    if key in props:
                        return {key: [patent_id] if props[key].get("type") == "array" else patent_id}
        raise ConnectorError("工具目录缺少专利 ID 参数定义，请重新发现工具", error_code="missing_tool_schema")

    def call_discovered_tool(self, service_name: str, tool_name: str, arguments: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
        """Execute a discovered read-only tool through the same safe decoder."""
        service_key = next((key for key, name in self.services.items() if name == service_name), None)
        if not service_key:
            raise ConnectorError("未知 MCP 服务", error_code="unknown_service")
        if tool_name not in READ_ONLY_TOOLS[service_key]:
            raise ConnectorError("工具未在只读调用白名单中", error_code="unsupported_tool")
        return self._call_by_service_name(service_name, tool_name, arguments)

    def _call_by_service_name(self, service_name: str, tool_name: str, arguments: dict[str, Any]):
        raw = self.transport.call_tool(service_name, tool_name, arguments)
        if isinstance(raw, Mapping) and raw.get("isError"):
            raise ConnectorError("MCP 工具执行失败", error_code="mcp_tool_error")
        result = raw.get("structuredContent") if isinstance(raw, Mapping) else raw
        if not isinstance(result, Mapping):
            result = raw
        blocks = result.get("content", []) if isinstance(result, Mapping) else []
        text_value = next((item.get("text") for item in blocks if isinstance(item, Mapping) and item.get("type") == "text"), None)
        try:
            envelope = json.loads(text_value) if isinstance(text_value, str) else result
        except (TypeError, json.JSONDecodeError) as exc:
            raise ConnectorError("HimmPat MCP 业务结果不是有效 JSON", error_code="invalid_provider_json") from exc
        if not isinstance(envelope, Mapping):
            raise ConnectorError("HimmPat MCP 业务结果结构无效", error_code="invalid_provider_payload")
        if "data" not in envelope:
            raise ConnectorError("HimmPat MCP 业务结果缺少 data", error_code="invalid_provider_payload")
        code = int(envelope.get("code", 200) or 200)
        if code != 200:
            raise ConnectorError("HimmPat 业务请求未成功", error_code="provider_business_error", retryable=False, status_code=code)
        data = envelope.get("data", {})
        if isinstance(data, list):
            data = {"items": data}
        if not isinstance(data, Mapping):
            data = {"value": data}
        return dict(data), dict(redact_payload(envelope))

    def _identifiers(self, publication: str | None, application: str | None, jurisdiction: str | None) -> list[ProviderIdentifier]:
        identifiers = []
        if publication:
            identifiers.append(ProviderIdentifier("publication", publication, jurisdiction_code=jurisdiction))
        if application:
            identifiers.append(ProviderIdentifier("application", application, jurisdiction_code=_jurisdiction(application, jurisdiction)))
        return identifiers

    def _enrich_legal(self, records: list[ProviderPatentRecord]) -> list[ProviderPatentRecord]:
        ids = [record.external_record_id for record in records]
        data, envelope = self._call("legal", "get_patent_legal_status_by_patent_ids", {"ids": ids})
        enriched = []
        for record in records:
            state = data.get(record.external_record_id) if isinstance(data, Mapping) else None
            if not isinstance(state, Mapping):
                enriched.append(record)
                continue
            status = _status(state.get("state"), state.get("stc"))
            event_date = _date(state.get("grd")) or next((item.event_date for item in record.legal_events), None)
            events = list(record.legal_events)
            if event_date:
                stable = hashlib.sha256(json.dumps({"id": record.external_record_id, "state": state}, sort_keys=True, ensure_ascii=False, default=str).encode("utf-8")).hexdigest()[:40]
                events.append(ProviderLegalEvent(
                    provider_event_id=f"himmpat:{stable}",
                    event_code=str(state.get("stc") or state.get("state") or "UNKNOWN"),
                    event_date=event_date,
                    status=status,
                    jurisdiction_code=record.fields.get("country"),
                    raw_description=f"HimmPat legal state: {state.get('state') or '-'} / {state.get('stc') or '-'}",
                    payload=dict(redact_payload(state)),
                ))
            fields = dict(record.fields)
            if state.get("grd"):
                fields["grant_date"] = _date(state.get("grd"))
            fields["legal_status"] = status
            fields["legal_status_details"] = json.dumps(redact_payload(state), ensure_ascii=False, sort_keys=True)
            enriched.append(ProviderPatentRecord(
                external_record_id=record.external_record_id,
                identifiers=record.identifiers,
                fields=fields,
                legal_events=tuple(events),
                source_updated_at=record.source_updated_at,
                source_version=record.source_version,
                raw_payload={**record.raw_payload, "legal_status": dict(redact_payload(envelope))},
            ))
        return enriched

    def _configured_services(self, key: str, default: list[str]) -> list[str]:
        configured = self.config.get(key)
        if isinstance(configured, list) and configured:
            return [str(item) for item in configured]
        return default
