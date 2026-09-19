"""Configuration-driven REST/JSON patent connector.

The connector only performs transport, response extraction and normalization.
It deliberately has no SQLAlchemy dependency and cannot write PatWiki
business entities.  Provider-specific behavior belongs in the connector
configuration: request paths, parameter templates, response paths and field
maps are all explicit JSON values.
"""
from __future__ import annotations

from dataclasses import asdict
from datetime import date, datetime, timezone
from email.utils import parsedate_to_datetime
import hashlib
import json
import re
import time
from typing import Any, Callable, Mapping
from urllib.parse import urljoin, urlparse

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
from app.integrations.credentials import CredentialStoreError, resolve_credential_ref


_TEMPLATE = re.compile(r"^\{\{\s*([^{}]+?)\s*\}\}$")
_EMBEDDED_TEMPLATE = re.compile(r"\{\{\s*([^{}]+?)\s*\}\}")
_SENSITIVE_KEYS = {
    "authorization",
    "api_key",
    "x_api_key",
    "apikey",
    "access_token",
    "refresh_token",
    "password",
    "cookie",
    "set-cookie",
    "secret",
    "token",
    "client_secret",
}


def _contains_inline_secret(value: Any, *, parent_key: str = "") -> bool:
    key = parent_key.casefold().replace("-", "_")
    if key in _SENSITIVE_KEYS and key not in {"credential_ref"}:
        return True
    if isinstance(value, Mapping):
        return any(_contains_inline_secret(item, parent_key=str(name)) for name, item in value.items())
    if isinstance(value, list):
        return any(_contains_inline_secret(item, parent_key=parent_key) for item in value)
    return False


def _path_get(value: Any, path: str | None, default: Any = None) -> Any:
    if path is None or path == "":
        return value
    current = value
    normalized = str(path).strip()
    if normalized.startswith("$"):
        normalized = normalized[1:].lstrip(".")
    tokens = [item for item in re.split(r"\.|\[|\]", normalized) if item != ""]
    for token in tokens:
        if isinstance(current, Mapping):
            if token not in current:
                return default
            current = current[token]
        elif isinstance(current, (list, tuple)) and token.isdigit():
            index = int(token)
            if index >= len(current):
                return default
            current = current[index]
        else:
            return default
    return current


