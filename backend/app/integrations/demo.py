"""Deterministic connector used for local development and contract tests."""
from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any

from app.integrations.contracts import (
    CanonicalPatentQuery,
    ConnectorCapabilities,
    ConnectorHealth,
    PatentConnector,
    ProviderIdentifier,
    ProviderLegalEvent,
    ProviderPatentRecord,
    SearchPage,
)


def record_from_payload(payload: dict[str, Any]) -> ProviderPatentRecord:
    identifiers = tuple(
        ProviderIdentifier(
            identifier_type=str(item["identifier_type"]),
            raw_value=str(item["raw_value"]),
            jurisdiction_code=item.get("jurisdiction_code"),
            kind_code=item.get("kind_code"),
            identifier_namespace=item.get("identifier_namespace", "official"),
        )
        for item in payload.get("identifiers", [])
    )
    events = tuple(
        ProviderLegalEvent(
            provider_event_id=str(item["provider_event_id"]),
            event_code=str(item["event_code"]),
            event_date=date.fromisoformat(str(item["event_date"])),
            status=str(item.get("status", "unknown")),
            jurisdiction_code=item.get("jurisdiction_code"),
            raw_description=item.get("raw_description"),
            payload=item.get("payload", {}),
        )
        for item in payload.get("legal_events", [])
    )
    return ProviderPatentRecord(
        external_record_id=str(payload["external_record_id"]),
        identifiers=identifiers,
        fields=dict(payload.get("fields", {})),
        legal_events=events,
        source_updated_at=datetime.fromisoformat(payload["source_updated_at"]) if payload.get("source_updated_at") else None,
        source_version=payload.get("source_version"),
        raw_payload=payload,
    )


class DemoConnector(PatentConnector):
    def __init__(self, config: dict[str, Any] | None = None):
        self.config = config or {}
        self.records = [record_from_payload(item) for item in self.config.get("records", [])]

    def capabilities(self) -> ConnectorCapabilities:
        return ConnectorCapabilities(cursor_pagination=True, updated_since=True)

    def healthcheck(self) -> ConnectorHealth:
        return ConnectorHealth(status="ok", message="demo connector ready")

    @staticmethod
    def _matches(record: ProviderPatentRecord, query: CanonicalPatentQuery) -> bool:
        fields = record.fields
        if query.applicant and query.applicant.casefold() not in str(fields.get("applicant", "")).casefold():
            return False
        if query.jurisdiction and query.jurisdiction.upper() != str(fields.get("country", "")).upper():
            return False
        expression = (query.expression or "").strip().casefold()
        if expression:
            haystack = " ".join(str(fields.get(key, "")) for key in ("title", "abstract", "applicant", "publication_number")).casefold()
            if expression not in haystack:
                return False
        return True

    def search(self, query: CanonicalPatentQuery, cursor: str | None, limit: int) -> SearchPage:
        candidates = [record for record in self.records if self._matches(record, query)]
        offset = int(cursor or 0)
        page = tuple(candidates[offset:offset + limit])
        next_cursor = str(offset + len(page)) if offset + len(page) < len(candidates) else None
        return SearchPage(
            records=page,
            next_cursor=next_cursor,
            watermark=datetime.now(timezone.utc).replace(tzinfo=None),
            source_version=str(self.config.get("version", "demo-v1")),
        )

    def fetch_patent(self, identifier: ProviderIdentifier) -> ProviderPatentRecord:
        needle = identifier.raw_value.casefold().replace(" ", "")
        for record in self.records:
            if any(item.raw_value.casefold().replace(" ", "") == needle for item in record.identifiers):
                return record
        raise LookupError(f"demo record not found: {identifier.raw_value}")
