"""Staged patent import: analyse first, write only after explicit review."""
from __future__ import annotations

from datetime import date, datetime
import hashlib
import json
from pathlib import Path
from typing import Any, Iterable

from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from app.core.exceptions import BadRequestException, NotFoundException
from app.core.time import utc_now_naive
from app.models import (
    Citation, CustomField, FieldObservation, ImportBatch, ImportBatchStatus,
    ImportSourceRow, Patent, PatentDatabase, PatentHistory, PatentIdentifier, LegalStatus,
    PatentType, RiskLevel,
)
from app.services.field_registry import SYSTEM_FIELD_KEYS
from app.services.import_service import ImportService, IMPORT_SKIP_FIELD
from app.services.patent_identity_service import (
    ensure_patent_identifiers, find_patents_by_identifier_specs_bulk,
    identifier_specs_from_values,
)
from app.models.database_membership import PatentDatabaseMembership

REVIEW_ACTIONS = {"adopt", "keep_existing", "fill_empty", "ignore", "quarantine"}
PROTECTED_FIELDS = {"has_risk", "risk_level", "risk_description"}
RELATION_FIELDS = {"family_members", "cited_patents", "citing_patents"}
DATE_FIELDS = {"filing_date", "publication_date", "grant_date", "priority_date", "legal_status_date"}


def is_unmapped_target_error(reason: str | None) -> bool:
    """Identify an explicit mapping to an unregistered field.

    It is a governance warning, not a parse failure: the source cell must be
    retained as an unmapped observation while other fields in the row remain
    eligible for import.
    """
    return bool(reason and reason.startswith("未知的导入目标字段"))


def text_value(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    # Do not read pandas Timestamp.value here: that is an integer nanosecond
    # count, not the date text users expect to review and import.
    if hasattr(value, "value"):
        value = value.value
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False, default=str)
    return str(value)


def raw_row(row: dict) -> dict[str, str]:
    return {str(key): text_value(value) or "" for key, value in row.items()}


