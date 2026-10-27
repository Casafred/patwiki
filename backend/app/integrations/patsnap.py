"""PatSnap (智慧芽) Streamable HTTP MCP adapter.

PatSnap exposes one MCP endpoint and returns provider business payloads in
``{success, error_code, data}``.  This adapter converts the documented
read-only tools to PatWiki's provider-neutral patent connector contract so it
can be selected anywhere the existing HimmPat adapter is accepted.
"""
from __future__ import annotations

from datetime import date, datetime, timezone
import hashlib
import json
import re
from typing import Any, Mapping
from urllib.parse import urlsplit
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


DEFAULT_ENDPOINT = "https://connect.zhihuiya.com/1458a4/mcp"
DEFAULT_INTELLIGENT_IMAGE_ENDPOINT = "https://connect.zhihuiya.com/958a46/mcp"
SERVICE_NAME = "patsnap"
# One entry per provider tool; this is also the update-field allowlist.
TOOL_FIELDS = {
    "bibliography": ["publication_number", "application_number", "title", "abstract", "applicant", "assignee", "inventor", "agent", "filing_date", "publication_date", "grant_date", "country", "ipc_main", "ipc_all", "cpc_main", "cpc_all", "priority_number", "priority_date", "priority_country", "cited_patents", "mcp_record_fields", "mcp_priority_claims", "mcp_classification_details", "mcp_party_details"],
    "family": ["family_members", "mcp_family_members"],
    "forward_citation": ["citing_patents", "mcp_citation_data"],
    "claims": ["claims", "mcp_claim_metadata"],
    "description": ["description_full", "mcp_description_metadata"],
    "get_patent_legal_status": ["legal_status"],
    "legal_data": ["legal_status_details", "mcp_legal_event_details"],
    "abstract_image": ["mcp_abstract_figure"],
    "fulltext_image": ["mcp_description_figures"],
    "pdf": ["mcp_pdf_original"],
    "abstract_translated": ["mcp_abstract_translation"],
    "claim_translated": ["mcp_claim_translation"],
    "description_translated": ["mcp_description_translation"],
    "reexamination_invalidation": ["mcp_reexamination_invalidation"],
    "license_data": ["mcp_license_events"],
    "transfer_data": ["mcp_transfer_events"],
    "pledge_data": ["mcp_pledge_events"],
    "customs_data": ["mcp_customs_data"],
    "award_data": ["mcp_award_data"],
    "tech_summary": ["technical_problem", "technical_solution", "technical_effect", "mcp_tech_summary"],
    "intelligent_image": ["mcp_intelligent_figures"],
}
DEFAULT_TOOLS = {name: name for name in TOOL_FIELDS}
DEFAULT_TOOLS.update(search="search_patents", legal_status="get_patent_legal_status")
READ_ONLY_TOOLS = frozenset(DEFAULT_TOOLS.values())
UPDATE_FIELDS = set(field for fields in TOOL_FIELDS.values() for field in fields)
RESOURCE_FIELDS = {"mcp_pdf_original", "mcp_abstract_figure", "mcp_description_figures", "mcp_intelligent_figures"}
BRIEFING_TOOLS = {"tech_summary", "intelligent_image"}


def tool_mappable_fields(tool_name: str) -> list[str]:
    return TOOL_FIELDS.get(tool_name, [])


def safe_evidence(value: Any) -> Any:
    """Signed download URLs are transient credentials, never durable evidence."""
    value = redact_payload(value)
    if isinstance(value, Mapping):
        return {key: safe_evidence(item) for key, item in value.items()}
    if isinstance(value, list):
        return [safe_evidence(item) for item in value]
    if isinstance(value, str) and value.startswith('https://'):
        return value.split('?', 1)[0]
    return value


def _classification(value: Any) -> tuple[str | None, list[str]]:
    def symbol(item):
        if isinstance(item, str): return item
        if not isinstance(item, Mapping): return None
        if item.get('section'):
            return f"{item.get('section', '')}{item.get('class', '')}{item.get('sub_class', '')}{item.get('main_group', '')}/{item.get('sub_group', '')}"
        return item.get('text') or item.get('classification_symbol')
    if isinstance(value, Mapping):
        main = symbol(value.get('main_classification'))
        rest = value.get('further_classification') or []
        rest = rest if isinstance(rest, list) else [rest]
        return main, list(dict.fromkeys(x for x in [main, *(symbol(item) for item in rest)] if x))
    values = value if isinstance(value, list) else [value]
    values = [x for item in values if (x := symbol(item))]
    return (values[0] if values else None), values


