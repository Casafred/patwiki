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
    raise ValueError(f"unsupported connector provider_type: {definition.provider_type}")
