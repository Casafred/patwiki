"""Provider-neutral external data connector contracts."""

from app.integrations.contracts import (
    ConnectorCapabilities,
    ConnectorHealth,
    ConnectorError,
    CanonicalPatentQuery,
    ProviderIdentifier,
    ProviderLegalEvent,
    ProviderPatentRecord,
    SearchPage,
    PatentConnector,
)
from app.integrations.rest_json import RestJsonConnector
from app.integrations.mcp_readonly import McpReadonlyConnector
from app.integrations.registry import get_connector

__all__ = [
    "ConnectorCapabilities",
    "ConnectorHealth",
    "ConnectorError",
    "CanonicalPatentQuery",
    "ProviderIdentifier",
    "ProviderLegalEvent",
    "ProviderPatentRecord",
    "SearchPage",
    "PatentConnector",
    "RestJsonConnector",
    "McpReadonlyConnector",
    "get_connector",
]