def _date(value: Any) -> date | None:
    if value in (None, ""):
        return None
    text = str(value).strip()
    if re.fullmatch(r"\d{8}", text):
        text = f"{text[:4]}-{text[4:6]}-{text[6:]}"
    try:
        return date.fromisoformat(text[:10])
    except ValueError:
        return None


def _text(value: Any) -> str | None:
    if value in (None, ""):
        return None
    if isinstance(value, str):
        return value.strip() or None
    if isinstance(value, Mapping):
        for key in ("text", "value", "name", "title", "content", "claim_text", "claims", "description"):
            if key in value:
                found = _text(value[key])
                if found:
                    return found
        return "\n\n".join(x for item in value.values() if (x := _text(item))) or None
    if isinstance(value, (list, tuple)):
        return "\n\n".join(x for item in value if (x := _text(item))) or None
    return str(value)


def _language(value: Any) -> str | None:
    if isinstance(value, Mapping):
        return _text(value)
    if isinstance(value, list):
        preferred = next((item for item in value if isinstance(item, Mapping) and str(item.get("lang", "")).upper() in {"CN", "ZH"}), None)
        return _text(preferred or value)
    return _text(value)


def _people(value: Any) -> str | None:
    if isinstance(value, str):
        return value.strip() or None
    if isinstance(value, Mapping):
        return _text(value)
    if isinstance(value, list):
        names = []
        for item in value:
            name = _text(item)
            if name and name not in names:
                names.append(name)
        return "、".join(names) or None
    return None


def _number(value: Any) -> str | None:
    if isinstance(value, Mapping):
        for key in ("pn", "publication_number", "publicationNumber", "number"):
            if value.get(key):
                return str(value[key]).strip()
        if value.get("country") and value.get("doc_number"):
            return f"{value['country']}{value['doc_number']}{value.get('kind') or ''}".strip()
        if value.get("doc_number"):
            return str(value["doc_number"]).strip()
        return None
    return str(value).strip() if value not in (None, "") else None


def _numbers(value: Any) -> list[str]:
    result: list[str] = []
    def visit(item: Any) -> None:
        if isinstance(item, Mapping):
            for key in ("pn", "publication_number", "publicationNumber", "number"):
                if item.get(key):
                    value = str(item[key]).strip()
                    if value and value not in result:
                        result.append(value)
            # PatSnap family members are commonly represented as
            # {country, doc_number, kind}; normalize that provider shape to
            # the publication-number string used by PatWiki.
            if item.get("country") and item.get("doc_number"):
                value = f"{item['country']}{item['doc_number']}{item.get('kind') or ''}".strip()
                if value and value not in result:
                    result.append(value)
            elif item.get("doc_number"):
                value = str(item["doc_number"]).strip()
                if value and value not in result:
                    result.append(value)
            for child in item.values():
                if isinstance(child, (Mapping, list, tuple)):
                    visit(child)
        elif isinstance(item, (list, tuple)):
            for child in item:
                visit(child)
        elif isinstance(item, str) and re.fullmatch(r"[A-Za-z]{2,3}\d+[A-Za-z]?\d*", item.strip()):
            if item.strip() not in result:
                result.append(item.strip())
    visit(value)
    return result


def _path(value: Any, path: str, default: Any = None) -> Any:
    current = value
    for token in [part for part in re.split(r"\.|\[|\]", path) if part]:
        if isinstance(current, Mapping):
            current = current.get(token, default)
        elif isinstance(current, list) and token.isdigit() and int(token) < len(current):
            current = current[int(token)]
        else:
            return default
    return current


def _status(value: Any) -> str:
    text = " ".join(str(x) for x in value) if isinstance(value, list) else str(value or "")
    upper = text.upper()
    if any(x in text for x in ("失效", "终止", "无效", "过期", "Expired")) or any(x in upper for x in ("EXPIRED", "LAPSED")):
        return "expired"
    if any(x in text for x in ("授权", "有效", "Granted")) or "GRANTED" in upper:
        return "granted"
    if any(x in text for x in ("驳回", "拒绝", "Rejected")) or "REJECTED" in upper:
        return "rejected"
    if any(x in text for x in ("放弃", "撤回", "Abandoned")) or "ABANDONED" in upper:
        return "abandoned"
    if text:
        return "pending"
    return "unknown"


