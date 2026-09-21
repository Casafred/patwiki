"""Provider-neutral JSON-RPC MCP transport.

The transport owns protocol concerns only: endpoint construction, credential
resolution, initialize/session handling, tool discovery and tool calls.  It
does not know patent fields or any provider business response format.
"""
from __future__ import annotations

import json
import time
from collections.abc import Mapping
from typing import Any, Callable
from urllib.parse import urlparse

import httpx

from app.integrations.contracts import ConnectorError
from app.integrations.credentials import CredentialStoreError, resolve_credential_ref


SENSITIVE_KEYS = {
    "authorization", "api_key", "apikey", "access_token", "refresh_token",
    "password", "cookie", "set-cookie", "secret", "token", "client_secret",
}


def redact_payload(value: Any) -> Any:
    """Return a JSON-safe payload with credential-like values removed."""
    if isinstance(value, Mapping):
        return {
            str(key): "[REDACTED]" if str(key).casefold().replace("-", "_") in SENSITIVE_KEYS else redact_payload(item)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [redact_payload(item) for item in value]
    if isinstance(value, tuple):
        return [redact_payload(item) for item in value]
    return value


def _decode_response(response: httpx.Response) -> dict[str, Any]:
    """Decode JSON MCP responses and the SSE-style fallback used by some hosts."""
    try:
        payload = response.json()
    except (ValueError, json.JSONDecodeError):
        payload = None
        for line in response.text.splitlines():
            if line.startswith("data:"):
                candidate = line[5:].strip()
                if not candidate or candidate == "[DONE]":
                    continue
                try:
                    payload = json.loads(candidate)
                    break
                except json.JSONDecodeError:
                    continue
    if not isinstance(payload, dict):
        raise ConnectorError("MCP 响应不是有效 JSON", error_code="mcp_invalid_json")
    return payload


class McpTransport:
    """Small synchronous MCP client suitable for the local sync scheduler."""

    def __init__(
        self,
        endpoint: str,
        *,
        credential_ref: str | None = None,
        credential_value: str | None = None,
        service_path_template: str | None = "/api/service/himmuc_api/mcp/{service_name}",
        protocol_version: str = "2025-06-18",
        client_name: str = "patwiki",
        client_version: str = "0.1.0",
        timeout_seconds: float = 30,
        retry_config: dict[str, Any] | None = None,
        client: httpx.Client | None = None,
        sleeper: Callable[[float], None] | None = None,
    ):
        self.endpoint = endpoint.strip().rstrip("/")
        parsed = urlparse(self.endpoint)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ConnectorError("MCP endpoint 必须是 http(s) URL", error_code="invalid_mcp_endpoint")
        if service_path_template and "{service_name}" not in service_path_template:
            raise ConnectorError("MCP service_path_template 缺少 service_name", error_code="invalid_mcp_service_path")
        if timeout_seconds <= 0:
            raise ConnectorError("MCP timeout_seconds 必须大于 0", error_code="invalid_timeout")
        self.credential_ref = credential_ref
        self.credential_value = credential_value
        self.service_path_template = service_path_template
        self.protocol_version = protocol_version
        self.client_name = client_name
        self.client_version = client_version
        self.retry_config = retry_config or {}
        self.client = client or httpx.Client(
            follow_redirects=False,
            timeout=httpx.Timeout(timeout_seconds),
        )
        self._owns_client = client is None
        self.sleeper = sleeper or time.sleep
        self._sessions: dict[str, str | None] = {}
        self._request_id = 0

    def close(self) -> None:
        if self._owns_client:
            self.client.close()

    def service_endpoint(self, service_name: str) -> str:
        # The provider may give a complete streamable-HTTP endpoint. In that
        # mode the endpoint is already scoped to one MCP service and must not
        # have another service path appended to it.
        if not self.service_path_template:
            return self.endpoint
        path = self.service_path_template.format(service_name=service_name.strip())
        parsed = urlparse(path)
        if parsed.scheme:
            if parsed.scheme != urlparse(self.endpoint).scheme or parsed.netloc != urlparse(self.endpoint).netloc:
                raise ConnectorError("MCP service endpoint 不得跳转到其他主机", error_code="invalid_mcp_endpoint")
            return path
        return f"{self.endpoint}/{path.lstrip('/')}"

    def initialize(self, service_name: str) -> str | None:
        payload, response = self._request(service_name, "initialize", {
            "protocolVersion": self.protocol_version,
            "capabilities": {},
            "clientInfo": {"name": self.client_name, "version": self.client_version},
        }, session_id=None)
        result = payload.get("result")
        if not isinstance(result, Mapping):
            raise ConnectorError("MCP initialize 返回结构无效", error_code="mcp_invalid_initialize")
        session_id = response.headers.get("Mcp-Session-Id")
        self._sessions[service_name] = session_id
        return session_id

    def _session(self, service_name: str) -> str | None:
        if service_name not in self._sessions:
            return self.initialize(service_name)
        return self._sessions[service_name]

    def list_tools(self, service_name: str) -> list[dict[str, Any]]:
        payload, _ = self._request(service_name, "tools/list", {}, session_id=self._session(service_name))
        result = payload.get("result")
        tools = result.get("tools") if isinstance(result, Mapping) else None
        if not isinstance(tools, list):
            raise ConnectorError("MCP tools/list 返回结构无效", error_code="mcp_invalid_tools")
        return [dict(item) for item in tools if isinstance(item, Mapping)]

    def call_tool(self, service_name: str, tool_name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        payload, _ = self._request(service_name, "tools/call", {
            "name": tool_name,
            "arguments": arguments,
        }, session_id=self._session(service_name))
        result = payload.get("result")
        if not isinstance(result, Mapping):
            raise ConnectorError("MCP tools/call 返回结构无效", error_code="mcp_invalid_tool_result")
        if result.get("isError"):
            raise ConnectorError("MCP 工具返回错误", error_code="mcp_tool_error", retryable=False)
        return dict(result)

    def discover(self, services: list[str]) -> dict[str, Any]:
        discovered = []
        for service_name in services:
            started = time.monotonic()
            tools = self.list_tools(service_name)
            discovered.append({
                "service": service_name,
                "status": "ok",
                "tool_count": len(tools),
                "latency_ms": int((time.monotonic() - started) * 1000),
                "tools": redact_payload(tools),
            })
        return {"services": discovered, "protocol_version": self.protocol_version}

    def _headers(self, session_id: str | None) -> dict[str, str]:
        value = self.credential_value
        if value is None:
            try:
                value = resolve_credential_ref(self.credential_ref)
            except CredentialStoreError as exc:
                raise ConnectorError("MCP 连接器凭证不可用", error_code="credential_unavailable") from exc
        if not value:
            raise ConnectorError("MCP 连接器缺少凭证", error_code="credential_missing")
        headers = {
            "Authorization": f"Bearer {value}",
            "Accept": "application/json, text/event-stream",
            "Content-Type": "application/json",
            "MCP-Protocol-Version": self.protocol_version,
        }
        if session_id:
            headers["Mcp-Session-Id"] = session_id
        return headers

    def _request(
        self,
        service_name: str,
        method: str,
        params: dict[str, Any],
        *,
        session_id: str | None,
    ) -> tuple[dict[str, Any], httpx.Response]:
        self._request_id += 1
        body = {"jsonrpc": "2.0", "id": self._request_id, "method": method, "params": params}
        attempts = max(1, int(self.retry_config.get("max_attempts", 2)))
        for attempt in range(1, attempts + 1):
            try:
                response = self.client.post(
                    self.service_endpoint(service_name),
                    headers=self._headers(session_id),
                    json=body,
                )
            except (httpx.TimeoutException, httpx.TransportError) as exc:
                if attempt < attempts:
                    self._wait(attempt)
                    continue
                raise ConnectorError("MCP 供应商请求失败", error_code="mcp_transport_error", retryable=True) from exc
            if response.status_code in {408, 425, 429, 500, 502, 503, 504}:
                if attempt < attempts:
                    self._wait(attempt)
                    continue
                raise ConnectorError("MCP 供应商暂时不可用", error_code="mcp_http_retryable", retryable=True, status_code=response.status_code)
            if response.status_code in {401, 403}:
                raise ConnectorError("MCP 供应商认证或权限失败", error_code="mcp_authentication_error", status_code=response.status_code)
            if response.status_code >= 400:
                raise ConnectorError("MCP 供应商请求失败", error_code="mcp_http_error", status_code=response.status_code)
            payload = _decode_response(response)
            if payload.get("error"):
                raise ConnectorError("MCP JSON-RPC 请求失败", error_code="mcp_rpc_error", retryable=False)
            return payload, response
        raise ConnectorError("MCP 供应商请求失败", error_code="mcp_request_exhausted", retryable=True)

    def _wait(self, attempt: int) -> None:
        delay = float(self.retry_config.get("backoff_seconds", 0.2)) * (2 ** (attempt - 1))
        maximum = float(self.retry_config.get("max_delay_seconds", 5))
        self.sleeper(max(0.0, min(maximum, delay)))
