"""Runtime connector registry.

The registry is the only place where provider implementations are selected;
sync orchestration depends on the contract, not provider modules.
"""
from __future__ import annotations

from typing import Any

from app.models import ConnectorDefinition


def get_connector(definition: ConnectorDefinition):
    if definition.provider_type == "demo":
        from app.integrations.demo import DemoConnector
        return DemoConnector(definition.config_json or {})
    if definition.provider_type in {"rest_json", "generic_json"}:
        from app.integrations.rest_json import RestJsonConnector
        config = definition.config_json or {}
        auth = config.get("auth") or {}
        selected_credential = None
        credential_id = auth.get("credential_id")
        for credential in getattr(definition, "credentials", []) or []:
            if credential_id is None or credential.id == credential_id:
                selected_credential = credential
                break
        return RestJsonConnector(
            config,
            endpoint=definition.endpoint,
            credential_ref=(selected_credential.credential_ref if selected_credential else auth.get("credential_ref")),
        )
    if definition.provider_type in {"himmpat_mcp", "mcp_himmpat"}:
        from app.integrations.himmpat import HimmPatMcpAdapter
        config = definition.config_json or {}
        auth = config.get("auth") or {}
        selected_credential = None
        credential_id = auth.get("credential_id")
        for credential in getattr(definition, "credentials", []) or []:
            if credential_id is None or credential.id == credential_id:
                selected_credential = credential
                break
        return HimmPatMcpAdapter(
            config,
            endpoint=definition.endpoint,
            credential_ref=(selected_credential.credential_ref if selected_credential else auth.get("credential_ref") or config.get("credential_ref")),
        )
    if definition.provider_type in {"mcp_readonly", "mcp_standard"} and definition.transport == "mcp":
        from app.integrations.mcp_readonly import McpTransportReadonlyConnector
        from app.integrations.demo import record_from_payload
        from app.integrations.mcp_transport import McpTransport
        config = definition.config_json or {}
        auth = config.get("auth") or {}
        selected_credential = None
        credential_id = auth.get("credential_id")
        for credential in getattr(definition, "credentials", []) or []:
            if credential_id is None or credential.id == credential_id:
                selected_credential = credential
                break
        mcp_transport = McpTransport(
            definition.endpoint or config.get("endpoint") or "",
            credential_ref=(selected_credential.credential_ref if selected_credential else auth.get("credential_ref") or config.get("credential_ref")),
            credential_value=auth.get("credential_value") or config.get("credential_value"),
            service_path_template=str(config.get("service_path_template", "/mcp/{service_name}")),
            protocol_version=str(config.get("protocol_version", "2025-06-18")),
            timeout_seconds=float(config.get("timeout_seconds", 30)),
            retry_config=dict(config.get("retry") or {}),
        )
        tools = dict(config.get("tools") or {})
        response_config = dict(config.get("response") or {})
        return McpTransportReadonlyConnector(
            mcp_transport,
            service_name=str(config.get("service_name") or "default"),
            record_mapper=record_from_payload,
            search_tool=tools.get("search", "search_patents"),
            fetch_tool=tools.get("fetch", "get_patent"),
            health_tool=tools.get("health"),
            response_config=response_config,
        )
    if definition.transport == "mcp":
        raise ValueError(f"unsupported MCP provider_type: {definition.provider_type}")
    raise ValueError(f"unsupported connector provider_type: {definition.provider_type}")
