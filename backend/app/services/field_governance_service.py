"""Seed and query the 31-source-table field governance baseline."""
from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path
import re
import unicodedata
from typing import Iterable

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models import (
    FieldDefinition,
    FieldRegistrySnapshot,
    SourceFieldMapping,
    SourceTableDefinition,
)


BASELINE_FILENAMES = {
    "tables": "01-01_表格目录.csv",
    "fields": "02-02_字段逐项盘点.csv",
    "concepts": "03-03_归一化字段字典.csv",
    "metadata": "10-10_字段元数据扩展.csv",
}


def default_baseline_dir() -> Path:
    return Path(__file__).resolve().parents[3] / "docs" / "PatWiki_refactor_data"


def normalize_source_alias(value: str) -> str:
    """Normalize only formatting noise; never infer a different business term."""
    value = unicodedata.normalize("NFKC", str(value or "")).strip().lower()
    return re.sub(r"[\s_\-./\\:：,，;；()（）【】\[\]]", "", value)


def canonical_key_for(display_name: str) -> str:
    digest = hashlib.sha1(normalize_source_alias(display_name).encode("utf-8")).hexdigest()[:20]
    return f"cf_{digest}"


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def registry_version(baseline_dir: Path | None = None) -> tuple[str, dict[str, str]] | None:
    baseline_dir = baseline_dir or default_baseline_dir()
    file_hashes: dict[str, str] = {}
    for filename in BASELINE_FILENAMES.values():
        path = baseline_dir / filename
        if not path.is_file():
            return None
        file_hashes[filename] = hashlib.sha256(path.read_bytes()).hexdigest()
    payload = json.dumps(file_hashes, ensure_ascii=False, sort_keys=True).encode("utf-8")
    return f"baseline-{hashlib.sha256(payload).hexdigest()[:20]}", file_hashes


def _split_aliases(value: str) -> list[str]:
    return [part.strip() for part in re.split(r"[、,，;；|]", str(value or "")) if part.strip()]


def _int_or_none(value: str) -> int | None:
    try:
        return int(str(value or "").strip())
    except (TypeError, ValueError):
        return None


def _explicit_runtime_target(source_name: str, canonical_name: str) -> str | None:
    """Return only a target already explicitly declared by ImportService."""
    # Lazy import avoids a module cycle: ImportService consults this service
    # after its hardcoded mapping has been checked.
    from app.services.import_service import STANDARD_FIELD_MAPPINGS, SYSTEM_FIELD_KEYS, VIRTUAL_FIELDS

    normalized = normalize_source_alias(source_name)
    candidates = [source_name, canonical_name]
    for known_name, target in STANDARD_FIELD_MAPPINGS.items():
        if normalize_source_alias(known_name) == normalized:
            candidates.insert(0, known_name)
    for candidate in candidates:
        target = STANDARD_FIELD_MAPPINGS.get(candidate)
        if target and (target in SYSTEM_FIELD_KEYS or target in VIRTUAL_FIELDS):
            return target
    return None