class PatsnapMcpAdapter(PatentConnector):
    """Read-only PatSnap adapter compatible with HimmPat's sync contract."""

    def __init__(self, config: dict[str, Any] | None = None, *, endpoint: str | None = None,
                 credential_ref: str | None = None, transport: McpTransport | None = None):
        self.config = config or {}
        self.tools = {**DEFAULT_TOOLS, **dict(self.config.get("tools") or {})}
        self._resource_urls: dict[str, str] = {}
        self.service_name = str(self.config.get("service_name") or SERVICE_NAME)
        self.transport = transport or McpTransport(
            endpoint or self.config.get("endpoint") or DEFAULT_ENDPOINT,
            credential_ref=credential_ref or self.config.get("credential_ref"),
            credential_value=self.config.get("credential_value") or (self.config.get("auth") or {}).get("credential_value"),
            service_path_template=None,
            protocol_version=str(self.config.get("protocol_version", "2025-03-26")),
            timeout_seconds=float(self.config.get("timeout_seconds", 45)),
            retry_config=dict(self.config.get("retry") or {}),
        )

    def close(self) -> None:
        self.transport.close()

    def _briefing_call(self, tool: str, arguments: dict[str, Any]) -> tuple[Any, dict[str, Any]]:
        transport = McpTransport(
            str(self.config.get("intelligent_image_endpoint") or DEFAULT_INTELLIGENT_IMAGE_ENDPOINT),
            credential_ref=self.transport.credential_ref, credential_value=self.transport.credential_value,
            service_path_template=None, protocol_version="2025-03-26",
            timeout_seconds=float(self.config.get("timeout_seconds", 60)),
        )
        try:
            return self._decode(transport.call_tool("briefing", self.tools[tool], arguments))
        finally:
            transport.close()

    def intelligent_images(self, patent_number: str, *, lang: str = "CN") -> tuple[Any, dict[str, Any]]:
        return self._briefing_call("intelligent_image", {"pn": patent_number, "lang": lang})

    @staticmethod
    def download_intelligent_image(url: str) -> tuple[bytes, str]:
        parsed = urlsplit(str(url))
        if parsed.scheme != "https" or parsed.hostname not in {"data-abstract-image.zhihuiya.com", "data-fulltext-image.zhihuiya.com"} or parsed.username or parsed.port:
            raise ConnectorError("智能附图资源域未验证", error_code="invalid_resource_host")
        try:
            with httpx.Client(timeout=httpx.Timeout(45.0, connect=10.0), follow_redirects=False) as client:
                response = client.get(url)
            if response.status_code != 200:
                raise ConnectorError("智能附图下载失败", error_code="resource_download_failed", retryable=True)
            content = response.content
            if len(content) > 12 * 1024 * 1024:
                raise ConnectorError("智能附图超过 12MB", error_code="resource_too_large")
            content_type = (response.headers.get("content-type") or "").split(";", 1)[0].lower()
            if content_type not in {"image/png", "image/jpeg", "image/webp"}:
                raise ConnectorError("智能附图返回内容不是支持的图片", error_code="invalid_image_resource")
            return content, content_type
        except ConnectorError:
            raise
        except (httpx.TimeoutException, httpx.TransportError) as exc:
            raise ConnectorError("智能附图网络请求失败", error_code="resource_download_failed", retryable=True) from exc

    def capabilities(self) -> ConnectorCapabilities:
        return ConnectorCapabilities(search=True, fetch_patent=True, legal_events=bool(self.config.get("enrich_legal_status", True)), cursor_pagination=True)

    def healthcheck(self) -> ConnectorHealth:
        started = datetime.now(timezone.utc)
        catalog = self.transport.discover([self.service_name])
        latency = int((datetime.now(timezone.utc) - started).total_seconds() * 1000)
        count = sum(item.get("tool_count", 0) for item in catalog.get("services", []))
        return ConnectorHealth(status="ok", message=f"PatSnap MCP 已连接，发现 {count} 个工具", latency_ms=latency)

    def discover_tools(self) -> dict[str, Any]:
        catalog = self.transport.discover([self.service_name])
        transport = McpTransport(
            str(self.config.get("intelligent_image_endpoint") or DEFAULT_INTELLIGENT_IMAGE_ENDPOINT),
            credential_ref=self.transport.credential_ref, credential_value=self.transport.credential_value,
            service_path_template=None, protocol_version="2025-03-26",
        )
        try:
            extra = transport.discover(["briefing"])
            for service in extra.get("services", []):
                service["tools"] = [tool for tool in service.get("tools", []) if tool.get("name") in BRIEFING_TOOLS]
                service["tool_count"] = len(service["tools"])
            catalog["services"].extend(extra.get("services", []))
        finally:
            transport.close()
        return catalog

    @staticmethod
    def _decode(raw: Any) -> tuple[Any, dict[str, Any]]:
        result = raw.get("structuredContent") if isinstance(raw, Mapping) else raw
        if not isinstance(result, Mapping): result = raw
        text = next((item.get("text") for item in (result.get("content", []) if isinstance(result, Mapping) else []) if isinstance(item, Mapping) and item.get("type") == "text"), None)
        if isinstance(text, str):
            try: result = json.loads(text)
            except json.JSONDecodeError as exc:
                raise ConnectorError("PatSnap MCP 业务结果不是有效 JSON", error_code="invalid_provider_json") from exc
        if not isinstance(result, Mapping):
            raise ConnectorError("PatSnap MCP 业务结果结构无效", error_code="invalid_provider_payload")
        if (result.get("success") is not True and result.get("status") is not True) or int(result.get("error_code", 0) or 0) != 0:
            raise ConnectorError(f"PatSnap 业务请求未成功（错误码 {result.get('error_code', 'unknown')}）", error_code="provider_business_error")
        return result.get("data"), dict(safe_evidence(result))

    def _call(self, tool_key: str, arguments: dict[str, Any]) -> tuple[Any, dict[str, Any]]:
        if tool_key in BRIEFING_TOOLS:
            return self._briefing_call(tool_key, arguments)
        return self._decode(self.transport.call_tool(self.service_name, self.tools.get(tool_key, tool_key), arguments))

    def search(self, query: CanonicalPatentQuery, cursor: str | None, limit: int) -> SearchPage:
        expression = (query.expression or query.extra.get("query_text") or "").strip()
        if not expression and query.applicant:
            expression = f"PA=({query.applicant})"
        if not expression:
            raise ConnectorError("PatSnap 检索需要 expression 或 applicant", error_code="missing_query")
        offset = max(0, int(cursor or 0))
        size = max(1, min(100, int(limit)))
        data, envelope = self._call("search", {"query_text": expression, "offset": offset, "limit": size, "collapse_type": "ALL"})
        if not isinstance(data, Mapping):
            raise ConnectorError("PatSnap 检索结果结构无效", error_code="invalid_response_shape")
        rows = data.get("results") or data.get("items") or []
        if not isinstance(rows, list):
            raise ConnectorError("PatSnap 检索结果不是数组", error_code="invalid_response_shape")
        records = tuple(self._summary_record(row) for row in rows if isinstance(row, Mapping) and _number(row))
        total = int(data.get("total_search_result_count") or data.get("total") or 0)
        next_cursor = str(offset + len(records)) if records and (total <= 0 or offset + len(records) < total) else None
        return SearchPage(records=records, next_cursor=next_cursor, watermark=datetime.now(timezone.utc).replace(tzinfo=None), source_version="patsnap-mcp")

    def fetch_patent(self, identifier: ProviderIdentifier) -> ProviderPatentRecord:
        return self.fetch_patent_fields(identifier, set(self.config.get("enrich_dossier_fields") or []))

    def fetch_patent_fields(self, identifier: ProviderIdentifier, requested_fields: set[str]) -> ProviderPatentRecord:
        number = identifier.raw_value
        data, envelope = self._call("bibliography", {"patent_number": number})
        row = self._select_row(data, number)
        if not isinstance(row, Mapping):
            raise ConnectorError("PatSnap 著录项响应无效", error_code="invalid_response_shape")
        record = self._bibliography_record(row, number, envelope)
        fields = set(requested_fields)
        if not fields and self.config.get("enrich_legal_on_fetch", True): fields.add("legal_status")
        result = dict(record.fields)
        evidence = {"bibliography": envelope}
        for tool, offered in TOOL_FIELDS.items():
            if tool == "bibliography" or not fields.intersection(offered): continue
            arguments: dict[str, Any] = {"patent_number": number}
            if tool in {"claims", "description"} or tool.endswith("translated"):
                arguments["replace_by_related"] = 0
            if tool.endswith("translated") or tool == "tech_summary":
                arguments["lang"] = str(self.config.get("translation_language") or "CN")
            if tool == "intelligent_image": arguments = {"pn": number, "lang": "CN"}
            if tool == "fulltext_image": arguments.update(limit=100, offset=0)
            value, raw = self._call(tool, arguments)
            if tool == "fulltext_image" and isinstance(value, Mapping):
                images = list(value.get("fulltext_image") or [])
                total = int(value.get("total_search_result_count") or len(images))
                # Get every page; fail visibly rather than claiming a truncated set is complete.
                while len(images) < total:
                    page, page_raw = self._call(tool, {**arguments, "offset": len(images)})
                    more = page.get("fulltext_image", []) if isinstance(page, Mapping) else []
                    if not more: raise ConnectorError("智慧芽全文附图分页不完整", error_code="incomplete_figures")
                    images.extend(more)
                value = {**value, "fulltext_image": images}
            mapped = self.extract_mapped_fields(self.tools[tool], value, number)
            result.update({key: val for key, val in mapped.items() if val not in (None, "", [], {})})
            evidence[tool] = raw
        # Retain legal event evidence for the existing governance pipeline.
        events = []
        for item in (result.get("mcp_legal_event_details") or []):
            legal = item.get("patsnap_legal_data", {}) if isinstance(item, Mapping) else {}
            for event in legal.get("inpadoc_legal_data", []):
                when = _date(event.get("event_date"))
                status = {"GR01": "granted", "PB01": "published", "SE01": "examining"}.get(event.get("event_code"))
                if when and status:
                    stable = hashlib.sha256(json.dumps(event, sort_keys=True).encode()).hexdigest()[:40]
                    events.append(ProviderLegalEvent(f"patsnap:{stable}", str(event.get("event_code") or "LEGAL"), when, status, result.get("country"), payload=dict(safe_evidence(event))))
        if result.get("grant_date") and not events and "legal_status" in fields:
            events.append(ProviderLegalEvent(f"patsnap:{number}:grant", "GRANT", _date(result["grant_date"]), result.get("legal_status"), result.get("country")))
        return ProviderPatentRecord(record.external_record_id, record.identifiers, result, tuple(events), record.source_updated_at, record.source_version, evidence)

    def _with_field(self, record: ProviderPatentRecord, field: str, value: Any, payload: dict[str, Any], raw: dict[str, Any]) -> ProviderPatentRecord:
        fields = dict(record.fields)
        if value not in (None, "", [], {}):
            fields[field] = value
        payload[field] = raw
        return ProviderPatentRecord(record.external_record_id, record.identifiers, fields, record.legal_events, record.source_updated_at, record.source_version, payload)

    def _summary_record(self, item: Mapping[str, Any]) -> ProviderPatentRecord:
        number = _number(item)
        app = item.get("application_number") or item.get("applicationNumber") or item.get("ap")
        jurisdiction = str(item.get("country") or (number[:2] if number else "")).upper() or None
        fields = {key: value for key, value in {
            "publication_number": number, "application_number": app, "title": _text(item.get("title") or item.get("ti")),
            "abstract": _text(item.get("abstract") or item.get("ab")), "applicant": _people(item.get("applicants") or item.get("applicant") or item.get("pa")),
            "filing_date": _date(item.get("application_date") or item.get("apd")), "publication_date": _date(item.get("publication_date") or item.get("pd")), "country": jurisdiction,
        }.items() if value is not None}
        return ProviderPatentRecord(str(item.get("patent_id") or item.get("id") or number), (ProviderIdentifier("publication", number, jurisdiction),), fields, source_version="patsnap-mcp", raw_payload=dict(redact_payload(item)))

    def _bibliography_record(self, item: Mapping[str, Any], requested_number: str, envelope: Mapping[str, Any]) -> ProviderPatentRecord:
        b = item.get("bibliographic_data") if isinstance(item.get("bibliographic_data"), Mapping) else item
        application = b.get("application_reference") or b.get("applicationReference") or {}
        publication = b.get("publication_reference") or b.get("publicationReference") or {}
        parties = b.get("parties") or {}
        number = _number(publication) or _number(item) or requested_number
        application_number = (str(application.get("country") or "") + str(application.get("doc_number") or application.get("docNumber") or "")).strip() or None
        jurisdiction = str(publication.get("country") or (number[:2] if number else "")).upper() or None
        fields = {key: value for key, value in {
            "publication_number": number, "application_number": application_number, "title": _language(b.get("invention_title") or b.get("inventionTitle")),
            "abstract": _language(b.get("abstracts") or b.get("abstract")), "applicant": _people(parties.get("applicants") or b.get("applicants")),
            "assignee": _people(parties.get("assignees") or b.get("assignees")), "inventor": _people(parties.get("inventors") or b.get("inventors")),
            "filing_date": _date(application.get("date")), "publication_date": _date(publication.get("date")), "country": jurisdiction,
            "priority_number": _number((b.get("priority_claims") or [{}])[0]) if b.get("priority_claims") else None,
            "priority_date": _date((b.get("priority_claims") or [{}])[0].get("date")) if b.get("priority_claims") else None,
            "ipc_main": _classification((b.get("classification_data") or {}).get("classification_ipcr"))[0],
            "ipc_all": _classification((b.get("classification_data") or {}).get("classification_ipcr"))[1],
            "cpc_main": _classification((b.get("classification_data") or {}).get("classification_cpc"))[0],
            "cpc_all": _classification((b.get("classification_data") or {}).get("classification_cpc"))[1],
            "agent": _people(parties.get("agents")),
            "priority_country": (b.get("priority_claims") or [{}])[0].get("country"),
            "grant_date": _date((b.get("dates_of_public_availability") or {}).get("printed_with_granted")),
            "cited_patents": ", ".join(_numbers((b.get("reference_cited") or {}).get("cited_patents"))),
            "mcp_record_fields": redact_payload(b),
            "mcp_priority_claims": redact_payload(b.get("priority_claims")),
            "mcp_classification_details": redact_payload(b.get("classification_data")),
            "mcp_party_details": redact_payload(parties),
        }.items() if value is not None}
        return ProviderPatentRecord(str(item.get("patent_id") or item.get("id") or number), (ProviderIdentifier("publication", number, jurisdiction),), fields, source_version="patsnap-mcp", raw_payload=dict(redact_payload(envelope)))

    @staticmethod
    def _select_row(data: Any, number: str) -> Any:
        if isinstance(data, list):
            return next((item for item in data if isinstance(item, Mapping) and (_number(item) == number or not number)), data[0] if data else None)
        if isinstance(data, Mapping):
            if number in data:
                return data[number]
            if isinstance(data.get("results"), list):
                return PatsnapMcpAdapter._select_row(data["results"], number)
            return data
        return None

    def call_discovered_tool(self, service_name: str, tool_name: str, arguments: dict[str, Any]) -> tuple[Any, dict[str, Any]]:
        if service_name == "briefing" and tool_name in BRIEFING_TOOLS:
            return self._briefing_call(tool_name, arguments)
        if service_name != self.service_name or tool_name not in READ_ONLY_TOOLS:
            raise ConnectorError("工具未在智慧芽只读调用白名单中", error_code="unsupported_tool")
        return self._call(tool_name, arguments)

    def _resources(self, data: Any, field: str) -> list[dict[str, Any]]:
        result = []
        def visit(item):
            if isinstance(item, list):
                for child in item: visit(child)
            elif isinstance(item, Mapping):
                path = item.get("storage_path") or item.get("path")
                if isinstance(path, str) and path.startswith("https://"):
                    stable = path.split("?", 1)[0]
                    if stable not in {entry["path"] for entry in result}:
                        self._resource_urls[stable] = path
                        result.append({**safe_evidence(item), "path": stable,
                                       "resource_kind": "pdf" if field == "mcp_pdf_original" else "image",
                                       "figure_index": item.get("fig_title_code") or item.get("num") or len(result) + 1})
                else:
                    for child in item.values():
                        if isinstance(child, (list, Mapping)): visit(child)
        visit(data)
        return result

    def download_resource(self, path: str, kind: str) -> tuple[bytes, str]:
        url = self._resource_urls.get(path)
        if not url:
            raise ConnectorError("附图下载链接已过期，请重新获取供应商资源", error_code="expired_resource")
        if kind != "pdf": return self.download_intelligent_image(url)
        parsed = urlsplit(url)
        if parsed.scheme != "https" or parsed.hostname != "data-pdf.zhihuiya.com" or parsed.username or parsed.port:
            raise ConnectorError("PDF 资源域未验证", error_code="invalid_resource_host")
        with httpx.Client(timeout=60, follow_redirects=False) as client:
            response = client.get(url)
        if response.status_code != 200 or not response.content.startswith(b"%PDF-"):
            raise ConnectorError("PDF 原文下载失败或内容无效", error_code="invalid_pdf_resource")
        if len(response.content) > 100 * 1024 * 1024:
            raise ConnectorError("PDF 原文超过 100MB", error_code="resource_too_large")
        return response.content, "application/pdf"

    def extract_mapped_fields(self, tool_name: str, data: Any, patent_id: str | None = None) -> dict[str, Any]:
        tool = next((name for name in TOOL_FIELDS if self.tools[name] == tool_name), tool_name)
        if tool == "bibliography":
            row = self._select_row(data, patent_id or "")
            return dict(self._bibliography_record(row, patent_id or "", {}).fields) if isinstance(row, Mapping) else {}
        if tool not in TOOL_FIELDS or not data: return {}
        row = self._select_row(data, patent_id or "")
        if tool in {"claims", "description"}:
            field = "claims" if tool == "claims" else "description_full"
            # Read only the text property; do not concatenate PN, IDs or counters.
            collection = row.get("claims" if tool == "claims" else "description") if isinstance(row, Mapping) else data
            text = _language(collection)
            if text:
                from html.parser import HTMLParser
                class PlainText(HTMLParser):
                    def __init__(self): super().__init__(); self.parts = []
                    def handle_data(self, text): self.parts.append(text)
                    def handle_endtag(self, tag):
                        if tag in {"div", "p", "claim"}: self.parts.append("\n")
                parser = PlainText(); parser.feed(text); text = "".join(parser.parts).strip()
            return {field: text, TOOL_FIELDS[tool][1]: safe_evidence(data)}
        if tool == "family":
            family = row.get("patent_family", {}) if isinstance(row, Mapping) else {}
            return {"family_members": ", ".join(_numbers(family.get("simple_family") or family)), "mcp_family_members": safe_evidence(data)}
        if tool == "forward_citation":
            # The response's root PN identifies the source, not a citing member.
            members = []
            def visit(value):
                if isinstance(value, list):
                    for child in value: visit(child)
                elif isinstance(value, Mapping):
                    if value.get("country") and value.get("doc_number"): members.extend(_numbers(value))
                    for key, child in value.items():
                        if key not in {"pn", "patent_id"}: visit(child)
            visit(data)
            return {"citing_patents": ", ".join(dict.fromkeys(members)), "mcp_citation_data": safe_evidence(data)}
        if tool == "get_patent_legal_status":
            result = {"legal_status": _status(row.get("simple_legal_status") if isinstance(row, Mapping) else row)}
            if isinstance(row, Mapping) and row.get("grant_date"): result["grant_date"] = _date(row["grant_date"])
            return result
        if tool == "legal_data":
            return {"legal_status_details": json.dumps(safe_evidence(data), ensure_ascii=False, default=str), "mcp_legal_event_details": safe_evidence(data)}
        if tool == "tech_summary":
            row = row if isinstance(row, Mapping) else {}
            return {"technical_problem": _text(_path(row, "tech_problem_summary.tech_problem_para")),
                    "technical_solution": _text(_path(row, "technical_approach_summary.technical_approach_para")),
                    "technical_effect": _text(_path(row, "benefit_summary.benefit_para")), "mcp_tech_summary": safe_evidence(data)}
        field = TOOL_FIELDS[tool][0]
        if field in RESOURCE_FIELDS: return {field: self._resources(data, field)}
        return {field: safe_evidence(data)}
