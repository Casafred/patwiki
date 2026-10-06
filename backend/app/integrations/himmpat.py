"""HimmPat MCP adapter.

HimmPat exposes several MCP services.  This module maps those service/tool
contracts into PatWiki's provider-neutral patent connector contract; the
generic MCP protocol implementation remains in ``mcp_transport``.
"""
from __future__ import annotations

from datetime import date, datetime, timezone
import hashlib
from html import unescape
import json
import re
from typing import Any, Mapping
from urllib.parse import urlparse

import httpx

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
    "operations": "product_patent_operations",
    "value": "product_patent_value",
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

# Extended dossier enrichments are kept separate from the legacy workbench
# count so existing clients that enumerate the original 40-tool catalogue
# remain compatible.  The adapter still accepts these tools for selected
# field updates and direct calls.
EXTRA_READ_ONLY_TOOLS = {
    "operations": {
        "get_transfer_data_by_patent_id", "get_license_data_by_patent_id", "get_piedge_by_patent_id", "get_preservation_by_patent_id",
        "get_transfer_details_by_patent_ids", "get_license_details_by_patent_ids", "get_piedge_details_by_patent_ids", "get_preservation_details_by_patent_ids",
    },
    "value": {"get_patent_technology_value_by_patent_id", "get_patent_legal_value_by_patent_id",
              "get_patent_market_value_by_patent_id", "get_patent_strategic_value_by_patent_id",
              "get_patent_value_evaluation_v2_by_patent_id"},
}

def _read_only_tools(service_key: str) -> set[str]:
    return set(READ_ONLY_TOOLS.get(service_key, set())) | set(EXTRA_READ_ONLY_TOOLS.get(service_key, set()))
DOSSIER_UPDATE_FIELDS = {
    "publication_number", "application_number", "title", "abstract", "applicant", "assignee", "inventor",
    "agent", "filing_date", "publication_date", "country", "ipc_all", "priority_number", "priority_date",
    "claims", "description_full", "technical_problem", "technical_solution", "technical_effect",
    "legal_status_details",
    "mcp_record_fields", "mcp_priority_claims", "mcp_classification_details", "mcp_party_details",
    "mcp_claim_metadata", "mcp_description_metadata", "mcp_family_members", "mcp_citation_data",
    "mcp_cited_patents", "mcp_legal_event_details", "mcp_reexamination", "mcp_invalidation",
    "mcp_transfer_events", "mcp_license_events", "mcp_pledge_events", "mcp_preservation_events",
    "mcp_value_evaluation", "mcp_technology_value", "mcp_legal_value", "mcp_market_value",
    "mcp_strategic_value", "mcp_pdf_original", "mcp_abstract_figure", "mcp_description_figures",
}

