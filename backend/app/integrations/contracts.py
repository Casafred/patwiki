"""Stable contracts shared by API and MCP patent connectors."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import date, datetime
from typing import Any, Protocol


def _json_value(value: Any) -> Any:
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, dict):
        return {str(key): _json_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_value(item) for item in value]
    return value


@dataclass(frozen=True)
class ConnectorCapabilities:
    search: bool = True
    fetch_patent: bool = True
    legal_events: bool = True
    webhooks: bool = False
    cursor_pagination: bool = False
    updated_since: bool = False


@dataclass(frozen=True)
class ConnectorHealth:
    status: str
    message: str = ""
    latency_ms: int | None = None


class ConnectorError(RuntimeError):
    """Provider-neutral error exposed by connector implementations.

    The synchronization service uses ``retryable`` and ``error_code`` to
    decide whether a failed run can be retried.  Connector implementations
    must never expose credentials or authorization headers in the message.
    """

    def __init__(
        self,
        message: str,
        *,
        error_code: str = "connector_error",
        retryable: bool = False,
        status_code: int | None = None,
        retry_after: float | None = None,
    ):
        super().__init__(message)
        self.error_code = error_code
        self.retryable = retryable
        self.status_code = status_code
        self.retry_after = retry_after


@dataclass(frozen=True)
class CanonicalPatentQuery:
    applicant: str | None = None
    expression: str | None = None
    jurisdiction: str | None = None
    published_from: str | None = None
    published_to: str | None = None
    legal_status: list[str] = field(default_factory=list)
    extra: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, payload: dict[str, Any] | None) -> "CanonicalPatentQuery":
        payload = payload or {}
        known_keys = {"applicant", "expression", "jurisdiction", "published_from", "published_to", "legal_status"}
        return cls(
            applicant=payload.get("applicant"),
            expression=payload.get("expression"),
            jurisdiction=payload.get("jurisdiction"),
            published_from=payload.get("published_from"),
            published_to=payload.get("published_to"),
            legal_status=list(payload.get("legal_status") or []),
            extra={key: value for key, value in payload.items() if key not in known_keys},
        )


@dataclass(frozen=True)
class ProviderIdentifier:
    identifier_type: str
    raw_value: str
    jurisdiction_code: str | None = None
    kind_code: str | None = None
    identifier_namespace: str = "official"


@dataclass(frozen=True)
class ProviderLegalEvent:
    provider_event_id: str
    event_code: str
    event_date: date
    status: str = "unknown"
    jurisdiction_code: str | None = None
    raw_description: str | None = None
    payload: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ProviderPatentRecord:
    external_record_id: str
    identifiers: tuple[ProviderIdentifier, ...]
    fields: dict[str, Any] = field(default_factory=dict)
    legal_events: tuple[ProviderLegalEvent, ...] = ()
    source_updated_at: datetime | None = None
    source_version: str | None = None
    raw_payload: dict[str, Any] = field(default_factory=dict)

    def as_payload(self) -> dict[str, Any]:
        return _json_value(asdict(self))


@dataclass(frozen=True)
class SearchPage:
    records: tuple[ProviderPatentRecord, ...]
    next_cursor: str | None = None
    watermark: datetime | None = None
    source_version: str | None = None


class PatentConnector(Protocol):
    def capabilities(self) -> ConnectorCapabilities: ...
    def healthcheck(self) -> ConnectorHealth: ...
    def search(self, query: CanonicalPatentQuery, cursor: str | None, limit: int) -> SearchPage: ...
    def fetch_patent(self, identifier: ProviderIdentifier) -> ProviderPatentRecord: ...