def row_hash(row: dict[str, str]) -> str:
    return hashlib.sha256(json.dumps(row, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()


def current_value(patent: Patent | None, field_key: str) -> str | None:
    if patent is None:
        return None
    if field_key in RELATION_FIELDS:
        return text_value((patent.custom_fields or {}).get(field_key))
    if field_key in SYSTEM_FIELD_KEYS:
        return text_value(getattr(patent, field_key, None))
    return text_value((patent.custom_fields or {}).get(field_key))


def candidate_value(field_key: str, patent_data: dict | None, virtual: dict | None) -> str | None:
    if not patent_data:
        return None
    virtual = virtual or {}
    relation_keys = {
        "family_members": "family_numbers",
        "cited_patents": "cited_numbers",
        "citing_patents": "citing_numbers",
    }
    if field_key in relation_keys:
        return ", ".join(virtual.get(relation_keys[field_key]) or [])
    custom = patent_data.get("custom_fields") or {}
    return text_value(custom[field_key]) if field_key in custom else text_value(patent_data.get(field_key))


def difference_type(current: str | None, candidate: str | None) -> str:
    if not candidate:
        return "unknown"
    if not current:
        return "new"
    if current == candidate:
        return "same"
    if current.strip() == candidate.strip():
        return "format"
    return "content"


def default_action(observation: FieldObservation) -> str:
    if observation.field_resolution == "quarantined" or observation.difference_type == "quarantined":
        return "quarantine"
    if observation.field_resolution == "unmapped_retained":
        return "keep_existing"
    if observation.patent_id is None:
        return "adopt"
    if observation.difference_type == "new":
        return "fill_empty"
    return "keep_existing"


def source_rows(db: Session, batch_id: int) -> list[ImportSourceRow]:
    return db.query(ImportSourceRow).filter(
        ImportSourceRow.import_batch_id == batch_id,
    ).order_by(ImportSourceRow.source_row.asc(), ImportSourceRow.id.asc()).all()


def observations(db: Session, batch_id: int) -> list[FieldObservation]:
    return db.query(FieldObservation).filter(
        FieldObservation.import_batch_id == batch_id,
    ).order_by(FieldObservation.source_row_id.asc(), FieldObservation.source_column_index.asc(), FieldObservation.id.asc()).all()


def observation_payload(item: FieldObservation, source: ImportSourceRow, batch: ImportBatch) -> dict:
    return {
        "id": item.id,
        "batch_id": batch.id,
        "filename": batch.filename,
        "source_table_title": batch.source_table_title,
        "worksheet_name": batch.worksheet_name,
        "source_row_id": source.id,
        "source_row": source.source_row,
        "patent_id": item.patent_id,
        "candidate_patent_ids": source.candidate_patent_ids or [],
        "source_field_name": item.source_field_name,
        "source_column_index": item.source_column_index,
        "canonical_field_key": item.canonical_field_key,
        "raw_value": item.raw_value,
        "normalized_value": item.normalized_value,
        "current_value": item.current_value,
        "candidate_value": item.candidate_value,
        "difference_type": item.difference_type,
        "field_resolution": item.field_resolution,
        "proposed_action": item.proposed_action,
        "final_decision": item.final_decision,
        "review_action": item.final_decision or default_action(item),
        "decided_by": item.decided_by,
        "decided_at": item.decided_at.isoformat() if item.decided_at else None,
        "source_row_values": source.raw_row,
        "created_at": item.created_at.isoformat() if item.created_at else None,
    }


def validate_publication_mapping(columns: list[str], mapping: dict[str, str]) -> None:
    matches = [column for column in columns if mapping.get(column, "").strip() == "publication_number"]
    if not matches:
        raise BadRequestException(
            "导入必须包含并映射公开号列；申请号或授权号不能替代公开号",
            detail={"mapping_issues": [{
                "column": "__publication_number__",
                "target_field": "publication_number",
                "reason": "缺少公开号列",
            }]},
        )
    if len(matches) > 1:
        raise BadRequestException("一个导入批次只能有一个公开号来源列")


def add_observations(
    db: Session,
    batch: ImportBatch,
    source: ImportSourceRow,
    columns: list[str],
    mapping: dict[str, str],
    patent: Patent | None,
    data: dict | None,
    virtual: dict | None,
    field_errors: dict[str, str] | None = None,
) -> int:
    unknown_count = 0
    field_errors = field_errors or {}
    for index, column in enumerate(columns):
        value = source.raw_row.get(column, "")
        if not value:
            continue
        target = mapping.get(column, "").strip()
        if target == IMPORT_SKIP_FIELD:
            continue
        if target in field_errors:
            # An explicit mapping to a field that is not registered is still
            # source data, not a reason to discard the cell or quarantine the
            # whole row. Keep it in the same governance queue as an unmapped
            # column so it can be mapped after the import.
            if is_unmapped_target_error(field_errors[target]):
                unknown_count += 1
                db.add(FieldObservation(
                    import_batch_id=batch.id, source_row_id=source.id,
                    patent_id=patent.id if patent else None,
                    source_field_name=column, source_column_index=index,
                    raw_value=value, normalized_value=value, candidate_value=value,
                    difference_type="unknown", field_resolution="unmapped_retained",
                    proposed_action="retain",
                ))
                continue
            current = current_value(patent, target)
            db.add(FieldObservation(
                import_batch_id=batch.id, source_row_id=source.id,
                patent_id=patent.id if patent else None,
                source_field_name=column, source_column_index=index,
                canonical_field_key=target, raw_value=value,
                normalized_value=None, current_value=current, candidate_value=None,
                difference_type="quarantined", field_resolution="quarantined",
                proposed_action="quarantine",
            ))
            continue
        if not target:
            unknown_count += 1
            db.add(FieldObservation(
                import_batch_id=batch.id, source_row_id=source.id,
                patent_id=patent.id if patent else None,
                source_field_name=column, source_column_index=index,
                raw_value=value, normalized_value=value, candidate_value=value,
                difference_type="unknown", field_resolution="unmapped_retained",
                proposed_action="retain",
            ))
            continue
        # Relation columns have two representations: the parsed numbers are
        # used to build links, while the exact source cell remains the value
        # shown/exported in the Wiki projection.
        candidate = value if target in RELATION_FIELDS else candidate_value(target, data, virtual)
        normalized_candidate = candidate_value(target, data, virtual)
        current = current_value(patent, target)
        diff = difference_type(current, candidate)
        item = FieldObservation(
            import_batch_id=batch.id, source_row_id=source.id,
            patent_id=patent.id if patent else None,
            source_field_name=column, source_column_index=index,
            canonical_field_key=target, raw_value=value,
            normalized_value=normalized_candidate or candidate or value, current_value=current,
            candidate_value=candidate or value, difference_type=diff,
            field_resolution="mapped",
        )
        item.proposed_action = default_action(item)
        db.add(item)
    return unknown_count


def stage_import(
    db: Session, *, content: bytes, filename: str, sheet_name: str | None,
    mapping: dict[str, str], database_id: int, product_id: int | None = None,
    project_id: int | None = None, view_id: int | None = None,
    source_table_title: str | None = None, source_system: str | None = None,
    artifact_path: str | None = None,
) -> dict:
    df, columns = ImportService.parse_excel(content, filename, sheet_name)
    validate_publication_mapping(columns, mapping)
    issues = ImportService.validate_mapping(columns, mapping, db)
    blocking_issues = [issue for issue in issues if issue.get("severity", "warning") == "error"]
    mapping_warnings = [issue for issue in issues if issue.get("severity", "warning") != "error"]
    if blocking_issues:
        # Keep this defensive check for callers that bypass validate_publication_mapping.
        raise BadRequestException("导入已阻止：请先修复公开号映射", detail={"mapping_issues": blocking_issues})
    batch = ImportBatch(
        filename=filename, source_table_title=source_table_title or Path(filename).stem,
        worksheet_name=sheet_name, source_system=source_system,
        mapping_version="v2-review", file_hash=hashlib.sha256(content).hexdigest(),
        artifact_path=artifact_path, status=ImportBatchStatus.PROCESSING,
         started_at=utc_now_naive(), total_rows=len(df), mapping_config=mapping,
         review_config={"database_id": database_id, "product_id": product_id,
                        "project_id": project_id, "view_id": view_id,
                        "source_system": source_system, "mapping_warnings": mapping_warnings},
        created_patent_ids=[],
    )
    db.add(batch)
    db.flush()
    custom_cache = {field.key: field for field in db.query(CustomField).all()}
    errors: list[dict] = []
    field_error_reports: list[dict] = []
    reports: list[dict] = []
    unknown_count = 0
    seen_publications: set[str] = set()
    duplicate_count = 0
    existing_count = 0
    new_count = 0
    retained_source_rows = 0
    skipped_empty_rows = 0
    try:
        identity_specs_by_row: dict[int, list] = {}
        parsed_rows: dict[int, tuple[dict, dict, dict]] = {}
        staged_sources: list[ImportSourceRow] = []
        # Parse once and resolve identities in one bounded query. Reusing the
        # parsed values also removes a second conversion pass per source row.
        for index, (_, row) in enumerate(df.iterrows()):
            parsed_row = raw_row(row.to_dict())
            source = ImportSourceRow(
                import_batch_id=batch.id,
                source_row=index + 2,
                raw_row=parsed_row,
                row_hash=row_hash(parsed_row),
            )
            staged_sources.append(source)
            parsed = ImportService._row_to_patent_data_tolerant(
                parsed_row, mapping, db, custom_fields_cache=custom_cache,
            )
            parsed_rows[index] = parsed
            data, _, _ = parsed
            publication = (data.get("publication_number") or "").strip()
            specs = [spec for spec in identifier_specs_from_values(
                {"publication": publication}, data.get("country"),
            ) if spec.identifier_type == "publication"]
            if specs:
                identity_specs_by_row[index] = specs
        # One flush assigns all source-row ids for observation foreign keys.
        # The previous per-row flush made review latency grow linearly with
        # SQLite round trips.
        db.add_all(staged_sources)
        db.flush()
        bulk_matches = find_patents_by_identifier_specs_bulk(db, identity_specs_by_row)
        for index, (_, row) in enumerate(df.iterrows()):
            row_values = raw_row(row.to_dict())
            source = staged_sources[index]
            try:
                data, virtual, field_errors = parsed_rows[index]
                publication = (data.get("publication_number") or "").strip()
                publication_error = field_errors.get("publication_number")
                if publication_error:
                    raise ValueError(publication_error)
                if not publication:
                    if any(value for value in row_values.values()):
                        # The workbook still has a valid publication column, but
                        # this row has no identity. Preserve it as replayable
                        # source evidence instead of treating it as a bad row.
                        source.resolution_status = "retained_source_row"
                        source.resolution_reason = "本行缺少公开号，已保留为待补身份来源行"
                        retained_source_rows += 1
                        unknown_count += add_observations(
                            db, batch, source, columns, mapping, None, data, virtual,
                            field_errors,
                        )
                        report = {
                            "row": index + 2,
                            "status": "retained_source_row",
                            "reason": source.resolution_reason,
                        }
                        reports.append(report)
                        continue
                    source.resolution_status = "skipped_empty_row"
                    source.resolution_reason = "整行没有非空内容"
                    skipped_empty_rows += 1
                    reports.append({
                        "row": index + 2,
                        "status": "skipped_empty_row",
                        "reason": source.resolution_reason,
                    })
                    continue
                specs = [spec for spec in identifier_specs_from_values(
                    {"publication": publication}, data.get("country"),
                ) if spec.identifier_type == "publication"]
                if not specs:
                    raise ValueError(f"公开号格式无法识别：{publication}")
                matches = bulk_matches.get(index, [])
                if len(matches) > 1:
                    source.resolution_status = "quarantined"
                    source.resolution_reason = "规范化公开号命中多个专利，已隔离等待人工确认"
                    source.candidate_patent_ids = [item.id for item in matches]
                    unknown_count += add_observations(
                        db, batch, source, columns, mapping, None, data, virtual, field_errors,
                    )
                    report = {"row": index + 2, "status": "identity_conflict", "reason": source.resolution_reason}
                    errors.append(report)
                    reports.append(report)
                    continue
                patent = matches[0] if matches else None
                if publication in seen_publications:
                    duplicate_count += 1
                    source.resolution_reason = "本批次公开号重复，后续行等待审查"
                seen_publications.add(publication)
                if patent:
                    source.patent_id = patent.id
                    source.resolution_status = "resolved"
                    source.resolution_reason = "公开号已命中现有 Patent Wiki，等待字段审查"
                    existing_count += 1
                else:
                    source.resolution_status = "pending_create"
                    source.resolution_reason = "公开号有效，等待审查后创建 Patent Wiki"
                    new_count += 1
                unknown_count += add_observations(
                    db, batch, source, columns, mapping, patent, data, virtual, field_errors,
                )
                report = {"row": index + 2, "status": "existing_review" if patent else "new_review",
                          "reason": source.resolution_reason, "patent_id": patent.id if patent else None}
                report_field_errors = {
                    key: reason for key, reason in field_errors.items()
                    if not is_unmapped_target_error(reason)
                }
                if report_field_errors:
                    field_warnings = [
                        {"row": index + 2, "status": "field_error", "field": key, "reason": reason}
                        for key, reason in report_field_errors.items()
                    ]
                    reports.append({
                        "row": index + 2,
                        "status": "existing_review_with_field_errors" if patent else "new_review_with_field_errors",
                        "reason": source.resolution_reason,
                        "patent_id": patent.id if patent else None,
                        "field_errors": field_warnings,
                    })
                    # The row remains eligible for valid-field updates. These
                    # warnings are surfaced separately from row quarantine.
                    field_error_reports.extend(field_warnings)
                else:
                    reports.append(report)
            except Exception as exc:
                source.resolution_status = "quarantined"
                source.resolution_reason = str(exc)
                # Keep any successfully parsed fields in the observation set;
                # only the identity failure quarantines the row itself.
                try:
                    partial_data, partial_virtual, partial_errors = ImportService._row_to_patent_data_tolerant(
                        row_values, mapping, db, custom_fields_cache=custom_cache,
                    )
                except Exception:
                    partial_data, partial_virtual, partial_errors = None, None, {}
                unknown_count += add_observations(
                    db, batch, source, columns, mapping, None,
                    partial_data, partial_virtual, partial_errors,
                )
                report = {"row": index + 2, "status": "quarantined", "reason": str(exc)}
                errors.append(report)
                reports.append(report)
        batch.processed_rows = len(df)
        batch.duplicate_count = duplicate_count
        batch.error_count = len(errors) + len(field_error_reports)
        batch.errors = [*errors, *field_error_reports] or None
        batch.status = ImportBatchStatus.REVIEW_REQUIRED
        batch.completed_at = utc_now_naive()
        db.commit()
    except Exception:
        db.rollback()
        raise
    staged = observations(db, batch.id)
    return {
        "batch_id": batch.id, "status": batch.status.value, "total": len(df),
        "created": 0, "updated": 0, "skipped": 0, "errors": len(errors),
        "field_errors": len(field_error_reports),
        "review_count": sum(item.difference_type in {"new", "content", "format"} for item in staged),
        "unmapped_retained": unknown_count, "existing_count": existing_count,
        "new_count": new_count, "quarantined_count": len(errors),
        "retained_source_rows": retained_source_rows,
        "skipped_empty_rows": skipped_empty_rows,
        "unknown_columns": [key for key, value in mapping.items() if not value and value != IMPORT_SKIP_FIELD],
        "mapping_warnings": mapping_warnings,
        "row_reports": reports, "error_details": errors,
        "field_error_details": field_error_reports,
    }


def list_batch_changes(db: Session, batch_id: int, *, only_differences: bool = False, limit: int = 2000) -> dict:
    batch = db.query(ImportBatch).filter(ImportBatch.id == batch_id).first()
    if not batch:
        raise NotFoundException("导入批次不存在")
    source_by_id = {row.id: row for row in source_rows(db, batch_id)}
    query = db.query(FieldObservation).filter(FieldObservation.import_batch_id == batch_id)
    if only_differences:
        query = query.filter(FieldObservation.difference_type.in_(["new", "content", "format"]))
    items = query.order_by(FieldObservation.source_row_id.asc(), FieldObservation.source_column_index.asc()).limit(limit).all()
    return {"batch_id": batch.id, "status": batch.status.value, "total": len(items),
            "items": [observation_payload(item, source_by_id[item.source_row_id], batch)
                      for item in items if item.source_row_id in source_by_id]}


def review_batch(db: Session, batch_id: int, *, items: Iterable[dict] = (),
                 default_action_name: str | None = None,
                 reviewed_by: str = "local-user", reason: str | None = None) -> dict:
    batch = db.query(ImportBatch).filter(ImportBatch.id == batch_id).first()
    if not batch:
        raise NotFoundException("导入批次不存在")
    if batch.status != ImportBatchStatus.REVIEW_REQUIRED:
        raise BadRequestException("当前导入批次不在待审查状态")
    if default_action_name is not None and default_action_name not in REVIEW_ACTIONS:
        raise BadRequestException(f"不支持的导入审查动作：{default_action_name}")
    staged = observations(db, batch_id)
    by_id = {int(item["observation_id"]): str(item["action"]) for item in items}
    unknown_ids = set(by_id) - set(item.id for item in staged)
    if unknown_ids:
        raise BadRequestException(f"审查项不属于该导入批次：{sorted(unknown_ids)[:5]}")
    actor = reviewed_by.strip() or "local-user"
    count = 0
    for item in staged:
        action = by_id.get(item.id)
        if action is None and default_action_name and item.field_resolution == "mapped":
            action = default_action_name
        if action is None:
            continue
        if action not in REVIEW_ACTIONS:
            raise BadRequestException(f"不支持的导入审查动作：{action}")
        if item.field_resolution == "unmapped_retained" and action == "adopt":
            raise BadRequestException("未治理字段必须先映射到正式字段，不能直接采用")
        item.final_decision = action
        item.decided_by = actor
        item.decided_at = utc_now_naive()
        count += 1
    config = dict(batch.review_config or {})
    config["last_review"] = {"reviewed_by": actor, "reason": reason, "reviewed_at": utc_now_naive().isoformat()}
    batch.review_config = config
    db.commit()
    return {"batch_id": batch.id, "reviewed_count": count, "status": batch.status.value}


def coerce_value(field_key: str, value: str):
    if field_key in DATE_FIELDS:
        try:
            parsed = ImportService._parse_date(value)
            if parsed is None:
                raise ValueError(value)
            return parsed
        except ValueError as exc:
            raise BadRequestException(f"来源值无法写入日期字段 {field_key}：{value}") from exc
    if field_key == "legal_status":
        try:
            return LegalStatus(value)
        except ValueError:
            return ImportService._map_legal_status(value)
    if field_key == "patent_type":
        try:
            return PatentType(value)
        except ValueError:
            return ImportService._map_patent_type(value)
    if field_key == "risk_level":
        try:
            return RiskLevel(value)
        except ValueError:
            return ImportService._map_risk_level(value)
    if field_key == "has_risk":
        return value.strip().lower() in {"1", "true", "yes", "y", "是", "有"}
    return value


def write_value(patent: Patent, field_key: str, value: str) -> tuple[Any, Any]:
    old = current_value(patent, field_key)
    new = coerce_value(field_key, value)
    if field_key in RELATION_FIELDS:
        patent.custom_fields = {**(patent.custom_fields or {}), field_key: value}
    elif field_key in SYSTEM_FIELD_KEYS:
        setattr(patent, field_key, new)
    else:
        patent.custom_fields = {**(patent.custom_fields or {}), field_key: new}
    return old, new


def import_storage_value(item: FieldObservation) -> str:
    """Return the value that belongs in the canonical record projection.

    For relation columns this must be the exact source cell. The normalized
    number list is only for relation resolution and must never replace the
    user's original column text in list/detail/export views.
    """
    if item.canonical_field_key in RELATION_FIELDS:
        return item.raw_value or ""
    return item.candidate_value or item.raw_value or ""


def add_import_history(
    db: Session,
    *,
    patent: Patent,
    item: FieldObservation,
    batch: ImportBatch,
    source: ImportSourceRow,
    old_value: Any,
    new_value: Any,
    actor: str,
) -> None:
    """Record both changed and no-op import decisions for Wiki traceability."""
    db.add(PatentHistory(
        patent_id=patent.id,
        field_key=item.canonical_field_key or item.source_field_name,
        field_display_name=item.source_field_name,
        old_value=text_value(old_value),
        new_value=text_value(new_value),
        source="import",
        changed_by=actor,
        import_batch_id=batch.id,
        source_table_title=batch.source_table_title,
        source_row=source.source_row,
        source_field_name=item.source_field_name,
    ))


def apply_batch(db: Session, batch_id: int, *, applied_by: str = "local-user") -> dict:
    batch = db.query(ImportBatch).filter(ImportBatch.id == batch_id).first()
    if not batch:
        raise NotFoundException("导入批次不存在")
    if batch.status != ImportBatchStatus.REVIEW_REQUIRED:
        raise BadRequestException("导入批次必须先完成审查，且只能执行一次")
    config = batch.review_config or {}
    database_id = config.get("database_id")
    if not database_id or not batch.artifact_path or not Path(batch.artifact_path).is_file():
        raise BadRequestException("导入批次缺少目标专利库或原始文件")
    mapping = dict(batch.mapping_config or {})
    df, _ = ImportService.parse_excel(Path(batch.artifact_path).read_bytes(), batch.filename, batch.worksheet_name)
    staged = observations(db, batch_id)
    rows = source_rows(db, batch_id)
    source_by_id = {row.id: row for row in rows}
    by_row: dict[int, list[FieldObservation]] = {}
    for item in staged:
        by_row.setdefault(item.source_row_id, []).append(item)
    actor = applied_by.strip() or "local-user"
    inserted = updated = unchanged = 0
    errors: list[dict] = []
    created_ids: list[int] = []
    changed_ids: set[int] = set()
    pending_relations: list[tuple[Patent, dict]] = []
    new_by_publication: dict[str, Patent] = {}
    row_reports: list[dict] = []
    field_error_details: list[dict] = []
    target_membership_patent_ids = {
        int(row[0]) for row in db.query(PatentDatabaseMembership.patent_id).filter(
            PatentDatabaseMembership.database_id == database_id,
        ).all()
    }
    try:
        for index, _ in enumerate(df.iterrows()):
            source = rows[index] if index < len(rows) else None
            if source is None:
                continue
            try:
                if source.resolution_status in {"quarantined", "retained_source_row", "skipped_empty_row"}:
                    if source.resolution_status != "quarantined":
                        row_reports.append({
                            "row": source.source_row,
                            "status": source.resolution_status,
                            "reason": source.resolution_reason,
                        })
                        continue
                    # Identity/parse failures are already isolated during
                    # staging. Applying a batch must never turn an ambiguous
                    # row into a guessed Patent just because another match is
                    # available at execution time.
                    row_reports.append({
                        "row": source.source_row,
                        "status": "quarantined",
                        "reason": source.resolution_reason or "来源行已隔离",
                    })
                    errors.append({
                        "row": source.source_row,
                        "status": "quarantined",
                        "reason": source.resolution_reason or "来源行已隔离",
                    })
                    continue
                data, virtual, parse_errors = ImportService._row_to_patent_data_tolerant(
                    source.raw_row, mapping, db,
                )
                publication = (data.get("publication_number") or "").strip()
                items = by_row.get(source.id, [])
                actions = {item.id: item.final_decision or default_action(item) for item in items}
                publication_item = next((item for item in items if item.canonical_field_key == "publication_number"), None)
                if publication_item and actions.get(publication_item.id) in {"ignore", "quarantine", "keep_existing"} and not source.patent_id:
                    raise ValueError("创建专利时必须采用公开号")
                patent = db.query(Patent).filter(Patent.id == source.patent_id).first() if source.patent_id else None
                created_in_batch = False
                if patent is None:
                    # Staging already resolved every valid identity. Pending
                    # rows are new at apply time; only reuse a patent created
                    # earlier in this same batch, with no per-row DB lookup.
                    patent = new_by_publication.get(publication)
                    created_in_batch = patent is not None and patent.id in created_ids
                created = False
                provisional_title = False
                row_field_errors: list[dict] = []
                if patent is None:
                    provisional_title = not bool(data.get("title"))
                    create_data: dict[str, Any] = {
                        "database_id": database_id, "source_batch_id": batch.id,
                        "source_row": source.source_row, "publication_number": publication,
                        "country": data.get("country") or "CN", "title": data.get("title") or "待补全",
                    }
                    for field_key, value in data.items():
                        if field_key in {"custom_fields", "database_id", "source_batch_id", "source_row", "view_id", "product_id"} | PROTECTED_FIELDS:
                            continue
                        item = next((item for item in items if item.canonical_field_key == field_key), None)
                        if item and actions.get(item.id) in {"adopt", "fill_empty"}:
                            create_data[field_key] = value
                    for key in ("product_id", "view_id"):
                        if config.get(key):
                            create_data[key] = config[key]
                    custom = {}
                    for key, value in (data.get("custom_fields") or {}).items():
                        key_items = [item for item in items if item.canonical_field_key == key]
                        adopted_items = [
                            item for item in key_items
                            if actions.get(item.id) in {"adopt", "fill_empty"}
                        ]
                        if not adopted_items:
                            continue
                        if key in RELATION_FIELDS:
                            # Keep the source projection byte-for-byte as far
                            # as the decoded cell permits. Relation parsing
                            # happens separately below.
                            custom[key] = "\n".join(item.raw_value or "" for item in adopted_items)
                        else:
                            custom[key] = value
                    patent = Patent(**create_data)
                    patent.custom_fields = custom
                    db.add(patent)
                    db.flush()
                    new_by_publication[publication] = patent
                    created_ids.append(patent.id)
                    inserted += 1
                    created = True

                    # A newly created Patent has no old value, but each
                    # adopted source field still needs a Wiki provenance
                    # entry. This is especially important for duplicate rows
                    # in one batch, where the second row reuses this Patent.
                    for item in items:
                        if actions.get(item.id) not in {"adopt", "fill_empty"} or not item.canonical_field_key or not item.candidate_value:
                            continue
                        add_import_history(
                            db,
                            patent=patent,
                            item=item,
                            batch=batch,
                            source=source,
                            old_value=None,
                            new_value=import_storage_value(item),
                            actor=actor,
                        )
                else:
                    row_changes = 0
                    for item in items:
                        key = item.canonical_field_key
                        action = actions.get(item.id)
                        if not key:
                            continue
                        if not item.candidate_value and key not in parse_errors:
                            continue
                        current = current_value(patent, key)
                        if action == "adopt" and not created_in_batch and current != item.current_value:
                            detail = {
                                "row": source.source_row,
                                "status": "field_conflict",
                                "field": key,
                                "reason": f"{key} 在审查后发生变化，已保留较新的当前值",
                                "current_value": current,
                                "reviewed_value": item.current_value,
                                "candidate_value": item.candidate_value,
                            }
                            row_field_errors.append(detail)
                            field_error_details.append(detail)
                            item.difference_type = "quarantined"
                            item.field_resolution = "quarantined"
                            item.final_decision = "quarantine"
                            continue
                        if action in {"adopt", "fill_empty"}:
                            if key in parse_errors or item.difference_type == "quarantined":
                                # A malformed source cell is isolated at field
                                # level. Other valid fields in this row still
                                # apply and the raw value remains reviewable.
                                detail = {
                                    "row": source.source_row,
                                    "status": "field_error",
                                    "field": key,
                                    "reason": parse_errors.get(key) or "字段已隔离，未写入正式数据",
                                    "candidate_value": item.candidate_value or item.raw_value,
                                }
                                row_field_errors.append(detail)
                                field_error_details.append(detail)
                                continue
                            if action == "fill_empty" and current:
                                # The value was filled by somebody else after
                                # review. Keep that newer value and retain a
                                # no-op provenance event for this decision.
                                add_import_history(
                                    db, patent=patent, item=item, batch=batch,
                                    source=source, old_value=current,
                                    new_value=current, actor=actor,
                                )
                                continue
                            storage_value = import_storage_value(item)
                            try:
                                old, _ = write_value(patent, key, storage_value)
                            except Exception as exc:
                                detail = {
                                    "row": source.source_row,
                                    "status": "field_error",
                                    "field": key,
                                    "reason": str(exc),
                                    "candidate_value": storage_value,
                                }
                                row_field_errors.append(detail)
                                field_error_details.append(detail)
                                item.difference_type = "quarantined"
                                item.field_resolution = "quarantined"
                                item.final_decision = "quarantine"
                                continue
                            new = current_value(patent, key)
                            if text_value(old) != text_value(new):
                                row_changes += 1
                            add_import_history(
                                db, patent=patent, item=item, batch=batch,
                                source=source, old_value=old, new_value=new,
                                actor=actor,
                            )
                        elif action in {"keep_existing", "ignore", "quarantine"}:
                            # A no-op still records that this source field was
                            # reviewed and left unchanged. The FieldObservation
                            # carries the explicit decision; this history item
                            # makes the import visible in the Patent Wiki.
                            add_import_history(
                                db, patent=patent, item=item, batch=batch,
                                source=source, old_value=current,
                                new_value=current, actor=actor,
                            )
                    if row_changes:
                        updated += 1
                        changed_ids.add(patent.id)
                    else:
                        unchanged += 1
                if config.get("project_id"):
                    from app.services.patent_service import PatentService
                    PatentService.set_patent_projects(
                        db, patent, [int(config["project_id"])], commit=False,
                    )
                ensure_patent_identifiers(db, patent, additional_specs=identifier_specs_from_values({
                    "application": data.get("application_number"), "publication": publication,
                    "grant": data.get("grant_number")}, data.get("country")),
                    source_system=config.get("source_system") or "import", source_timestamp=utc_now_naive())
                source.patent_id = patent.id
                if patent.id not in target_membership_patent_ids:
                    db.add(PatentDatabaseMembership(
                        patent_id=patent.id,
                        database_id=database_id,
                    ))
                    target_membership_patent_ids.add(patent.id)
                source.resolution_status = "resolved"
                source.resolution_reason = (
                    "import applied after review; some fields were isolated"
                    if row_field_errors else "import applied after review"
                )
                for item in items:
                    item.patent_id = patent.id
                relation_items = [item for item in items if item.canonical_field_key in RELATION_FIELDS]
                if virtual and any(actions.get(item.id) in {"adopt", "fill_empty"} for item in relation_items):
                    pending_relations.append((patent, virtual))
                applied_report = {
                    "row": source.source_row,
                    "status": "created_pending_title" if created and provisional_title else "created" if created else "updated" if patent.id in changed_ids else "reviewed",
                    "patent_id": patent.id,
                }
                if row_field_errors:
                    applied_report["field_errors"] = row_field_errors
                row_reports.append(applied_report)
            except Exception as exc:
                source.resolution_status = "quarantined"
                source.resolution_reason = str(exc)
                errors.append({"row": source.source_row, "status": "apply_error", "reason": str(exc)})
        from app.api.imports import _process_relations
        family_links = citation_links = 0
        for patent, virtual in pending_relations:
            result = _process_relations(db, patent, virtual, database_id)
            family_links += result["family_links"]
            citation_links += result["citation_links"]
        batch.inserted_count = inserted
        batch.updated_count = updated
        batch.skipped_count = unchanged
        batch.error_count = len(errors) + len(field_error_details)
        batch.processed_rows = batch.total_rows
        batch.errors = [*errors, *field_error_details] or None
        batch.created_patent_ids = created_ids
        batch.status = ImportBatchStatus.COMPLETED
        batch.completed_at = utc_now_naive()
        target_database = db.query(PatentDatabase).filter(
            PatentDatabase.id == database_id,
        ).first()
        if target_database:
            target_database.patent_count = db.query(func.count(Patent.id)).filter(or_(
                Patent.database_id == database_id,
                db.query(PatentDatabaseMembership.id).filter(
                    PatentDatabaseMembership.patent_id == Patent.id,
                    PatentDatabaseMembership.database_id == database_id,
                ).exists(),
            )).scalar() or 0
        db.commit()
    except Exception:
        db.rollback()
        raise
    return {"batch_id": batch.id, "status": batch.status.value, "total": batch.total_rows,
            "created": inserted, "updated": updated, "unchanged": unchanged,
            # Kept for API compatibility. The UI should show this as
            # "unchanged after review", never as an import failure.
            "skipped": unchanged, "errors": len(errors),
             "error_details": errors, "row_reports": row_reports, "database_id": database_id,
             "family_links": family_links, "citation_links": citation_links,
             "field_errors": len(field_error_details), "field_error_details": field_error_details,
             "unmapped_retained": db.query(FieldObservation).filter(FieldObservation.import_batch_id == batch.id, FieldObservation.field_resolution == "unmapped_retained").count()}


def restore_value(patent: Patent, field_key: str, value: str | None) -> None:
    if value is None and field_key not in SYSTEM_FIELD_KEYS:
        custom = dict(patent.custom_fields or {})
        custom.pop(field_key, None)
        patent.custom_fields = custom
    elif value is None:
        setattr(patent, field_key, None)
    else:
        write_value(patent, field_key, value)


def rollback_batch(db: Session, batch_id: int, *, rolled_back_by: str = "local-user") -> dict:
    batch = db.query(ImportBatch).filter(ImportBatch.id == batch_id).first()
    if not batch:
        raise NotFoundException("导入批次不存在")
    if batch.status == ImportBatchStatus.ROLLED_BACK:
        raise BadRequestException("该导入批次已经回撤，不能重复操作")
    if batch.status != ImportBatchStatus.COMPLETED:
        raise BadRequestException("只有已执行完成的导入批次可以回撤")
    created_ids = set(batch.created_patent_ids or [])
    history_query = db.query(PatentHistory).filter(PatentHistory.import_batch_id == batch.id)
    if created_ids:
        history_query = history_query.filter(~PatentHistory.patent_id.in_(created_ids))
    histories = history_query.order_by(PatentHistory.id.desc()).all()
    patent_ids = {item.patent_id for item in histories} | created_ids
    patents = {item.id: item for item in db.query(Patent).filter(Patent.id.in_(patent_ids)).all()} if patent_ids else {}
    expected: dict[tuple[int, str], str | None] = {}
    for item in histories:
        expected.setdefault((item.patent_id, item.field_key), item.new_value)
    conflicts = []
    for (patent_id, key), expected_value in expected.items():
        if patent_id not in patents or current_value(patents[patent_id], key) != expected_value:
            conflicts.append({"patent_id": patent_id, "field_key": key, "expected_value": expected_value})
    if conflicts:
        raise BadRequestException("导入后已有后续修改，拒绝自动回撤，请先处理冲突", detail={"conflicts": conflicts})
    actor = rolled_back_by.strip() or "local-user"
    restored = 0
    for item in histories:
        patent = patents.get(item.patent_id)
        if not patent:
            continue
        old_current = current_value(patent, item.field_key)
        restore_value(patent, item.field_key, item.old_value)
        db.add(PatentHistory(
            patent_id=patent.id, field_key=item.field_key, field_display_name=item.field_display_name,
            old_value=old_current, new_value=item.old_value, source="import_revert", changed_by=actor,
            import_batch_id=batch.id, source_table_title=batch.source_table_title,
            source_row=item.source_row, source_field_name=item.source_field_name,
        ))
        restored += 1
    if created_ids:
        db.query(Citation).filter(or_(Citation.citing_patent_id.in_(created_ids), Citation.cited_patent_id.in_(created_ids))).delete(synchronize_session=False)
        for patent_id in created_ids:
            patent = patents.get(patent_id)
            if patent:
                db.delete(patent)
    batch.status = ImportBatchStatus.ROLLED_BACK
    batch.completed_at = utc_now_naive()
    db.commit()
    return {"batch_id": batch.id, "status": batch.status.value, "restored_value_count": restored, "deleted_patent_count": len(created_ids)}