# Maps each read-only MCP tool to the canonical patent fields its result can
# populate.  The workbench uses this so a tool result can be written back to
# the patent workspace through the same review pipeline as a refresh, instead
# of being stored as an opaque snapshot only.
TOOL_FIELD_MAPPING: dict[str, dict[str, Any]] = {
    "get_patent_publication_by_patent_ids": {"kind": "dossier"},
    "get_patent_record_fields_by_patent_ids": {"kind": "dossier_full"},
    "get_claims_by_patent_id": {"kind": "text", "field": "claims"},
    "get_description_by_patent_id": {"kind": "text", "field": "description_full"},
    "get_patent_ai_tech_info": {
        "kind": "technical",
        "fields": ("technical_problem", "technical_solution", "technical_effect"),
    },
    "get_patent_legal_status_by_patent_ids": {"kind": "legal"},
    "get_legal_details_by_patent_id": {"kind": "legal_details", "field": "legal_status_details"},
    "get_patent_family_by_patent_id": {"kind": "custom", "field": "mcp_family_members"},
    "get_patent_citations_by_patent_id": {"kind": "custom", "field": "mcp_cited_patents"},
    "get_patent_citation_data_by_patent_id": {"kind": "custom", "field": "mcp_citation_data"},
    "get_abstract_and_figures_by_patent_ids": {"kind": "resource", "field": "mcp_abstract_figure", "resource_kind": "abstract_figure"},
    "get_figures_by_patent_ids": {"kind": "resource", "field": "mcp_description_figures", "resource_kind": "description_figure"},
    "get_pdf_by_patent_ids": {"kind": "resource", "field": "mcp_pdf_original", "resource_kind": "pdf"},
    "get_reexamination_by_patent_id": {"kind": "custom", "field": "mcp_reexamination"},
    "get_invalidation_by_patent_id": {"kind": "custom", "field": "mcp_invalidation"},
    "get_transfer_data_by_patent_id": {"kind": "custom", "field": "mcp_transfer_events"},
    "get_license_data_by_patent_id": {"kind": "custom", "field": "mcp_license_events"},
    "get_piedge_by_patent_id": {"kind": "custom", "field": "mcp_pledge_events"},
    "get_preservation_by_patent_id": {"kind": "custom", "field": "mcp_preservation_events"},
    "get_patent_technology_value_by_patent_id": {"kind": "custom", "field": "mcp_technology_value"},
    "get_patent_legal_value_by_patent_id": {"kind": "custom", "field": "mcp_legal_value"},
    "get_patent_market_value_by_patent_id": {"kind": "custom", "field": "mcp_market_value"},
    "get_patent_strategic_value_by_patent_id": {"kind": "custom", "field": "mcp_strategic_value"},
    "get_patent_value_evaluation_v2_by_patent_id": {"kind": "custom", "field": "mcp_value_evaluation"},
}


def tool_mappable_fields(tool_name: str) -> list[str]:
    """Return the canonical patent fields a tool result can be mapped onto."""
    spec = TOOL_FIELD_MAPPING.get(tool_name)
    if not spec:
        return []
    kind = spec.get("kind")
    if kind in {"dossier", "dossier_full"}:
        base = DOSSIER_UPDATE_FIELDS - {"claims", "description_full", "technical_problem", "technical_solution", "technical_effect"} - {
            "mcp_record_fields", "mcp_priority_claims", "mcp_classification_details", "mcp_party_details",
            "mcp_claim_metadata", "mcp_description_metadata", "mcp_family_members", "mcp_citation_data",
            "mcp_cited_patents", "mcp_legal_event_details", "mcp_reexamination", "mcp_invalidation",
            "mcp_transfer_events", "mcp_license_events", "mcp_pledge_events", "mcp_preservation_events",
            "mcp_value_evaluation", "mcp_technology_value", "mcp_legal_value", "mcp_market_value",
            "mcp_strategic_value", "mcp_pdf_original", "mcp_abstract_figure", "mcp_description_figures",
        }
        if kind == "dossier_full":
            base |= {"mcp_record_fields", "mcp_priority_claims", "mcp_classification_details", "mcp_party_details"}
        return sorted(base)
    if kind == "text":
        return [str(spec["field"])]
    if kind == "technical":
        return list(spec["fields"])
    if kind == "legal":
        return ["legal_status", "grant_date"]
    if kind == "legal_details":
        return [str(spec["field"])]
    if kind in {"custom", "resource"}:
        return [str(spec["field"])]
    return []



def _leaf_texts(value: Any) -> list[str]:
    """Collect every non-empty string leaf in a provider structure.

    Full-text tools (claims/description) differ in shape across HimmPat
    services: sometimes a plain string, sometimes a mapping keyed by claim
    number, sometimes a ``{"claimList": [...]}`` wrapper.  When no known key
    matches we still surface the text deterministically instead of failing.
    """
    if isinstance(value, str):
        text = value.strip()
        return [text] if text else []
    if isinstance(value, Mapping):
        parts: list[str] = []
        for item in value.values():
            parts.extend(_leaf_texts(item))
        return parts
    if isinstance(value, (list, tuple)):
        parts = []
        for item in value:
            parts.extend(_leaf_texts(item))
        return parts
    return []


