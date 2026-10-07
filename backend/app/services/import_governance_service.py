"""Shared audit rules for import decisions between differing non-empty values."""
from __future__ import annotations

from datetime import date, datetime
from enum import Enum
import json
from typing import Any

from sqlalchemy.orm import Session

from app.models import ImportFieldGovernanceAudit, Patent


def _storage_value(value: Any) -> Any:
    if isinstance(value, Enum):
        return _storage_value(value.value)
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, dict):
        return {str(key): _storage_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_storage_value(item) for item in value]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)


def _has_content(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, (dict, list, tuple)):
        return bool(value)
    return True


def _comparison_value(value: Any) -> Any:
    value = _storage_value(value)
    if isinstance(value, str):
        stripped = value.strip()
        if stripped.startswith(("[", "{")):
            try:
                parsed = json.loads(stripped)
            except json.JSONDecodeError:
                return stripped
            if isinstance(parsed, (dict, list)):
                return _comparison_value(parsed)
        return stripped
    if isinstance(value, dict):
        return {key: _comparison_value(item) for key, item in sorted(value.items())}
    if isinstance(value, list):
        return [_comparison_value(item) for item in value]
    return value


def record_import_field_change(
    db: Session,
    *,
    patent: Patent,
    field_key: str,
    old_value: Any,
    incoming_value: Any,
    final_value: Any | None = None,
    database_id: int | None = None,
    source_kind: str,
    source_label: str | None = None,
    source_reference: str | None = None,
    import_batch_id: int | None = None,
    source_row: int | None = None,
    source_field_name: str | None = None,
    resolution: str = "use_incoming",
    decided_by: str | None = None,
    reason: str | None = None,
) -> ImportFieldGovernanceAudit | None:
    """Record a choice only when old and incoming values are both present and differ."""
    if not _has_content(old_value) or not _has_content(incoming_value):
        return None
    if _comparison_value(old_value) == _comparison_value(incoming_value):
        return None
    record = ImportFieldGovernanceAudit(
        patent_id=patent.id,
        patent_uid=patent.entity_uid,
        patent_title=patent.title,
        application_number=patent.application_number,
        publication_number=patent.publication_number,
        database_id=database_id if database_id is not None else patent.database_id,
        field_key=field_key,
        old_value=_storage_value(old_value),
        incoming_value=_storage_value(incoming_value),
        final_value=_storage_value(incoming_value if final_value is None else final_value),
        source_kind=source_kind,
        source_label=source_label,
        source_reference=source_reference,
        import_batch_id=import_batch_id,
        source_row=source_row,
        source_field_name=source_field_name,
        resolution=resolution,
        decided_by=decided_by,
        reason=reason,
    )
    db.add(record)
    return record