def seed_registry_baseline(db: Session, baseline_dir: Path | None = None) -> dict:
    """Idempotently load the checked-in CSV baseline.

    A missing documentation bundle is a deployment concern, not a reason to
    corrupt the patent database.  The caller receives ``available=False`` and
    may show that state in diagnostics.
    """
    baseline_dir = baseline_dir or default_baseline_dir()
    version_info = registry_version(baseline_dir)
    if version_info is None:
        return {"available": False, "reason": f"baseline files not found: {baseline_dir}"}
    version, file_hashes = version_info
    existing_snapshot = db.query(FieldRegistrySnapshot).filter(
        FieldRegistrySnapshot.registry_version == version,
    ).first()
    if existing_snapshot:
        return governance_summary(db) | {
            "available": True,
            "registry_version": version,
            "seeded": False,
        }

    table_rows = _read_csv(baseline_dir / BASELINE_FILENAMES["tables"])
    field_rows = _read_csv(baseline_dir / BASELINE_FILENAMES["fields"])
    concept_rows = _read_csv(baseline_dir / BASELINE_FILENAMES["concepts"])
    metadata_rows = _read_csv(baseline_dir / BASELINE_FILENAMES["metadata"])

    db.query(FieldRegistrySnapshot).update({FieldRegistrySnapshot.is_active: False}, synchronize_session=False)
    snapshot = FieldRegistrySnapshot(
        registry_version=version,
        source_files=file_hashes,
        metadata_fields=[row.get("建议字段") for row in metadata_rows if row.get("建议字段")],
        is_active=True,
    )
    db.add(snapshot)

    table_by_title: dict[str, SourceTableDefinition] = {}
    for row in table_rows:
        title = (row.get("表格/视图") or "").strip()
        if not title:
            continue
        table_key = f"source_{hashlib.sha1(title.encode('utf-8')).hexdigest()[:20]}"
        table = db.query(SourceTableDefinition).filter(SourceTableDefinition.table_key == table_key).first()
        if table is None:
            table = SourceTableDefinition(table_key=table_key)
            db.add(table)
        table.title = title
        table.category = row.get("大类")
        table.purpose = row.get("用途")
        table.usage_level = row.get("使用层级")
        table.purpose_system = row.get("用途体系")
        table.field_count = _int_or_none(row.get("字段数"))
        table.target_shape = row.get("重构后建议")
        table.source_file = BASELINE_FILENAMES["tables"]
        table.status = "active"
        table_by_title[title] = table
    db.flush()

    concept_by_name: dict[str, FieldDefinition] = {}
    for row in concept_rows:
        display_name = (row.get("归一化字段") or "").strip()
        if not display_name:
            continue
        canonical_key = canonical_key_for(display_name)
        field = db.query(FieldDefinition).filter(FieldDefinition.canonical_key == canonical_key).first()
        if field is None:
            field = FieldDefinition(canonical_key=canonical_key, display_name=display_name)
            db.add(field)
        field.display_name = display_name
        field.owner_entity_type = row.get("建议归属实体")
        field.semantic_type = row.get("数据属性")
        field.source_type = row.get("主要生产方式")
        field.volatility = row.get("时间变化性")
        field.audit_policy = row.get("审计要求")
        field.sensitivity = row.get("敏感级")
        field.ai_policy = {"applicability": row.get("AI适用性")} if row.get("AI适用性") else None
        field.validation_schema = {"description": row.get("数据校验")} if row.get("数据校验") else None
        field.storage_kind = row.get("建议存储方式")
        field.responsibility_level = row.get("字段层级建议")
        field.migration_status = "candidate"
        field.is_active = True
        concept_by_name[display_name] = field
    db.flush()

    for row in field_rows:
        table_title = (row.get("来源表") or "").strip()
        source_name = (row.get("原始字段") or "").strip()
        canonical_name = (row.get("归一化字段") or "").strip()
        table = table_by_title.get(table_title)
        field = concept_by_name.get(canonical_name)
        if not table or not source_name or not field:
            continue
        target = _explicit_runtime_target(source_name, canonical_name)
        mapping = db.query(SourceFieldMapping).filter(
            SourceFieldMapping.source_table_id == table.id,
            SourceFieldMapping.source_field_name == source_name,
            SourceFieldMapping.mapping_version == version,
        ).first()
        if mapping is None:
            mapping = SourceFieldMapping(
                source_table_id=table.id,
                source_field_name=source_name,
                mapping_version=version,
            )
            db.add(mapping)
        mapping.normalized_alias = normalize_source_alias(source_name)
        mapping.canonical_field_key = field.canonical_key
        mapping.target_field_key = target
        mapping.mapping_status = "mapped" if target else "candidate"
        mapping.occurrence_count = 1
        mapping.notes = "基于当前 ImportService 显式别名建立；未映射列仍须保留来源证据。"

    db.commit()
    return governance_summary(db) | {
        "available": True,
        "registry_version": version,
        "seeded": True,
    }