def _text_field(value: Any, keys: tuple[str, ...], *, fallback: bool = False) -> str | None:
    if isinstance(value, str):
        return value.strip() or None
    if isinstance(value, Mapping):
        for key in keys:
            if key in value:
                text = _text_field(value[key], keys, fallback=fallback)
                if text:
                    return text
        if fallback:
            return "\n\n".join(_leaf_texts(value)) or None
    if isinstance(value, list):
        parts = [_text_field(item, keys, fallback=fallback) for item in value]
        joined = "\n\n".join(part for part in parts if part)
        if joined:
            return joined
        if fallback:
            return "\n\n".join(_leaf_texts(value)) or None
    return None


def _clean_claim_text(value: str) -> str:
    """Turn HimmPat claim XML into readable plain text for local fields."""
    source = str(value or "")
    matches = re.findall(r"<claim\b([^>]*)>(.*?)</claim\s*>", source, flags=re.IGNORECASE | re.DOTALL)
    blocks: list[str] = []
    for attributes, body in matches:
        number_match = re.search(r"\bnum\s*=\s*['\"]?0*(\d+)", attributes, flags=re.IGNORECASE)
        text = re.sub(r"<(?:claim-text|p|br)\b[^>]*>", "\n", body, flags=re.IGNORECASE)
        text = re.sub(r"</(?:claim-text|p|br)\s*>", "\n", text, flags=re.IGNORECASE)
        text = re.sub(r"<[^>]+>", "", text)
        text = unescape(text)
        text = re.sub(r"[ \t]+", " ", text)
        text = re.sub(r" *\n *", "\n", text)
        text = re.sub(r"\n{3,}", "\n\n", text).strip()
        if number_match:
            number = number_match.group(1)
            text = re.sub(rf"^(?:{re.escape(number)}\s*[.、:]\s*)+", "", text)
            text = f"{number}. {text}".strip()
        if text:
            blocks.append(text)
    if blocks:
        return "\n\n".join(blocks)
    text = re.sub(r"<[^>]+>", "", unescape(source))
    return re.sub(r"\s+", " ", text).strip()


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
        if self.config.get("enrich_legal_on_fetch", False) or self.config.get("enrich_legal_status", False) or extra.intersection({"legal_status", "grant_date", "legal_status_details"}):
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
            "mcp_claim_metadata": ("get_claims_by_patent_id", {"id": patent_id}),
            "mcp_description_metadata": ("get_description_by_patent_id", {"id": patent_id}),
            "technical": ("get_patent_ai_tech_info", {"ids": [patent_id]}),
            "family_members": ("get_patent_family_by_patent_id", {"id": patent_id}),
            "cited_patents": ("get_patent_citations_by_patent_id", {"id": patent_id}),
            "mcp_family_members": ("get_patent_family_by_patent_id", {"id": patent_id}),
            "mcp_citation_data": ("get_patent_citation_data_by_patent_id", {"id": patent_id}),
            "mcp_cited_patents": ("get_patent_citations_by_patent_id", {"id": patent_id}),
            "mcp_abstract_figure": ("get_abstract_and_figures_by_patent_ids", {"ids": [patent_id]}),
            "mcp_description_figures": ("get_figures_by_patent_ids", {"ids": [patent_id]}),
            "mcp_pdf_original": ("get_pdf_by_patent_ids", {"ids": [patent_id]}),
            "mcp_legal_event_details": ("get_legal_details_by_patent_id", {"id": patent_id}),
            "mcp_reexamination": ("get_reexamination_by_patent_id", {"id": patent_id}),
            "mcp_invalidation": ("get_invalidation_by_patent_id", {"id": patent_id}),
            "mcp_transfer_events": ("get_transfer_data_by_patent_id", {"id": patent_id}),
            "mcp_license_events": ("get_license_data_by_patent_id", {"id": patent_id}),
            "mcp_pledge_events": ("get_piedge_by_patent_id", {"id": patent_id}),
            "mcp_preservation_events": ("get_preservation_by_patent_id", {"id": patent_id}),
            "mcp_technology_value": ("get_patent_technology_value_by_patent_id", {"id": patent_id}),
            "mcp_legal_value": ("get_patent_legal_value_by_patent_id", {"id": patent_id}),
            "mcp_market_value": ("get_patent_market_value_by_patent_id", {"id": patent_id}),
            "mcp_strategic_value": ("get_patent_strategic_value_by_patent_id", {"id": patent_id}),
            "mcp_value_evaluation": ("get_patent_value_evaluation_v2_by_patent_id", {"id": patent_id}),
        }
        values = dict(record.fields)
        evidence = dict(record.raw_payload)
        if fields.intersection({"agent", "priority_number", "priority_date", "mcp_record_fields", "mcp_priority_claims", "mcp_classification_details", "mcp_party_details"}):
            data, envelope = self._call("dossier", "get_patent_record_fields_by_patent_ids", {"ids": [patent_id]})
            detail = data.get(patent_id)
            evidence["get_patent_record_fields_by_patent_ids"] = envelope
            if isinstance(detail, Mapping):
                values.update(self._dossier_record(patent_id, detail, envelope).fields)
                if "mcp_record_fields" in fields:
                    values["mcp_record_fields"] = redact_payload(detail)
                if "mcp_priority_claims" in fields:
                    values["mcp_priority_claims"] = redact_payload(detail.get("priorityClaimsModelList") or detail.get("priorityClaims") or [])
                if "mcp_classification_details" in fields:
                    values["mcp_classification_details"] = redact_payload(detail.get("classificationModel") or {})
                if "mcp_party_details" in fields:
                    values["mcp_party_details"] = redact_payload(detail.get("partiesModel") or {})
        if fields.intersection({"technical_problem", "technical_solution", "technical_effect"}):
            fields = fields | {"technical"}
        # A selected custom projection may need a provider tool from another
        # service.  The requested field remains the stable local contract.
        for field in sorted(fields):
            spec = calls.get(field)
            if not spec:
                continue
            tool, args = spec
            if "id" in args:
                args = self._single_patent_arguments(tool, patent_id)
            service_key = "dossier"
            if tool in READ_ONLY_TOOLS.get("legal", set()):
                service_key = "legal"
            elif tool in _read_only_tools("operations"):
                service_key = "operations"
            elif tool in _read_only_tools("value"):
                service_key = "value"
            data, envelope = self._call(service_key, tool, args)
            evidence[tool] = envelope
            value: Any = data.get(patent_id, data.get("items", data)) if isinstance(data, Mapping) else data
            if field == "technical":
                values.update(self.extract_mapped_fields(tool, value, patent_id))
            elif field in {"claims", "description_full"}:
                keys = ("claims", "claim", "claimsText", "clc", "clo", "cle", "text", "content", "value") if field == "claims" else ("description", "description_full", "descriptionText", "dec", "deo", "dee", "text", "content", "value")
                text = _text_field(value, keys, fallback=True)
                if text:
                    values[field] = _clean_claim_text(text) if field == "claims" and re.search(r"<claims?\b", text, flags=re.IGNORECASE) else text
            elif field in {"mcp_claim_metadata", "mcp_description_metadata"}:
                values[field] = redact_payload(value)
            elif field in {"family_members", "cited_patents"}:
                values[f"mcp_{field}"] = redact_payload(value)
            elif field in {"mcp_pdf_original", "mcp_abstract_figure", "mcp_description_figures"}:
                values[field] = self._resource_projection(value, field, tool, patent_id)
            else:
                values[field] = redact_payload(value)
        return ProviderPatentRecord(record.external_record_id, record.identifiers, values, record.legal_events, record.source_updated_at, record.source_version, evidence)

    @staticmethod
    def _resource_projection(value: Any, field: str, tool: str, patent_id: str) -> Any:
        """Keep only resource metadata; bytes are downloaded during confirm."""
        item = value
        if isinstance(value, Mapping) and patent_id in value:
            item = value[patent_id]
        kind = "pdf" if field == "mcp_pdf_original" else ("abstract_figure" if field == "mcp_abstract_figure" else "description_figure")
        if kind == "pdf":
            path = item.get("path") if isinstance(item, Mapping) else item
            return {"resource_kind": kind, "path": str(path), "tool": tool} if path else None
        if kind == "abstract_figure":
            path = None
            if isinstance(item, Mapping):
                path = item.get("path") or item.get("originalAbstractFigure") or item.get("abstractFigure")
                if isinstance(path, Mapping):
                    path = path.get("path") or path.get("id")
            elif item:
                path = item
            return {"resource_kind": kind, "path": str(path), "tool": tool} if path else None
        paths = item.get("paths") if isinstance(item, Mapping) else item
        if not isinstance(paths, list):
            paths = [paths] if paths else []
        return [
            {"resource_kind": kind, "path": str(path), "figure_index": index + 1, "tool": tool}
            for index, path in enumerate(paths) if path
        ]

    def _single_patent_arguments(self, tool_name: str, patent_id: str) -> dict[str, Any]:
        catalog = getattr(self, "_dossier_catalog", None)
        if catalog is None:
            catalog = self.transport.discover(list(dict.fromkeys(self.services.values())))
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

    def download_resource(self, resource_path: str, resource_kind: str) -> tuple[bytes, str]:
        """Download a HimmPat resource with the connector credential."""
        if not resource_path:
            raise ConnectorError("HimmPat 资源路径为空", error_code="empty_resource_path")
        endpoint = self.transport.endpoint.rstrip("/")
        suffix = "pdf" if resource_kind == "pdf" else "image"
        url = f"{endpoint}/api/service/himmuc_api/resource/get_{suffix}/{resource_path}"
        try:
            response = self.transport.client.get(url, headers=self.transport._headers(None))
            response.raise_for_status()
        except (httpx.HTTPError, ConnectorError) as exc:
            raise ConnectorError("HimmPat 资源下载失败", error_code="resource_download_failed", retryable=True) from exc
        content = response.content
        content_type = (response.headers.get("content-type") or "").split(";", 1)[0].lower()
        if resource_kind == "pdf":
            if not content.startswith(b"%PDF-"):
                raise ConnectorError("HimmPat 返回内容不是 PDF", error_code="invalid_pdf_resource")
            content_type = "application/pdf"
        elif not content.startswith((b"\xff\xd8\xff", b"\x89PNG", b"GIF8", b"RIFF")):
            raise ConnectorError("HimmPat 返回内容不是图片", error_code="invalid_image_resource")
        if not content_type.startswith(("image/", "application/pdf")):
            content_type = "application/pdf" if resource_kind == "pdf" else "image/jpeg"
        return content, content_type

    def call_discovered_tool(self, service_name: str, tool_name: str, arguments: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
        """Execute a discovered read-only tool through the same safe decoder."""
        service_key = next((key for key, name in self.services.items() if name == service_name), None)
        if not service_key:
            raise ConnectorError("未知 MCP 服务", error_code="unknown_service")
        if tool_name not in _read_only_tools(service_key):
            raise ConnectorError("工具未在只读调用白名单中", error_code="unsupported_tool")
        return self._call_by_service_name(service_name, tool_name, arguments)

    def extract_mapped_fields(self, tool_name: str, data: Mapping[str, Any], patent_id: str | None = None) -> dict[str, Any]:
        """Map a raw tool result onto canonical patent fields.

        The workbench lets a user run any read-only tool; this turns the
        provider-specific payload into the same field dict the refresh
        pipeline produces, so results can be written back through the shared
        review/confirm flow instead of remaining an opaque snapshot.
        """
        spec = TOOL_FIELD_MAPPING.get(tool_name)
        if not spec:
            return {}
        kind = spec["kind"]
        if kind in {"dossier", "dossier_full"}:
            item = self._select_patent_item(data, patent_id)
            if not isinstance(item, Mapping):
                return {}
            result = dict(self._dossier_record(str(patent_id or item.get("id") or ""), item, data).fields)
            if kind == "dossier_full":
                result.update({
                    "mcp_record_fields": redact_payload(item),
                    "mcp_priority_claims": redact_payload(item.get("priorityClaimsModelList") or item.get("priorityClaims") or []),
                    "mcp_classification_details": redact_payload(item.get("classificationModel") or {}),
                    "mcp_party_details": redact_payload(item.get("partiesModel") or {}),
                })
            return result
        if kind == "text":
            value = self._select_patent_item(data, patent_id)
            keys = ("claims", "claim", "claimsText", "clc", "clo", "cle", "text", "content", "value") if spec["field"] == "claims" else ("description", "description_full", "descriptionText", "dec", "deo", "dee", "text", "content", "value")
            text = _text_field(value, keys, fallback=True)
            if spec["field"] == "claims" and text and re.search(r"<claims?\b", text, flags=re.IGNORECASE):
                text = _clean_claim_text(text)
            return {str(spec["field"]): text} if text else {}
        if kind == "technical":
            value = self._select_patent_item(data, patent_id)
            if not isinstance(value, (Mapping, list)):
                return {}
            aliases = {
                "technical_problem": ("technical_problem", "technicalProblem", "aiTechProblem", "problem"),
                "technical_solution": ("technical_solution", "technicalSolution", "technicalMeans", "aiTechMeans", "solution"),
                "technical_effect": ("technical_effect", "technicalEffect", "aiTechEffect", "effect"),
            }
            result: dict[str, Any] = {}
            for key, alias_keys in aliases.items():
                text = _text_field(value, alias_keys)
                if text:
                    result[key] = text
            return result
        if kind == "legal":
            value = self._select_patent_item(data, patent_id)
            if not isinstance(value, Mapping):
                return {}
            result = {"legal_status": _status(value.get("state"), value.get("stc"))}
            grant = _date(value.get("grd"))
            if grant:
                result["grant_date"] = grant
            return result
        if kind == "legal_details":
            value = self._select_patent_item(data, patent_id)
            if value in (None, "", [], {}):
                return {}
            return {str(spec["field"]): json.dumps(redact_payload(value), ensure_ascii=False, sort_keys=True)}
        if kind in {"custom", "resource"}:
            value = self._select_patent_item(data, patent_id)
            field = str(spec["field"])
            if kind == "resource":
                value = self._resource_projection(value, field, tool_name, str(patent_id or ""))
            if value in (None, "", [], {}):
                return {}
            return {field: redact_payload(value)}
        return {}

    @staticmethod
    def _select_patent_item(data: Mapping[str, Any], patent_id: str | None) -> Any:
        if not isinstance(data, Mapping):
            return data
        if patent_id and patent_id in data:
            return data[patent_id]
        if "items" in data:
            return data["items"]
        if len(data) == 1:
            return next(iter(data.values()))
        return data

    def _call_by_service_name(self, service_name: str, tool_name: str, arguments: dict[str, Any]):
        raw = self.transport.call_tool(service_name, tool_name, arguments)
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
        # HimmPat uses business code 201 for a valid empty result while MCP
        # may mark the JSON-RPC content block as isError.  Preserve that
        # distinction so optional fields can simply remain unchanged.
        if code == 201:
            return {}, dict(redact_payload(envelope))
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
