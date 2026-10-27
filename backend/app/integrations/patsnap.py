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
DEFAULT_TOOLS = {
    "search": "search_patents",
    "bibliography": "bibliography",
    "family": "family",
    "claims": "claims",
    "description": "description",
    "legal_status": "get_patent_legal_status",
    "legal_data": "legal_data",
    "abstract_image": "abstract_image",
    "fulltext_image": "fulltext_image",
    "intelligent_image": "intelligent_image",
}
READ_ONLY_TOOLS = frozenset(DEFAULT_TOOLS.values())
UPDATE_FIELDS = {
    "publication_number", "application_number", "title", "abstract", "applicant", "assignee",
    "inventor", "filing_date", "publication_date", "country", "ipc_all", "priority_number",
    "priority_date", "claims", "description_full", "family_members", "legal_status",
    "legal_status_details", "mcp_record_fields", "mcp_priority_claims", "mcp_classification_details",
    "mcp_party_details", "mcp_claim_metadata", "mcp_description_metadata", "mcp_legal_event_details",
}


def tool_mappable_fields(tool_name: str) -> list[str]:
    mapping = {
        DEFAULT_TOOLS["bibliography"]: sorted(UPDATE_FIELDS - {
            "claims", "description_full", "family_members", "legal_status", "legal_status_details",
            "mcp_claim_metadata", "mcp_description_metadata", "mcp_legal_event_details",
        }),
        DEFAULT_TOOLS["claims"]: ["claims", "mcp_claim_metadata"],
        DEFAULT_TOOLS["description"]: ["description_full", "mcp_description_metadata"],
        DEFAULT_TOOLS["family"]: ["family_members"],
        DEFAULT_TOOLS["legal_status"]: ["legal_status", "grant_date"],
        DEFAULT_TOOLS["legal_data"]: ["legal_status_details", "mcp_legal_event_details"],
    }
    return mapping.get(tool_name, [])


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

    def intelligent_images(self, patent_number: str, *, lang: str = "CN") -> tuple[Any, dict[str, Any]]:
        """Call the separate briefing MCP used for intelligent patent figures."""
        endpoint = str(self.config.get("intelligent_image_endpoint") or DEFAULT_INTELLIGENT_IMAGE_ENDPOINT)
        transport = McpTransport(
            endpoint,
            credential_ref=self.transport.credential_ref,
            credential_value=self.transport.credential_value,
            service_path_template=None,
            protocol_version=str(self.config.get("intelligent_image_protocol_version", "2025-03-26")),
            timeout_seconds=float(self.config.get("timeout_seconds", 45)),
            retry_config=dict(self.config.get("retry") or {}),
        )
        service = str(self.config.get("intelligent_image_service_name") or "briefing")
        try:
            raw = transport.call_tool(service, self.tools["intelligent_image"], {"pn": patent_number, "lang": lang})
            result = raw.get("structuredContent") if isinstance(raw, Mapping) else raw
            if not isinstance(result, Mapping):
                result = raw
            text_block = next((item.get("text") for item in (result.get("content", []) if isinstance(result, Mapping) else []) if isinstance(item, Mapping) and item.get("type") == "text"), None)
            if isinstance(text_block, str):
                try:
                    result = json.loads(text_block)
                except json.JSONDecodeError as exc:
                    raise ConnectorError("智能附图 MCP 业务结果不是有效 JSON", error_code="invalid_provider_json") from exc
            if not isinstance(result, Mapping):
                raise ConnectorError("智能附图 MCP 业务结果结构无效", error_code="invalid_provider_payload")
            return result, dict(redact_payload(result))
        finally:
            transport.close()

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
        return self.transport.discover([self.service_name])

    def _call(self, tool_key: str, arguments: dict[str, Any]) -> tuple[Any, dict[str, Any]]:
        tool = self.tools.get(tool_key, tool_key)
        raw = self.transport.call_tool(self.service_name, tool, arguments)
        result = raw.get("structuredContent") if isinstance(raw, Mapping) else raw
        if not isinstance(result, Mapping):
            result = raw
        text_block = next((item.get("text") for item in (result.get("content", []) if isinstance(result, Mapping) else []) if isinstance(item, Mapping) and item.get("type") == "text"), None)
        if isinstance(text_block, str):
            try:
                result = json.loads(text_block)
            except json.JSONDecodeError as exc:
                raise ConnectorError("PatSnap MCP 业务结果不是有效 JSON", error_code="invalid_provider_json") from exc
        if not isinstance(result, Mapping):
            raise ConnectorError("PatSnap MCP 业务结果结构无效", error_code="invalid_provider_payload")
        success = result.get("success") is True or result.get("status") is True
        if not success or int(result.get("error_code", 0) or 0) != 0:
            raise ConnectorError("PatSnap 业务请求未成功", error_code="provider_business_error", retryable=False)
        return result.get("data"), dict(redact_payload(result))

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
        if not fields and self.config.get("enrich_legal_on_fetch", True):
            fields.add("legal_status")
        payload = dict(record.raw_payload)
        if "claims" in fields:
            value, raw = self._call("claims", {"patent_number": number})
            record = self._with_field(record, "claims", _text(value), payload, raw)
        if "description_full" in fields:
            value, raw = self._call("description", {"patent_number": number})
            record = self._with_field(record, "description_full", _text(value), payload, raw)
        if "family_members" in fields:
            value, raw = self._call("family", {"patent_number": number})
            members = ", ".join(_numbers(value))
            record = self._with_field(record, "family_members", members, payload, raw)
        if "legal_status" in fields or "grant_date" in fields or self.config.get("enrich_legal_status"):
            value, raw = self._call("legal_status", {"patent_number": number})
            status_value = value[0] if isinstance(value, list) and value else value
            status = _status((status_value or {}).get("simple_legal_status") if isinstance(status_value, Mapping) else status_value)
            legal_fields = dict(record.fields)
            legal_fields["legal_status"] = status
            if isinstance(status_value, Mapping):
                grant = _date(status_value.get("grant_date") or status_value.get("grantDate"))
                if grant:
                    legal_fields["grant_date"] = grant
            legal_fields["legal_status_details"] = json.dumps(redact_payload(status_value), ensure_ascii=False, sort_keys=True, default=str)
            event_date = _date(status_value.get("grant_date") if isinstance(status_value, Mapping) else None)
            events = list(record.legal_events)
            if event_date:
                stable = hashlib.sha256(json.dumps(status_value, sort_keys=True, default=str).encode()).hexdigest()[:40]
                events.append(ProviderLegalEvent(f"patsnap:{stable}", "LEGAL_STATUS", event_date, status, legal_fields.get("country"), payload=dict(redact_payload(status_value))))
            record = ProviderPatentRecord(record.external_record_id, record.identifiers, legal_fields, tuple(events), record.source_updated_at, record.source_version, {**payload, "legal_status": raw})
        return record

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
            "ipc_all": redact_payload((b.get("classification_data") or {}).get("classification_ipcr")) if isinstance(b.get("classification_data"), Mapping) else None,
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
        if service_name != self.service_name:
            raise ConnectorError("未知 PatSnap MCP 服务", error_code="unknown_service")
        if tool_name not in READ_ONLY_TOOLS and tool_name not in set(self.tools.values()):
            raise ConnectorError("工具未在只读调用白名单中", error_code="unsupported_tool")
        return self._call(tool_name, arguments)

    def extract_mapped_fields(self, tool_name: str, data: Any, patent_id: str | None = None) -> dict[str, Any]:
        if tool_name == self.tools["bibliography"]:
            row = self._select_row(data, patent_id or "")
            return dict(self._bibliography_record(row, patent_id or "", {}).fields) if isinstance(row, Mapping) else {}
        if tool_name == self.tools["claims"]:
            return {"claims": _text(data), "mcp_claim_metadata": redact_payload(data)} if data else {}
        if tool_name == self.tools["description"]:
            return {"description_full": _text(data), "mcp_description_metadata": redact_payload(data)} if data else {}
        if tool_name == self.tools["family"]:
            return {"family_members": ", ".join(_numbers(data))} if _numbers(data) else {}
        if tool_name == self.tools["legal_status"]:
            row = data[0] if isinstance(data, list) and data else data
            return {"legal_status": _status(row.get("simple_legal_status") if isinstance(row, Mapping) else row)}
        if tool_name == self.tools["legal_data"]:
            return {"legal_status_details": json.dumps(redact_payload(data), ensure_ascii=False, sort_keys=True, default=str)} if data else {}
        return {}