def find_approved_runtime_mapping(
    db: Session,
    source_column: str,
    valid_targets: Iterable[str],
) -> str | None:
    """Resolve an alias only when the baseline explicitly approved it."""
    normalized = normalize_source_alias(source_column)
    rows = db.query(SourceFieldMapping).filter(
        SourceFieldMapping.normalized_alias == normalized,
        SourceFieldMapping.mapping_status == "mapped",
    ).all()
    valid = set(valid_targets)
    targets = {row.target_field_key for row in rows if row.target_field_key in valid}
    return next(iter(targets)) if len(targets) == 1 else None


def governance_summary(db: Session) -> dict:
    return {
        "source_table_count": db.query(SourceTableDefinition).filter(SourceTableDefinition.status == "active").count(),
        "canonical_field_count": db.query(FieldDefinition).filter(FieldDefinition.is_active.is_(True)).count(),
        "source_mapping_count": db.query(SourceFieldMapping).count(),
        "mapping_status_counts": {
            status: count
            for status, count in db.query(
                SourceFieldMapping.mapping_status,
                func.count(SourceFieldMapping.id),
            ).group_by(SourceFieldMapping.mapping_status).all()
        },
    }


def list_source_tables(db: Session) -> list[dict]:
    rows = db.query(SourceTableDefinition).order_by(SourceTableDefinition.title).all()
    return [
        {
            "id": row.id,
            "table_key": row.table_key,
            "title": row.title,
            "category": row.category,
            "purpose": row.purpose,
            "usage_level": row.usage_level,
            "purpose_system": row.purpose_system,
            "field_count": row.field_count,
            "target_shape": row.target_shape,
            "source_file": row.source_file,
            "status": row.status,
        }
        for row in rows
    ]


def list_field_definitions(db: Session, limit: int = 500) -> list[dict]:
    rows = db.query(FieldDefinition).filter(FieldDefinition.is_active.is_(True)).order_by(FieldDefinition.display_name).limit(limit).all()
    return [
        {
            "id": row.id,
            "canonical_key": row.canonical_key,
            "display_name": row.display_name,
            "owner_entity_type": row.owner_entity_type,
            "semantic_type": row.semantic_type,
            "source_type": row.source_type,
            "source_timestamp": row.source_timestamp.isoformat() if row.source_timestamp else None,
            "volatility": row.volatility,
            "audit_policy": row.audit_policy,
            "sensitivity": row.sensitivity,
            "ai_policy": row.ai_policy,
            "validation_schema": row.validation_schema,
            "storage_kind": row.storage_kind,
            "migration_status": row.migration_status,
            "responsibility_level": row.responsibility_level,
        }
        for row in rows
    ]


def list_source_mappings(db: Session, status: str | None = None, limit: int = 1000) -> list[dict]:
    query = db.query(SourceFieldMapping, SourceTableDefinition, FieldDefinition).join(
        SourceTableDefinition,
        SourceTableDefinition.id == SourceFieldMapping.source_table_id,
    ).outerjoin(
        FieldDefinition,
        FieldDefinition.canonical_key == SourceFieldMapping.canonical_field_key,
    )
    if status:
        query = query.filter(SourceFieldMapping.mapping_status == status)
    rows = query.order_by(SourceTableDefinition.title, SourceFieldMapping.source_field_name).limit(limit).all()
    return [
        {
            "id": mapping.id,
            "source_table": table.title,
            "source_table_id": table.id,
            "source_field_name": mapping.source_field_name,
            "normalized_alias": mapping.normalized_alias,
            "canonical_field_key": mapping.canonical_field_key,
            "canonical_field_name": field.display_name if field else None,
            "target_field_key": mapping.target_field_key,
            "mapping_status": mapping.mapping_status,
            "mapping_version": mapping.mapping_version,
            "occurrence_count": mapping.occurrence_count,
            "notes": mapping.notes,
        }
        for mapping, table, field in rows
    ]
