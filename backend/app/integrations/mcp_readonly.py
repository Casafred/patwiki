"""Read-only MCP adapter slot for patent providers.

The application does not depend on a particular MCP SDK.  A host supplies a
small ``call_tool`` function, while this adapter enforces the same read-only
Connector contract used by REST providers.  Only configured search, fetch and
health tool names can be called; there is intentionally no generic write or
SQL passthrough.
"""
from __future__ import annotations

from dataclasses import asdict
from datetime import datetime
from typing import Any, Callable, Mapping, Protocol

from app.integrations.contracts import (
    CanonicalPatentQuery,
    ConnectorCapabilities,
    ConnectorError,
    ConnectorHealth,
    PatentConnector,
    ProviderIdentifier,
    ProviderPatentRecord,
    SearchPage,
)


class McpToolCaller(Protocol):
    def __call__(self, tool_name: str, arguments: dict[str, Any]) -> Any: ...


class McpReadonlyConnector(PatentConnector):
    """Adapt fixed, read-only MCP tools to ``PatentConnector``."""

    def __init__(
        self,
        call_tool: McpToolCaller,
        *,
        record_mapper: Callable[[Mapping[str, Any]], ProviderPatentRecord] | None = None,
        search_tool: str = "search_patents",
        fetch_tool: str = "get_patent",
        health_tool: str | None = None,
        response_config: dict[str, Any] | None = None,
    ):
        self.call_tool = call_tool
        self.record_mapper = record_mapper
        self.search_tool = search_tool
        self.fetch_tool = fetch_tool
        self.health_tool = health_tool
        self.response_config = response_config or {}

    def capabilities(self) -> ConnectorCapabilities:
        return ConnectorCapabilities(
            search=bool(self.search_tool),
            fetch_patent=bool(self.fetch_tool),
            legal_events=True,
            cursor_pagination=True,
        )

    def healthcheck(self) -> ConnectorHealth:
        if not self.health_tool:
            return ConnectorHealth(status="configured", message="MCP 只读工具已注册")
        payload = self._call(self.health_tool, {})
        status = str(payload.get("status", "ok")) if isinstance(payload, Mapping) else "ok"
        return ConnectorHealth(status=status, message="MCP 只读 healthcheck succeeded")

    def search(self, query: CanonicalPatentQuery, cursor: str | None, limit: int) -> SearchPage:
        if not self.search_tool:
            raise ConnectorError("MCP Connector 未配置搜索工具", error_code="missing_search_tool")
        payload = self._call(self.search_tool, {
            "query": asdict(query),
            "cursor": cursor,
            "limit": limit,
        })
        records_payload = self._path(payload, self.response_config.get("records_path"), payload)
        if not isinstance(records_payload, list):
            raise ConnectorError("MCP 搜索结果不是数组", error_code="invalid_response_shape")
        records = tuple(self._record(item) for item in records_payload)
        next_cursor = self._path(payload, self.response_config.get("next_cursor_path"))
        watermark_value = self._path(payload, self.response_config.get("watermark_path"))
        watermark = self._parse_datetime(watermark_value)
        source_version = self._path(payload, self.response_config.get("source_version_path"))
        return SearchPage(
            records=records,
            next_cursor=str(next_cursor) if next_cursor not in (None, "") else None,
            watermark=watermark,
            source_version=str(source_version) if source_version not in (None, "") else None,
        )

    def fetch_patent(self, identifier: ProviderIdentifier) -> ProviderPatentRecord:
        if not self.fetch_tool:
            raise ConnectorError("MCP Connector 未配置单件抓取工具", error_code="missing_fetch_tool")
        payload = self._call(self.fetch_tool, {"identifier": asdict(identifier)})
        record_payload = self._path(payload, self.response_config.get("record_path"), payload)
        if not isinstance(record_payload, Mapping):
            raise ConnectorError("MCP 单件结果不是对象", error_code="invalid_response_shape")
        return self._record(record_payload)

    def _call(self, tool_name: str, arguments: dict[str, Any]) -> Any:
        try:
            result = self.call_tool(tool_name, arguments)
        except Exception as exc:
            raise ConnectorError("MCP 只读工具调用失败", error_code="mcp_tool_error", retryable=True) from exc
        if isinstance(result, Mapping) and "structuredContent" in result:
            result = result["structuredContent"]
        if isinstance(result, Mapping) and result.get("isError"):
            raise ConnectorError("MCP 只读工具返回错误", error_code="mcp_tool_error", retryable=False)
        return result

    def _record(self, value: Any) -> ProviderPatentRecord:
        if isinstance(value, ProviderPatentRecord):
            return value
        if not isinstance(value, Mapping) or self.record_mapper is None:
            raise ConnectorError("MCP 返回未经过统一专利记录映射", error_code="unmapped_mcp_record")
        try:
            record = self.record_mapper(value)
        except ConnectorError:
            raise
        except Exception as exc:
            raise ConnectorError("MCP 专利记录映射失败", error_code="invalid_record") from exc
        if not isinstance(record, ProviderPatentRecord):
            raise ConnectorError("MCP 记录映射器必须返回 ProviderPatentRecord", error_code="invalid_record_mapper")
        return record

    @staticmethod
    def _path(value: Any, path: str | None, default: Any = None) -> Any:
        if not path:
            return default
        current = value
        for token in [part for part in str(path).replace("[", ".").replace("]", "").split(".") if part]:
            if isinstance(current, Mapping):
                current = current.get(token, default)
            elif isinstance(current, list) and token.isdigit() and int(token) < len(current):
                current = current[int(token)]
            else:
                return default
        return current

    @staticmethod
    def _parse_datetime(value: Any) -> datetime | None:
        if value in (None, ""):
            return None
        try:
            return datetime.fromisoformat(str(value).replace("Z", "+00:00")).replace(tzinfo=None)
        except ValueError as exc:
            raise ConnectorError("MCP 水位日期无法解析", error_code="invalid_date") from exc
