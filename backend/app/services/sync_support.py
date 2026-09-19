"""Shared synchronization policy values and serialization helpers."""
from __future__ import annotations

from datetime import date, datetime
import hashlib
import json
from typing import Any

from app.core.time import utc_now_naive


SAFE_EXTERNAL_FIELDS = {
    "application_number", "publication_number", "grant_number", "title", "abstract",
    "applicant", "inventor", "assignee", "agent", "filing_date", "publication_date",
    "grant_date", "priority_date", "priority_number", "priority_country", "country",
    "ipc_main", "ipc_all", "cpc_main", "cpc_all",
}

LEGAL_STATUS_MAP = {
    "pending": "pending", "published": "published", "examining": "examining",
    "granted": "granted", "rejected": "rejected", "withdrawn": "withdrawn",
    "deemed_withdrawn": "deemed_withdrawn", "expired": "expired",
    "abandoned": "abandoned", "unknown": "unknown",
}


def hash_payload(payload: Any) -> str:
    body = json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str).encode("utf-8")
    return hashlib.sha256(body).hexdigest()


def serialize_value(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if hasattr(value, "value"):
        return str(value.value)
    if isinstance(value, (dict, list, tuple)):
        return json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)
    return str(value)


def date_value(value: Any) -> date | None:
    if value is None or value == "":
        return None
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value)[:10])


def now() -> datetime:
    return utc_now_naive()