def _redact(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {
            str(key): "[REDACTED]" if str(key).casefold() in _SENSITIVE_KEYS else _redact(item)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [_redact(item) for item in value]
    return value


def _parse_datetime(value: Any) -> datetime | None:
    if value in (None, ""):
        return None
    if isinstance(value, datetime):
        parsed = value
    else:
        text = str(value).strip().replace("Z", "+00:00")
        try:
            parsed = datetime.fromisoformat(text)
        except ValueError:
            try:
                parsed = datetime.combine(date.fromisoformat(text), datetime.min.time())
            except ValueError as exc:
                raise ConnectorError("供应商日期无法解析", error_code="invalid_date") from exc
    if parsed.tzinfo:
        parsed = parsed.astimezone(timezone.utc).replace(tzinfo=None)
    return parsed


def _parse_date(value: Any) -> date:
    parsed = _parse_datetime(value)
    if parsed is None:
        raise ConnectorError("法律事件缺少事件日期", error_code="invalid_legal_event")
    return parsed.date()


class RestJsonConnector(PatentConnector):
    """Map a conventional REST/JSON API to the PatWiki connector contract."""

    def __init__(
        self,
        config: dict[str, Any] | None = None,
        *,
        endpoint: str | None = None,
        credential_ref: str | None = None,
        credential_value: str | None = None,
        client: httpx.Client | None = None,
        sleeper: Callable[[float], None] | None = None,
    ):
        self.config = config or {}
        if _contains_inline_secret(self.config):
            raise ConnectorError("REST Connector 禁止在普通配置中保存明文凭证", error_code="inline_credential_forbidden")
        self.endpoint = (endpoint or self.config.get("endpoint") or "").strip().rstrip("/")
        self._validate_endpoint()
        self.credential_ref = credential_ref or self._auth_config().get("credential_ref")
        self.credential_value = credential_value
        if client is None:
            timeout_seconds = float(self.config.get("timeout_seconds", 30))
            if timeout_seconds <= 0:
                raise ConnectorError("REST Connector timeout_seconds 必须大于 0", error_code="invalid_timeout")
            self.client = httpx.Client(
                follow_redirects=False,
                timeout=httpx.Timeout(timeout_seconds),
            )
            self._owns_client = True
        else:
            self.client = client
            self._owns_client = False
        self.sleeper = sleeper or time.sleep

    def close(self) -> None:
        if self._owns_client:
            self.client.close()

    def _validate_endpoint(self) -> None:
        if not self.endpoint:
            raise ConnectorError("REST Connector 未配置 endpoint", error_code="missing_endpoint")
        parsed = urlparse(self.endpoint)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ConnectorError("REST Connector endpoint 必须是 http(s) URL", error_code="invalid_endpoint")

    def _auth_config(self) -> dict[str, Any]:
        return dict(self.config.get("auth") or {})

    def capabilities(self) -> ConnectorCapabilities:
        values = dict(self.config.get("capabilities") or {})
        return ConnectorCapabilities(
            search=bool(values.get("search", True)),
            fetch_patent=bool(values.get("fetch_patent", True)),
            legal_events=bool(values.get("legal_events", True)),
            webhooks=bool(values.get("webhooks", False)),
            cursor_pagination=bool(values.get("cursor_pagination", True)),
            updated_since=bool(values.get("updated_since", False)),
        )

    def healthcheck(self) -> ConnectorHealth:
        spec = self.config.get("healthcheck")
        if not spec:
            return ConnectorHealth(status="configured", message="REST Connector 配置有效")
        started = time.monotonic()
        self._request(dict(spec), {"query": {}, "cursor": None, "limit": 1})
        return ConnectorHealth(status="ok", message="REST Connector healthcheck succeeded", latency_ms=int((time.monotonic() - started) * 1000))

    def search(self, query: CanonicalPatentQuery, cursor: str | None, limit: int) -> SearchPage:
        spec = dict(self.config.get("search") or {})
        if not spec:
            raise ConnectorError("REST Connector 未配置 search 映射", error_code="missing_search_config")
        context = self._context(query=query, cursor=cursor, limit=limit)
        payload = self._request(spec, context)
        response_config = dict(spec.get("response") or self.config.get("response") or {})
        records_payload = _path_get(payload, response_config.get("records_path"), payload)
        if not isinstance(records_payload, list):
            raise ConnectorError("search 响应 records_path 不是数组", error_code="invalid_response_shape")
        records = tuple(self._map_record(item) for item in records_payload if isinstance(item, Mapping))
        next_cursor = _path_get(payload, response_config.get("next_cursor_path"))
        watermark = _parse_datetime(_path_get(payload, response_config.get("watermark_path")))
        source_version = _path_get(payload, response_config.get("source_version_path"))
        return SearchPage(
            records=records,
            next_cursor=str(next_cursor) if next_cursor not in (None, "") else None,
            watermark=watermark,
            source_version=str(source_version) if source_version not in (None, "") else None,
        )

    def fetch_patent(self, identifier: ProviderIdentifier) -> ProviderPatentRecord:
        spec = dict(self.config.get("fetch") or {})
        if not spec:
            raise ConnectorError("REST Connector 未配置 fetch 映射", error_code="missing_fetch_config")
        context = self._context(identifier=identifier, query=CanonicalPatentQuery())
        payload = self._request(spec, context)
        response_config = dict(spec.get("response") or {})
        record_payload = _path_get(payload, response_config.get("record_path"), payload)
        if not isinstance(record_payload, Mapping):
            raise ConnectorError("fetch 响应 record_path 不是对象", error_code="invalid_response_shape")
        return self._map_record(record_payload)

    def _context(self, *, query: CanonicalPatentQuery | None = None, cursor: str | None = None, limit: int | None = None, identifier: ProviderIdentifier | None = None) -> dict[str, Any]:
        query_values = asdict(query or CanonicalPatentQuery())
        extra = query_values.pop("extra", {}) or {}
        query_values.update(extra)
        return {
            "query": query_values,
            "cursor": cursor,
            "limit": limit,
            "identifier": asdict(identifier) if identifier else {},
        }

    def _render(self, value: Any, context: dict[str, Any]) -> Any:
        if isinstance(value, Mapping):
            return {key: self._render(item, context) for key, item in value.items()}
        if isinstance(value, list):
            return [self._render(item, context) for item in value]
        if not isinstance(value, str):
            return value
        exact = _TEMPLATE.match(value)
        if exact:
            return _path_get(context, exact.group(1).strip())
        return _EMBEDDED_TEMPLATE.sub(lambda match: str(_path_get(context, match.group(1).strip(), "")), value)

    def _request(self, spec: dict[str, Any], context: dict[str, Any]) -> Any:
        method = str(spec.get("method", "GET")).upper()
        path = self._render(spec.get("path", ""), context)
        url = self._url(str(path or ""))
        headers = dict(self.config.get("headers") or {})
        headers.update(spec.get("headers") or {})
        headers = self._render(headers, context)
        headers.update(self._auth_headers())
        params = self._render(spec.get("params") or {}, context)
        body = self._render(spec.get("body"), context)
        if body is None and method not in {"GET", "HEAD"} and spec.get("json") is not None:
            body = self._render(spec.get("json"), context)
        attempts = max(1, int((self.config.get("retry") or {}).get("max_attempts", 3)))
        for attempt in range(1, attempts + 1):
            try:
                response = self.client.request(method, url, params=params, json=body, headers=headers)
            except (httpx.TimeoutException, httpx.TransportError) as exc:
                if attempt < attempts:
                    self._wait(None, attempt)
                    continue
                raise ConnectorError("供应商请求失败", error_code="transport_error", retryable=True) from exc
            if response.status_code in {408, 425, 429, 500, 502, 503, 504}:
                retry_after = self._retry_after(response)
                if attempt < attempts:
                    self._wait(retry_after, attempt)
                    continue
                raise ConnectorError("供应商暂时不可用", error_code="http_retryable", retryable=True, status_code=response.status_code, retry_after=retry_after)
            if response.status_code in {401, 403}:
                raise ConnectorError("供应商认证或权限失败", error_code="authentication_error", status_code=response.status_code)
            if 300 <= response.status_code < 400:
                raise ConnectorError("供应商响应包含不允许的重定向", error_code="redirect_not_allowed", status_code=response.status_code)
            if response.status_code >= 400:
                raise ConnectorError("供应商请求参数或资源错误", error_code="http_permanent", status_code=response.status_code)
            try:
                return response.json()
            except (ValueError, json.JSONDecodeError) as exc:
                raise ConnectorError("供应商响应不是有效 JSON", error_code="invalid_json", status_code=response.status_code) from exc
        raise ConnectorError("供应商请求失败", error_code="request_exhausted", retryable=True)

    def _url(self, path: str) -> str:
        if not path:
            return self.endpoint
        parsed = urlparse(path)
        if parsed.scheme:
            endpoint_parts = urlparse(self.endpoint)
            if parsed.scheme != endpoint_parts.scheme or parsed.netloc != endpoint_parts.netloc:
                raise ConnectorError("请求路径不得跳转到其他主机", error_code="invalid_request_url")
            return path
        return urljoin(f"{self.endpoint}/", path.lstrip("/"))

    def _auth_headers(self) -> dict[str, str]:
        auth = self._auth_config()
        if not auth:
            return {}
        value = self.credential_value
        if value is None:
            try:
                value = resolve_credential_ref(self.credential_ref)
            except CredentialStoreError as exc:
                raise ConnectorError("连接器凭证不可用", error_code="credential_unavailable") from exc
        if not value:
            if auth.get("required", True):
                raise ConnectorError("连接器缺少凭证", error_code="credential_missing")
            return {}
        auth_type = str(auth.get("type", "bearer")).casefold()
        header = str(auth.get("header", "Authorization"))
        if auth_type == "bearer":
            return {header: f"Bearer {value}"}
        if auth_type in {"api_key", "apikey"}:
            return {header if header != "Authorization" else "X-API-Key": value}
        if auth_type == "basic":
            return {header: f"Basic {value}"}
        raise ConnectorError("不支持的 REST 认证类型", error_code="unsupported_auth")

    def _wait(self, retry_after: float | None, attempt: int) -> None:
        retry = self.config.get("retry") or {}
        maximum = float(retry.get("max_delay_seconds", 30))
        base = float(retry_after if retry_after is not None else retry.get("backoff_seconds", 0.5) * (2 ** (attempt - 1)))
        self.sleeper(max(0.0, min(maximum, base)))

    @staticmethod
    def _retry_after(response: httpx.Response) -> float | None:
        value = response.headers.get("Retry-After")
        if not value:
            return None
        try:
            return max(0.0, float(value))
        except ValueError:
            try:
                target = parsedate_to_datetime(value)
                if target.tzinfo is None:
                    target = target.replace(tzinfo=timezone.utc)
                return max(0.0, target.timestamp() - time.time())
            except (TypeError, ValueError, OverflowError):
                return None

    def _map_value(self, payload: Mapping[str, Any], spec: Any, *, default: Any = None) -> Any:
        if spec is None:
            return default
        if isinstance(spec, Mapping):
            if "value" in spec:
                return spec["value"]
            return _path_get(payload, spec.get("path"), spec.get("default", default))
        return _path_get(payload, spec, default)

    def _map_record(self, payload: Mapping[str, Any]) -> ProviderPatentRecord:
        mapping = dict(self.config.get("record") or {})
        external_id = self._map_value(payload, mapping.get("external_record_id", "external_record_id"))
        if external_id in (None, ""):
            external_id = self._map_value(payload, "id")
        if external_id in (None, ""):
            external_id = hashlib.sha256(json.dumps(_redact(payload), ensure_ascii=False, sort_keys=True, default=str).encode("utf-8")).hexdigest()
        identifiers = []
        for identifier_spec in mapping.get("identifiers", []):
            spec = dict(identifier_spec)
            raw_value = self._map_value(payload, spec.get("raw_value_path", spec.get("raw_value")))
            if raw_value in (None, ""):
                continue
            identifiers.append(ProviderIdentifier(
                identifier_type=str(spec.get("identifier_type", "publication")),
                raw_value=str(raw_value),
                jurisdiction_code=self._string_value(payload, spec.get("jurisdiction_code_path", spec.get("jurisdiction_code"))),
                kind_code=self._string_value(payload, spec.get("kind_code_path", spec.get("kind_code"))),
                identifier_namespace=str(spec.get("identifier_namespace", "official")),
            ))
        fields = {}
        for canonical_key, field_spec in (mapping.get("fields") or {}).items():
            value = self._map_value(payload, field_spec)
            if value is not None:
                fields[str(canonical_key)] = value
        events = []
        event_config = dict(mapping.get("legal_events") or {})
        events_payload = self._map_value(payload, event_config.get("path")) if event_config.get("path") else []
        if events_payload is None:
            events_payload = []
        if not isinstance(events_payload, list):
            raise ConnectorError("legal_events path 不是数组", error_code="invalid_response_shape")
        for item in events_payload:
            if not isinstance(item, Mapping):
                continue
            event_id = self._map_value(item, event_config.get("provider_event_id_path", "id"))
            event_date = self._map_value(item, event_config.get("event_date_path", "event_date"))
            if event_id in (None, "") or event_date in (None, ""):
                raise ConnectorError("法律事件缺少稳定 ID 或日期", error_code="invalid_legal_event")
            events.append(ProviderLegalEvent(
                provider_event_id=str(event_id),
                event_code=str(self._map_value(item, event_config.get("event_code_path", "event_code"), default="UNKNOWN")),
                event_date=_parse_date(event_date),
                status=str(self._map_value(item, event_config.get("status_path", "status"), default="unknown")),
                jurisdiction_code=self._string_value(item, event_config.get("jurisdiction_code_path")),
                raw_description=self._string_value(item, event_config.get("raw_description_path")),
                payload=dict(_redact(item)),
            ))
        source_updated_at = _parse_datetime(self._map_value(payload, mapping.get("source_updated_at_path")))
        source_version = self._string_value(payload, mapping.get("source_version_path"))
        return ProviderPatentRecord(
            external_record_id=str(external_id),
            identifiers=tuple(identifiers),
            fields=fields,
            legal_events=tuple(events),
            source_updated_at=source_updated_at,
            source_version=source_version,
            raw_payload=dict(_redact(payload)),
        )

    def _string_value(self, payload: Mapping[str, Any], spec: Any) -> str | None:
        if spec is None:
            return None
        value = self._map_value(payload, spec)
        return None if value in (None, "") else str(value)
