import threading
import uuid
import hashlib
import csv
import tempfile
import os
import time
from datetime import date, datetime
from pathlib import Path
from fastapi import APIRouter, Depends, UploadFile, File, Form, Query
from fastapi.responses import FileResponse, StreamingResponse
from sqlalchemy.orm import Session
from sqlalchemy import func, text, or_
from typing import Literal, Optional
import json
import pandas as pd
from io import BytesIO, StringIO
from pydantic import BaseModel

from app.database import get_db, SessionLocal, engine
from app.schemas.schemas import ImportBatchResponse, StatsResponse
from app.services.import_service import IMPORT_SKIP_FIELD, ImportService
from app.services.patent_service import PatentService
from app.services.field_registry import SYSTEM_FIELD_KEYS, get_all_fields_meta
from app.services.merge_service import merge_patent_data, _is_empty
from app.services.patent_identity_service import (
    backfill_patent_identifiers,
    ensure_patent_identifiers,
    find_patents_by_identifiers,
    identifier_specs_from_values,
)
from app.config import settings
from app.models import (
    CustomField,
    GovernanceDecision,
    GovernanceReversal,
    ImportBatch,
    ImportBatchStatus,
    ImportSourceRow,
    FieldObservation,
    Patent,
    PatentHistory,
)
from app.core.exceptions import BadRequestException, NotFoundException

router = APIRouter(tags=["import"])

SOURCE_DIR = settings.FILES_DIR / "imports"
SOURCE_DIR.mkdir(parents=True, exist_ok=True)
# 持久化到磁盘，避免后端重启或内存清理导致会话过期
TEMP_DIR = Path(tempfile.gettempdir()) / "patwiki_imports"
TEMP_DIR.mkdir(parents=True, exist_ok=True)
# 内存索引：import_id -> {"path": str, "filename": str, "created_at": float}
TEMP_FILES: dict[str, dict] = {}
TEMP_TTL = 6 * 3600  # 6小时过期


def _cleanup_expired():
    """定期清理过期的临时文件"""
    while True:
        try:
            now = time.time()
            expired = [k for k, v in TEMP_FILES.items() if now - v["created_at"] > TEMP_TTL]
            for k in expired:
                info = TEMP_FILES.pop(k, None)
                if info and os.path.exists(info["path"]):
                    try:
                        os.remove(info["path"])
                    except OSError:
                        pass
        except Exception:
            pass
        time.sleep(300)


threading.Thread(target=_cleanup_expired, daemon=True).start()


def _optimize_sqlite_connection(db: Session):
    if "sqlite" in str(engine.url):
        db.execute(text("PRAGMA journal_mode=WAL"))
        db.execute(text("PRAGMA synchronous=NORMAL"))
        db.execute(text("PRAGMA cache_size=-64000"))
        db.execute(text("PRAGMA temp_store=MEMORY"))
        db.execute(text("PRAGMA mmap_size=268435456"))


class FieldMappingItem(BaseModel):
    source_column: str
    target_field: str


class ConfirmImportRequest(BaseModel):
    import_id: str
    field_mappings: list[FieldMappingItem]
    dedupe_by: str = "both"
    update_on_duplicate: bool = True
    product_id: Optional[int] = None
    project_id: Optional[int] = None
    database_id: Optional[int] = None
    source_table_title: Optional[str] = None
    source_system: Optional[str] = None
    sheet_name: Optional[str] = None
    view_id: Optional[int] = None  # P0-14：导入到指定视图（为空则导入到库的主视图）


class GovernanceDecisionRequest(BaseModel):
    action: Literal["retain_source", "ignore", "map_existing", "propose_field"]
    canonical_field_key: Optional[str] = None
    apply_to_batch: bool = False
    adopted_value: bool = False
    decided_by: str = "local-user"
    reason: Optional[str] = None


class GovernanceRevertRequest(BaseModel):
    reversed_by: str = "local-user"
    reason: Optional[str] = None


@router.post("/import/preview")
async def preview_import(
    file: UploadFile = File(...),
    sheet_name: Optional[str] = Form(None),
    db: Session = Depends(get_db),
):
    content = await file.read()
    filename = file.filename or "upload.xlsx"
    sheets = ImportService.list_sheets(content, filename)
    selected_sheet = sheet_name or (sheets[0] if sheets else None)
    if selected_sheet and sheets and selected_sheet not in sheets:
        raise BadRequestException(f"Sheet 不存在：{selected_sheet}")
    df, columns = ImportService.parse_excel(content, filename, selected_sheet)
    suggested_mapping, mapping_issues = ImportService.suggest_mapping(columns, db)

    preview_rows_list = []
    for _, row in df.head(3).iterrows():
        preview_rows_list.append({str(k): str(v) for k, v in row.to_dict().items()})

    import_id = str(uuid.uuid4())
    # 持久化到磁盘文件，避免后端重启或内存清理导致会话过期
    temp_path = TEMP_DIR / f"{import_id}.bin"
    with open(temp_path, "wb") as f:
        f.write(content)
    safe_filename = "".join(ch if ch.isalnum() or ch in "._-" else "_" for ch in Path(filename).name)
    artifact_path = SOURCE_DIR / f"{import_id}_{safe_filename or 'upload.xlsx'}"
    artifact_path.write_bytes(content)
    file_hash = hashlib.sha256(content).hexdigest()
    TEMP_FILES[import_id] = {
        "path": str(temp_path),
        "filename": file.filename or "upload.xlsx",
        "created_at": time.time(),
        "artifact_path": str(artifact_path),
        "file_hash": file_hash,
    }

    from app.services.database_service import DatabaseService
    databases = DatabaseService.list_databases(db)
    default_db = DatabaseService.get_default_database(db)

    return {
        "import_id": import_id,
        "detected_columns": columns,
        "preview_rows": preview_rows_list,
        "total_rows": len(df),
        "suggested_mapping": suggested_mapping,
        "mapping_issues": mapping_issues,
        "unmapped_columns": [column for column in columns if not suggested_mapping.get(column)],
        "unmapped_count": sum(
            1 for column in columns if not suggested_mapping.get(column)
        ),
        "available_fields": get_all_fields_meta(db),
        "databases": [DatabaseService.to_dict(d) for d in databases],
        "default_database_id": default_db.id if default_db else None,
        "sheets": sheets,
        "selected_sheet": selected_sheet,
    }


def _apply_patent_update(patent: Patent, data: dict):
    custom_fields_data = data.pop("custom_fields", None)
    for field, value in data.items():
        if hasattr(patent, field) and not _is_empty(value):
            setattr(patent, field, value)
    if custom_fields_data:
        current = dict(patent.custom_fields or {})
        for k, v in custom_fields_data.items():
            if not _is_empty(v):
                current[k] = v
        patent.custom_fields = current


def _text_value(value):
    if value is None:
        return None
    if hasattr(value, "value"):
        value = value.value
    if isinstance(value, (datetime,)):
        return value.isoformat()
    if hasattr(value, "isoformat") and not isinstance(value, str):
        try:
            return value.isoformat()
        except Exception:
            pass
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False, default=str)
    return str(value)


def _raw_row_dict(row_dict: dict) -> dict:
    return {
        str(key): _text_value(value) if _text_value(value) is not None else ""
        for key, value in row_dict.items()
    }


def _row_hash(raw_row: dict) -> str:
    payload = json.dumps(raw_row, ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _candidate_value(field_key: str, patent_data: dict | None, virtual: dict) -> str | None:
    if not patent_data:
        return None
    if field_key == "family_members":
        return ", ".join(virtual.get("family_numbers") or [])
    if field_key == "cited_patents":
        return ", ".join(virtual.get("cited_numbers") or [])
    if field_key == "citing_patents":
        return ", ".join(virtual.get("citing_numbers") or [])
    custom = patent_data.get("custom_fields") or {}
    if field_key in custom:
        return _text_value(custom.get(field_key))
    return _text_value(patent_data.get(field_key))


def _current_value(patent: Patent | None, field_key: str) -> str | None:
    if patent is None or field_key in {"family_members", "cited_patents", "citing_patents"}:
        return None
    custom = patent.custom_fields or {}
    if field_key in custom:
        return _text_value(custom.get(field_key))
    return _text_value(getattr(patent, field_key, None))


def _snapshot_values(patent: Patent | None, mapping: dict[str, str]) -> dict[str, str | None]:
    if patent is None:
        return {}
    return {
        target: _current_value(patent, target)
        for target in set(mapping.values())
        if target and target != IMPORT_SKIP_FIELD
    }


def _difference_type(current: str | None, candidate: str | None) -> str:
    if candidate is None or candidate == "":
        return "unknown"
    if current is None or current == "":
        return "new"
    if current == candidate:
        return "same"
    if current.strip() == candidate.strip():
        return "format"
    return "content"


def _record_field_observations(
    db: Session,
    batch: ImportBatch,
    source_row: ImportSourceRow,
    row_dict: dict,
    columns: list[str],
    mapping: dict[str, str],
    patent: Patent | None,
    patent_data: dict | None,
    virtual: dict | None,
    before_values: dict[str, str | None],
    resolution_status: str,
    final_decision: str | None = None,
) -> int:
    virtual = virtual or {}
    unknown_count = 0
    raw_row = _raw_row_dict(row_dict)
    for column_index, column in enumerate(columns):
        raw_value = raw_row.get(column, "")
        if raw_value == "":
            continue
        target = (mapping.get(column) or "").strip()
        if target == IMPORT_SKIP_FIELD:
            continue
        if not target:
            unknown_count += 1
            db.add(FieldObservation(
                import_batch_id=batch.id,
                source_row_id=source_row.id,
                patent_id=patent.id if patent else None,
                source_field_name=column,
                source_column_index=column_index,
                raw_value=raw_value,
                normalized_value=raw_value,
                candidate_value=raw_value,
                difference_type="unknown",
                field_resolution="unmapped_retained",
                proposed_action="retain",
            ))
            continue

        candidate = _candidate_value(target, patent_data, virtual)
        current_before = before_values.get(target)
        current_after = _current_value(patent, target)
        difference = "quarantined" if resolution_status == "quarantined" else _difference_type(current_before, candidate)
        action = "quarantine" if resolution_status == "quarantined" else {
            "new": "fill",
            "same": "keep",
            "format": "keep",
            "content": "update",
            "unknown": "retain",
        }.get(difference, "retain")
        decision = final_decision
        if decision is None and resolution_status == "resolved":
            decision = "adopted" if difference in {"new", "content"} else "kept"
        db.add(FieldObservation(
            import_batch_id=batch.id,
            source_row_id=source_row.id,
            patent_id=patent.id if patent else None,
            source_field_name=column,
            source_column_index=column_index,
            canonical_field_key=target,
            raw_value=raw_value,
            normalized_value=candidate or raw_value,
            current_value=current_after,
            candidate_value=candidate or raw_value,
            difference_type=difference,
            field_resolution="quarantined" if resolution_status == "quarantined" else "mapped",
            proposed_action=action,
            final_decision=decision,
        ))
        if patent:
            db.add(PatentHistory(
                patent_id=patent.id,
                field_key=target,
                field_display_name=column,
                old_value=current_before,
                new_value=candidate or raw_value,
                source="import",
                changed_by="import",
                import_batch_id=batch.id,
                source_table_title=batch.source_table_title,
                source_row=source_row.source_row,
                source_field_name=column,
            ))
    return unknown_count
@router.post("/import/confirm")
def confirm_import(
    req: ConfirmImportRequest,
    db: Session = Depends(get_db),
):
    # 从磁盘读取会话文件（不再依赖内存索引，避免后端重启导致会话丢失）
    temp_path = TEMP_DIR / f"{req.import_id}.bin"
    if not temp_path.exists():
        raise BadRequestException("导入会话已过期或文件不存在，请重新上传文件")
    # 基于文件 mtime 检查 TTL，避免后端重启后 created_at 被重置
    file_mtime = temp_path.stat().st_mtime
    if time.time() - file_mtime > TEMP_TTL:
        try:
            os.remove(temp_path)
        except OSError:
            pass
        raise BadRequestException(f"导入会话已过期（超过{TEMP_TTL // 3600}小时），请重新上传文件")
    # 同步内存索引（便于 /import/batches 等查询）
    info = TEMP_FILES.get(req.import_id)
    if not info:
        info = {
            "path": str(temp_path),
            "filename": "upload.xlsx",
            "created_at": file_mtime,
        }
        TEMP_FILES[req.import_id] = info

    database_id = req.database_id
    if database_id is None:
        from app.services.database_service import DatabaseService
        default_db = DatabaseService.get_default_database(db)
        if not default_db:
            raise BadRequestException("未指定库且系统无默认库，请先创建库")
        database_id = default_db.id
    else:
        from app.services.database_service import DatabaseService
        if not DatabaseService.get_database(db, database_id):
            raise BadRequestException(f"库不存在：{database_id}")

    with open(info["path"], "rb") as f:
        content = f.read()
    filename = info["filename"]
    artifact_path = info.get("artifact_path")
    if not artifact_path or not Path(artifact_path).exists():
        safe_filename = "".join(ch if ch.isalnum() or ch in "._-" else "_" for ch in Path(filename).name)
        artifact_path = str(SOURCE_DIR / f"{req.import_id}_{safe_filename or 'upload.xlsx'}")
        Path(artifact_path).write_bytes(content)
    file_hash = hashlib.sha256(content).hexdigest()

    mapping = {m.source_column: (m.target_field or "").strip() for m in req.field_mappings}

    errors = []
    inserted = 0
    updated = 0
    duplicates_count = 0
    skipped = 0
    error_count = 0
    family_links = 0
    citation_links = 0
    identity_conflicts = 0
    identity_index_report: dict = {"indexed": 0, "conflicts": []}
    BATCH_SIZE = 500
    batch: ImportBatch | None = None

    try:
        _optimize_sqlite_connection(db)

        batch = ImportBatch(
            filename=filename,
            source_table_title=(req.source_table_title or Path(filename).stem),
            worksheet_name=req.sheet_name,
            source_system=req.source_system,
            mapping_version="v1",
            file_hash=file_hash,
            artifact_path=str(artifact_path),
            status=ImportBatchStatus.PROCESSING,
            started_at=datetime.utcnow(),
        )
        db.add(batch)
        db.flush()

        df, columns = ImportService.parse_excel(content, filename, req.sheet_name)
        mapping_issues = ImportService.validate_mapping(columns, mapping, db)
        if mapping_issues:
            raise BadRequestException("导入已阻止：请解决所有字段映射问题后再导入", detail={
                "mapping_issues": mapping_issues,
            })
        total_rows = len(df)
        batch.total_rows = total_rows
        print(f"[PatWiki] 开始导入 {total_rows} 条数据...", flush=True)

        # Field mappings may only point to registered fields. Empty targets retain
        # source evidence for governance; the explicit skip marker bypasses only
        # the observation queue and never alters the raw source row.
        db.commit()

        custom_fields_cache = {cf.key: cf for cf in db.query(CustomField).all()}

        rows_data = []
        row_reports: list[dict] = []
        source_rows: dict[int, ImportSourceRow] = {}
        unmapped_retained = 0
        for idx, (_, row) in enumerate(df.iterrows()):
            row_dict = _raw_row_dict(row.to_dict())
            source_row = ImportSourceRow(
                import_batch_id=batch.id,
                source_row=idx + 2,
                raw_row=row_dict,
                row_hash=_row_hash(row_dict),
            )
            db.add(source_row)
            db.flush()
            source_rows[idx] = source_row
            try:
                patent_data, virtual = ImportService._row_to_patent_data(
                    row_dict, mapping, db, custom_fields_cache=custom_fields_cache
                )
                patent_data["database_id"] = database_id
                # P0-14：支持导入到指定视图
                if req.view_id:
                    patent_data["view_id"] = req.view_id
                if req.product_id:
                    patent_data["product_id"] = req.product_id
                country = patent_data.get("country", "CN")
                app_num = (patent_data.get("application_number") or "").strip()
                pub_num = (patent_data.get("publication_number") or "").strip()
                rows_data.append({
                    "idx": idx,
                    "patent_data": patent_data,
                    "virtual": virtual,
                    "country": country,
                    "app_num": app_num,
                    "pub_num": pub_num,
                    "identity_specs": identifier_specs_from_values(
                        {
                            "application": patent_data.get("application_number"),
                            "publication": patent_data.get("publication_number"),
                            "grant": patent_data.get("grant_number"),
                        },
                        country,
                    ),
                    "row_num": idx + 2,
                })
            except Exception as e:
                source_row.resolution_status = "quarantined"
                source_row.resolution_reason = str(e)
                unmapped_retained += _record_field_observations(
                    db, batch, source_row, row_dict, columns, mapping,
                    None, None, None, {}, "quarantined", "quarantined",
                )
                report = {"row": idx + 2, "status": "error_mapping", "reason": str(e)}
                errors.append(report)
                row_reports.append(report)
                error_count += 1

        # 旧库可能只有 Patent 的兼容号码字段；先补建统一身份索引。
        # 冲突只作为诊断返回，不自动合并或改写历史记录。
        identity_index_report = backfill_patent_identifiers(db)

        all_app_nums: dict[tuple[str, str], Patent] = {}
        all_pub_nums: dict[tuple[str, str], Patent] = {}

        # SQLite 单条 SQL 的表达式树深度上限约为 1000；当导入数千行时，
        # 直接拼接 `or_(num==x AND country==y, ...)` 会触发
        # "Expression tree is too large (maximum depth 1000)"。
        # 改为：先用 IN 子句分批捞候选记录（每批 ≤ 500 个参数，远低于 SQLite
        # SQLITE_MAX_VARIABLE_NUMBER 默认 999 上限），再在内存里按 (num, country)
        # 精确匹配，避免 SQL 表达式爆炸。
        app_pairs = {(rd["app_num"], rd["country"]) for rd in rows_data if rd["app_num"]}
        pub_pairs = {(rd["pub_num"], rd["country"]) for rd in rows_data if rd["pub_num"]}

        DEDUP_CHUNK = 500

        if app_pairs:
            app_nums_set = {num for num, _ in app_pairs}
            app_nums_list = list(app_nums_set)
            for i in range(0, len(app_nums_list), DEDUP_CHUNK):
                chunk = app_nums_list[i:i + DEDUP_CHUNK]
                existing_patents = db.query(Patent).filter(
                    Patent.database_id == database_id,
                    Patent.application_number.in_(chunk),
                ).all()
                for p in existing_patents:
                    if p.application_number:
                        key = (p.application_number.strip(), p.country or "CN")
                        if key in app_pairs:
                            all_app_nums[key] = p

        if pub_pairs:
            pub_nums_set = {num for num, _ in pub_pairs}
            pub_nums_list = list(pub_nums_set)
            for i in range(0, len(pub_nums_list), DEDUP_CHUNK):
                chunk = pub_nums_list[i:i + DEDUP_CHUNK]
                existing_patents_pub = db.query(Patent).filter(
                    Patent.database_id == database_id,
                    Patent.publication_number.in_(chunk),
                ).all()
                for p in existing_patents_pub:
                    if p.publication_number:
                        key = (p.publication_number.strip(), p.country or "CN")
                        if key in pub_pairs:
                            all_pub_nums[key] = p

        print(f"[PatWiki] 预查重完成: 库中已有申请号记录 {len(all_app_nums)} 条, 公开号记录 {len(all_pub_nums)} 条", flush=True)

        seen_app_nums: set[tuple[str, str]] = set()
        seen_pub_nums: set[tuple[str, str]] = set()
        pending_relations: list[tuple[Patent, dict]] = []
        imported_patent_ids: set[int] = set()

        for i, rd in enumerate(rows_data):
            source_row = source_rows[rd["idx"]]
            identity_matches = find_patents_by_identifiers(db, rd["identity_specs"])
            if len(identity_matches) > 1:
                identity_conflicts += 1
                source_row.resolution_status = "quarantined"
                source_row.resolution_reason = (
                    "一个导入行的申请号/公开号/授权号分别命中多个专利，已隔离等待人工确认"
                )
                source_row.candidate_patent_ids = [patent.id for patent in identity_matches]
                unmapped_retained += _record_field_observations(
                    db, batch, source_row, source_row.raw_row, columns, mapping,
                    None, rd["patent_data"], rd["virtual"], {},
                    "quarantined", "identity_conflict",
                )
                row_reports.append({
                    "row": rd["row_num"],
                    "status": "identity_conflict",
                    "reason": source_row.resolution_reason,
                    "candidate_patent_ids": [patent.id for patent in identity_matches],
                })
                continue
            try:
                with db.begin_nested():
                    patent_data = rd["patent_data"]
                    before_values: dict[str, str | None] = {}
                    adoption_decision: str | None = None
                    current_patent = None
                    virtual = rd["virtual"]
                    country = rd["country"]
                    app_num = rd["app_num"]
                    pub_num = rd["pub_num"]

                    if not patent_data.get("title"):
                        skipped += 1
                        row_reports.append({"row": rd["row_num"], "status": "skipped_missing_title", "reason": "标题为空，无法创建专利"})
                    else:
                        existing = identity_matches[0] if identity_matches else None
                        if req.dedupe_by in ("both", "application_number") and app_num:
                            key = (app_num, country)
                            existing = existing or all_app_nums.get(key)
                        if not existing and req.dedupe_by in ("both", "publication_number") and pub_num:
                            key = (pub_num, country)
                            existing = all_pub_nums.get(key)

                        current_patent = None
                        if existing:
                            before_values = _snapshot_values(existing, mapping)
                            duplicates_count += 1
                            if req.update_on_duplicate:
                                merged = merge_patent_data(existing, patent_data)
                                _apply_patent_update(existing, merged)
                                updated += 1
                                current_patent = existing
                                row_reports.append({"row": rd["row_num"], "status": "updated_duplicate", "reason": "与已有专利重复，已按字段合并更新", "patent_id": existing.id})
                            else:
                                skipped += 1
                                current_patent = existing
                                row_reports.append({"row": rd["row_num"], "status": "skipped_duplicate", "reason": "与已有专利重复，已按设置跳过", "patent_id": existing.id})
                                adoption_decision = "kept"
                        else:
                            is_batch_dup = False
                            if app_num and (app_num, country) in seen_app_nums:
                                is_batch_dup = True
                            if pub_num and (pub_num, country) in seen_pub_nums:
                                is_batch_dup = True

                            if is_batch_dup:
                                existing_in_batch = None
                                if app_num:
                                    existing_in_batch = all_app_nums.get((app_num, country))
                                if not existing_in_batch and pub_num:
                                    existing_in_batch = all_pub_nums.get((pub_num, country))
                                if existing_in_batch:
                                    duplicates_count += 1
                                    if req.update_on_duplicate:
                                        merged = merge_patent_data(existing_in_batch, patent_data)
                                        before_values = _snapshot_values(existing_in_batch, mapping)
                                        _apply_patent_update(existing_in_batch, merged)
                                        updated += 1
                                        current_patent = existing_in_batch
                                        row_reports.append({"row": rd["row_num"], "status": "updated_duplicate", "reason": "与本次导入的前一行重复，已合并更新", "patent_id": existing_in_batch.id})
                                    else:
                                        skipped += 1
                                        current_patent = existing_in_batch
                                        row_reports.append({"row": rd["row_num"], "status": "skipped_duplicate", "reason": "与本次导入的前一行重复，已按设置跳过", "patent_id": existing_in_batch.id})
                                        adoption_decision = "kept"
                                else:
                                    skipped += 1
                                    row_reports.append({"row": rd["row_num"], "status": "skipped_duplicate", "reason": "与本次导入的前一行重复，但未能定位到目标记录"})
                            else:
                                if app_num:
                                    seen_app_nums.add((app_num, country))
                                if pub_num:
                                    seen_pub_nums.add((pub_num, country))
                                if batch is not None:
                                    patent_data["source_batch_id"] = batch.id
                                custom_fields = patent_data.pop("custom_fields", {}) or {}
                                patent = Patent(**patent_data)
                                patent.custom_fields = custom_fields
                                db.add(patent)
                                db.flush()
                                patent_data["custom_fields"] = custom_fields
                                inserted += 1
                                current_patent = patent
                                row_reports.append({"row": rd["row_num"], "status": "created", "reason": "已创建", "patent_id": patent.id})
                                if app_num:
                                    all_app_nums[(app_num, country)] = patent
                                if pub_num:
                                    all_pub_nums[(pub_num, country)] = patent

                        if current_patent is not None:
                            ensure_patent_identifiers(
                                db,
                                current_patent,
                                additional_specs=rd["identity_specs"],
                                source_system=req.source_system or "import",
                                source_timestamp=datetime.utcnow(),
                            )
                            source_row.patent_id = current_patent.id
                            source_row.resolution_status = "resolved"
                            unknown_in_row = _record_field_observations(
                                db, batch, source_row, source_row.raw_row, columns, mapping,
                                current_patent, patent_data, virtual, before_values,
                                "resolved", adoption_decision,
                            )
                            unmapped_retained += unknown_in_row
                            source_row.resolution_reason = (
                                "mapped; unknown properties retained"
                                if unknown_in_row else "mapped"
                            )
                            imported_patent_ids.add(current_patent.id)
                            has_rel = virtual["family_numbers"] or virtual["cited_numbers"] or virtual["citing_numbers"]
                            if has_rel:
                                pending_relations.append((current_patent, virtual))
                        else:
                            source_row.resolution_status = "unmapped_retained"
                            source_row.resolution_reason = "no patent identity was resolved; raw row retained"
                            unmapped_retained += _record_field_observations(
                                db, batch, source_row, source_row.raw_row, columns, mapping,
                                None, patent_data, virtual, before_values,
                                "unmapped_retained", "retained",
                            )

                if (i + 1) % BATCH_SIZE == 0:
                    db.commit()
                    for cp, vv in pending_relations:
                        try:
                            relation_result = _process_relations(db, cp, vv, database_id)
                            family_links += relation_result["family_links"]
                            citation_links += relation_result["citation_links"]
                        except Exception as rel_err:
                            # 关系处理失败后 session 处于 rollback-pending 状态，
                            # 必须回滚才能继续后续操作，否则会级联抛出 PendingRollbackError。
                            print(f"[PatWiki] 关系处理警告(patent_id={cp.id}): {rel_err}", flush=True)
                            db.rollback()
                    db.commit()
                    pending_relations.clear()
                    progress = i + 1
                    pct = int(progress / total_rows * 100) if total_rows > 0 else 100
                    print(f"[PatWiki] 已处理 {progress}/{total_rows} ({pct}%) 新增:{inserted} 更新:{updated} 跳过:{skipped} 错误:{error_count}", flush=True)

            except Exception as e:
                source_row = source_rows[rd["idx"]]
                source_row.resolution_status = "quarantined"
                source_row.resolution_reason = str(e)
                unmapped_retained += _record_field_observations(
                    db, batch, source_row, source_row.raw_row, columns, mapping,
                    None, rd["patent_data"], rd["virtual"], {}, "quarantined", "quarantined",
                )
                report = {"row": rd["row_num"], "status": "error_database", "reason": str(e)}
                errors.append(report)
                row_reports.append(report)
                error_count += 1
                if error_count <= 10:
                    print(f"[PatWiki] 第 {rd['row_num']} 行错误: {e}", flush=True)

        db.commit()
        for cp, vv in pending_relations:
            try:
                relation_result = _process_relations(db, cp, vv, database_id)
                family_links += relation_result["family_links"]
                citation_links += relation_result["citation_links"]
            except Exception as rel_err:
                print(f"[PatWiki] 关系处理警告(patent_id={cp.id}): {rel_err}", flush=True)
                db.rollback()
        db.commit()

        print(f"[PatWiki] 导入完成: 新增:{inserted} 更新:{updated} 跳过:{skipped} 错误:{error_count}", flush=True)

        # 导入可能一次修改多个依赖字段，统一按库重算公式，避免逐行重复计算。
        from app.services.formula_service import FormulaService
        FormulaService.recalculate_all(db, database_id=database_id)

        from app.services.automation_service import AutomationEngine
        for imported_patent_id in imported_patent_ids:
            AutomationEngine.on_event(
                db,
                "record_imported",
                patent_id=imported_patent_id,
            )

        if database_id is not None:
            from app.services.database_service import DatabaseService
            DatabaseService.refresh_patent_count(db, database_id)
        if batch is not None:
            batch.processed_rows = total_rows
            batch.inserted_count = inserted
            batch.updated_count = updated
            batch.skipped_count = skipped
            batch.duplicate_count = duplicates_count
            batch.error_count = error_count
            batch.errors = [report for report in row_reports if report["status"] != "created"] or None
            batch.mapping_config = mapping
            batch.status = ImportBatchStatus.COMPLETED
            batch.completed_at = datetime.utcnow()
            db.add(batch)
            db.commit()
    except Exception as exc:
        # session 可能因前面的 IntegrityError 处于 rollback-pending 状态，
        # 必须先 rollback 才能写入批次失败状态，否则访问 batch 属性会再次
        # 抛出 PendingRollbackError，导致批次永远停留在 PROCESSING。
        db.rollback()
        if batch is not None:
            batch.status = ImportBatchStatus.FAILED
            batch.processed_rows = min(batch.total_rows or 0, inserted + updated + skipped + error_count)
            batch.error_count = max(error_count, 1)
            batch.errors = [*errors[:19], {"error": str(exc)}]
            batch.completed_at = datetime.utcnow()
            db.add(batch)
            db.commit()
        raise
    finally:
        info = TEMP_FILES.pop(req.import_id, None)
        if info and os.path.exists(info["path"]):
            try:
                os.remove(info["path"])
            except OSError:
                pass

    return {
        "total": total_rows,
        "created": inserted,
        "updated": updated,
        "skipped": skipped,
        "errors": error_count,
        "error_details": errors,
        "row_reports": row_reports,
        "database_id": database_id,
        "family_links": family_links,
        "citation_links": citation_links,
        "identity_conflicts": identity_conflicts,
        "identity_index": identity_index_report,
        "unmapped_retained": unmapped_retained,
        "unknown_columns": [
            column for column in columns
            if not mapping.get(column) and mapping.get(column) != IMPORT_SKIP_FIELD
        ],
        "batch_id": batch.id if batch is not None else None,
    }


@router.get("/import/batches", response_model=list[ImportBatchResponse])
def list_import_batches(
    status: Optional[str] = None,
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
):
    query = db.query(ImportBatch)
    if status:
        try:
            query = query.filter(ImportBatch.status == ImportBatchStatus(status))
        except ValueError as exc:
            raise BadRequestException(f"不支持的导入状态：{status}") from exc
    return query.order_by(ImportBatch.created_at.desc(), ImportBatch.id.desc()).limit(limit).all()


@router.get("/import/batches/{batch_id}", response_model=ImportBatchResponse)
def get_import_batch(batch_id: int, db: Session = Depends(get_db)):
    batch = db.query(ImportBatch).filter(ImportBatch.id == batch_id).first()
    if not batch:
        raise NotFoundException("导入批次不存在")
    return batch


def _unmapped_observation_query(
    db: Session,
    batch_id: Optional[int] = None,
    source_field: Optional[str] = None,
    patent_id: Optional[int] = None,
    source_row_id: Optional[int] = None,
    status: Optional[str] = "unmapped_retained",
):
    query = (
        db.query(FieldObservation, ImportSourceRow, ImportBatch)
        .join(ImportSourceRow, FieldObservation.source_row_id == ImportSourceRow.id)
        .join(ImportBatch, FieldObservation.import_batch_id == ImportBatch.id)
    )
    if batch_id is not None:
        query = query.filter(FieldObservation.import_batch_id == batch_id)
    if source_field:
        query = query.filter(FieldObservation.source_field_name == source_field)
    if patent_id is not None:
        query = query.filter(FieldObservation.patent_id == patent_id)
    if source_row_id is not None:
        query = query.filter(FieldObservation.source_row_id == source_row_id)
    if status and status != "all":
        query = query.filter(FieldObservation.field_resolution == status)
    return query


def _observation_to_dict(observation: FieldObservation, source_row: ImportSourceRow, batch: ImportBatch) -> dict:
    return {
        "id": observation.id,
        "batch_id": batch.id,
        "filename": batch.filename,
        "source_table_title": batch.source_table_title,
        "worksheet_name": batch.worksheet_name,
        "source_row_id": source_row.id,
        "source_row": source_row.source_row,
        "patent_id": observation.patent_id,
        "candidate_patent_ids": source_row.candidate_patent_ids or [],
        "source_field_name": observation.source_field_name,
        "source_column_index": observation.source_column_index,
        "canonical_field_key": observation.canonical_field_key,
        "raw_value": observation.raw_value,
        "normalized_value": observation.normalized_value,
        "current_value": observation.current_value,
        "candidate_value": observation.candidate_value,
        "difference_type": observation.difference_type,
        "field_resolution": observation.field_resolution,
        "proposed_action": observation.proposed_action,
        "final_decision": observation.final_decision,
        "decided_by": observation.decided_by,
        "decided_at": observation.decided_at.isoformat() if observation.decided_at else None,
        "source_row_values": source_row.raw_row,
        "created_at": observation.created_at.isoformat() if observation.created_at else None,
    }


def _governance_field_meta(db: Session, field_key: str) -> dict:
    field = next((item for item in get_all_fields_meta(db) if item.get("key") == field_key), None)
    if not field:
        raise BadRequestException(f"目标字段不存在：{field_key}")
    if not field.get("editable", True) or field_key in {"id", "created_at", "updated_at"}:
        raise BadRequestException(f"目标字段不可编辑：{field_key}")
    return field


def _coerce_governance_value(field_key: str, value: str):
    if field_key in {"filing_date", "publication_date", "grant_date", "priority_date", "legal_status_date"}:
        try:
            return date.fromisoformat(value[:10])
        except ValueError as exc:
            raise BadRequestException(
                f"来源值无法写入日期字段 {field_key}：{value}"
            ) from exc
    if field_key == "has_risk":
        return value.strip().lower() in {"1", "true", "yes", "y", "是", "有"}
    return value


def _write_governance_value(patent: Patent, field_key: str, value: str) -> tuple[str | None, str]:
    """Write an explicitly adopted observation value and return old/new text."""
    old_value = _current_value(patent, field_key)
    coerced = _coerce_governance_value(field_key, value)
    if field_key in SYSTEM_FIELD_KEYS:
        setattr(patent, field_key, coerced)
    else:
        current = dict(patent.custom_fields or {})
        current[field_key] = coerced
        patent.custom_fields = current
    return old_value, _text_value(coerced) or ""


def _restore_governance_value(patent: Patent, field_key: str, value: str | None) -> None:
    """Restore a value captured by a governance decision without deleting history."""
    if field_key in SYSTEM_FIELD_KEYS:
        setattr(patent, field_key, None if value is None else _coerce_governance_value(field_key, value))
        return
    current = dict(patent.custom_fields or {})
    if value is None:
        current.pop(field_key, None)
    else:
        current[field_key] = value
    patent.custom_fields = current


@router.patch("/import/observations/{observation_id}")
def decide_import_observation(
    observation_id: int,
    req: GovernanceDecisionRequest,
    db: Session = Depends(get_db),
):
    observation = db.query(FieldObservation).filter(FieldObservation.id == observation_id).first()
    if not observation:
        raise NotFoundException("待治理字段观察不存在")

    target_field = req.canonical_field_key.strip() if req.canonical_field_key else None
    if req.action == "map_existing":
        if not target_field:
            raise BadRequestException("映射已有字段时必须指定 canonical_field_key")
        target_field_meta = _governance_field_meta(db, target_field)
    elif target_field:
        raise BadRequestException("当前动作不接受 canonical_field_key")

    query = db.query(FieldObservation).filter(FieldObservation.id == observation_id)
    if req.apply_to_batch:
        query = db.query(FieldObservation).filter(
            FieldObservation.import_batch_id == observation.import_batch_id,
            FieldObservation.source_field_name == observation.source_field_name,
            FieldObservation.field_resolution.in_(["unmapped_retained", "candidate"]),
        )
    targets = query.order_by(FieldObservation.id.asc()).all()
    batch = db.query(ImportBatch).filter(ImportBatch.id == observation.import_batch_id).first()
    if not batch:
        raise NotFoundException("导入批次不存在")

    source_rows = {
        row.id: row
        for row in db.query(ImportSourceRow).filter(
            ImportSourceRow.id.in_({target.source_row_id for target in targets})
        ).all()
    }
    patents = {
        patent.id: patent
        for patent in db.query(Patent).filter(
            Patent.id.in_({target.patent_id for target in targets if target.patent_id})
        ).all()
    }
    if req.action == "map_existing":
        # Validate every candidate before mutating observations or patents so a
        # malformed batch remains entirely retryable.
        for target in targets:
            if target.normalized_value:
                _coerce_governance_value(target_field, target.normalized_value)

    resolution_by_action = {
        "retain_source": ("source_only", "retained"),
        "ignore": ("ignored", "ignored"),
        "map_existing": ("mapped", "mapped"),
        "propose_field": ("candidate", "proposed"),
    }
    field_resolution, final_decision = resolution_by_action[req.action]
    decision_batch_id = uuid.uuid4().hex
    changed_values = 0
    updated_items = []

    for target in targets:
        before_field_resolution = target.field_resolution
        before_final_decision = target.final_decision
        before_proposed_action = target.proposed_action
        before_canonical_field_key = target.canonical_field_key
        before_decided_by = target.decided_by
        before_decided_at = target.decided_at
        decision_canonical_field_key = (
            target_field if req.action == "map_existing" else target.canonical_field_key
        )
        patent = patents.get(target.patent_id) if req.action == "map_existing" else None
        patent_value_before = _current_value(patent, target_field) if patent else None
        patent_value_after = None
        patent_value_changed = False

        target_field_for_observation = target_field if req.action == "map_existing" else target.canonical_field_key
        target.canonical_field_key = target_field_for_observation
        target.field_resolution = field_resolution
        target.final_decision = final_decision
        target.proposed_action = req.action
        target.decided_by = req.decided_by.strip() or "local-user"
        target.decided_at = datetime.utcnow()

        if req.action == "map_existing" and target.patent_id and target.normalized_value:
            if patent:
                current = _current_value(patent, target_field)
                candidate = target.normalized_value
                should_adopt = req.adopted_value and candidate != ""
                should_fill = not current and candidate != ""
                if should_adopt or should_fill:
                    old_value, new_value = _write_governance_value(patent, target_field, candidate)
                    if old_value != new_value:
                        source_row = source_rows.get(target.source_row_id)
                        db.add(PatentHistory(
                            patent_id=patent.id,
                            field_key=target_field,
                            field_display_name=target_field_meta.get("name") or target_field,
                            old_value=old_value,
                            new_value=new_value,
                            source="governance",
                            changed_by=target.decided_by,
                            import_batch_id=batch.id,
                            source_table_title=batch.source_table_title,
                            source_row=source_row.source_row if source_row else None,
                            source_field_name=target.source_field_name,
                        ))
                        changed_values += 1
                        patent_value_after = new_value
                        patent_value_changed = True

        db.add(GovernanceDecision(
            observation_id=target.id,
            decision_batch_id=decision_batch_id,
            action=req.action,
            scope="batch_source_field" if req.apply_to_batch else "single",
            canonical_field_key=decision_canonical_field_key,
            mapping_version=batch.mapping_version,
            before_field_resolution=before_field_resolution,
            before_final_decision=before_final_decision,
            before_proposed_action=before_proposed_action,
            before_canonical_field_key=before_canonical_field_key,
            before_decided_by=before_decided_by,
            before_decided_at=before_decided_at,
            patent_id=patent.id if patent else None,
            patent_field_key=target_field if patent else None,
            patent_value_before=patent_value_before,
            patent_value_after=patent_value_after,
            patent_value_changed=patent_value_changed,
            adopted_value=req.adopted_value,
            decided_by=target.decided_by,
            reason=req.reason,
        ))
        source_row = source_rows.get(target.source_row_id)
        if source_row:
            updated_items.append(_observation_to_dict(target, source_row, batch))

    try:
        db.commit()
    except Exception:
        db.rollback()
        raise
    return {
        "action": req.action,
        "scope": "batch_source_field" if req.apply_to_batch else "single",
        "decision_batch_id": decision_batch_id,
        "updated_count": len(targets),
        "adopted_value_count": changed_values,
        "items": updated_items,
    }


@router.get("/import/governance/batches")
def list_governance_batches(
    offset: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
):
    grouped = (
        db.query(
            GovernanceDecision.decision_batch_id.label("batch_id"),
            func.count(GovernanceDecision.id).label("decision_count"),
            func.min(GovernanceDecision.created_at).label("created_at"),
            func.max(GovernanceDecision.id).label("last_decision_id"),
        )
        .filter(GovernanceDecision.decision_batch_id.isnot(None))
        .group_by(GovernanceDecision.decision_batch_id)
    )
    total = db.query(func.count(func.distinct(GovernanceDecision.decision_batch_id))).filter(
        GovernanceDecision.decision_batch_id.isnot(None)
    ).scalar() or 0
    rows = grouped.order_by(func.max(GovernanceDecision.id).desc()).offset(offset).limit(limit).all()
    items = []
    for row in rows:
        first = db.query(GovernanceDecision).filter(
            GovernanceDecision.decision_batch_id == row.batch_id,
        ).order_by(GovernanceDecision.id.asc()).first()
        reversal = db.query(GovernanceReversal).filter(
            GovernanceReversal.decision_batch_id == row.batch_id,
        ).order_by(GovernanceReversal.id.desc()).first()
        items.append({
            "decision_batch_id": row.batch_id,
            "decision_count": row.decision_count,
            "action": first.action if first else None,
            "scope": first.scope if first else None,
            "mapping_version": first.mapping_version if first else None,
            "decided_by": first.decided_by if first else None,
            "created_at": row.created_at.isoformat() if row.created_at else None,
            "reversed": reversal is not None,
            "reversal_reason": reversal.reason if reversal else None,
            "reversed_at": reversal.created_at.isoformat() if reversal and reversal.created_at else None,
        })
    return {"total": total, "offset": offset, "limit": limit, "items": items}


@router.post("/import/governance/batches/{decision_batch_id}/revert")
def revert_governance_batch(
    decision_batch_id: str,
    req: GovernanceRevertRequest,
    db: Session = Depends(get_db),
):
    decisions = db.query(GovernanceDecision).filter(
        GovernanceDecision.decision_batch_id == decision_batch_id,
    ).order_by(GovernanceDecision.id.asc()).all()
    if not decisions:
        raise NotFoundException("治理决策批次不存在")
    if db.query(GovernanceReversal).filter(
        GovernanceReversal.decision_batch_id == decision_batch_id,
    ).first():
        raise BadRequestException("该治理决策批次已经恢复，不能重复操作")

    after_state = {
        "retain_source": ("source_only", "retained"),
        "ignore": ("ignored", "ignored"),
        "map_existing": ("mapped", "mapped"),
        "propose_field": ("candidate", "proposed"),
    }
    observation_ids = {decision.observation_id for decision in decisions}
    observations = {
        item.id: item
        for item in db.query(FieldObservation).filter(FieldObservation.id.in_(observation_ids)).all()
    }
    for decision in decisions:
        observation = observations.get(decision.observation_id)
        if not observation:
            raise BadRequestException("治理批次引用的来源观察已不存在，无法安全恢复")
        latest = db.query(GovernanceDecision).filter(
            GovernanceDecision.observation_id == decision.observation_id,
        ).order_by(GovernanceDecision.id.desc()).first()
        if not latest or latest.id != decision.id:
            raise BadRequestException("治理批次中的观察已有后续决策，请先处理后续变更")
        expected_resolution, expected_final = after_state[decision.action]
        if (
            observation.field_resolution != expected_resolution
            or observation.final_decision != expected_final
            or observation.proposed_action != decision.action
            or observation.canonical_field_key != decision.canonical_field_key
        ):
            raise BadRequestException("治理批次中的观察已发生后续修改，拒绝覆盖")

    patents = {
        item.id: item
        for item in db.query(Patent).filter(
            Patent.id.in_({decision.patent_id for decision in decisions if decision.patent_id})
        ).all()
    }
    latest_values = {}
    for decision in decisions:
        if decision.patent_value_changed and decision.patent_id and decision.patent_field_key:
            latest_values[(decision.patent_id, decision.patent_field_key)] = decision.patent_value_after
    for (patent_id, field_key), expected_value in latest_values.items():
        patent = patents.get(patent_id)
        if not patent or (_current_value(patent, field_key) or "") != (expected_value or ""):
            raise BadRequestException("专利字段已被后续修改，拒绝覆盖；请人工确认后再恢复")

    restored_values = 0
    for decision in reversed(decisions):
        observation = observations[decision.observation_id]
        observation.field_resolution = decision.before_field_resolution
        observation.final_decision = decision.before_final_decision
        observation.proposed_action = decision.before_proposed_action
        observation.canonical_field_key = decision.before_canonical_field_key
        observation.decided_by = decision.before_decided_by
        observation.decided_at = decision.before_decided_at

        if decision.patent_value_changed and decision.patent_id and decision.patent_field_key:
            patent = patents[decision.patent_id]
            current_value = _current_value(patent, decision.patent_field_key)
            _restore_governance_value(
                patent,
                decision.patent_field_key,
                decision.patent_value_before,
            )
            batch = db.query(ImportBatch).filter(
                ImportBatch.id == observation.import_batch_id,
            ).first()
            source_row = db.query(ImportSourceRow).filter(
                ImportSourceRow.id == observation.source_row_id,
            ).first()
            db.add(PatentHistory(
                patent_id=patent.id,
                field_key=decision.patent_field_key,
                field_display_name=decision.patent_field_key,
                old_value=current_value,
                new_value=decision.patent_value_before,
                source="governance_revert",
                changed_by=req.reversed_by.strip() or "local-user",
                import_batch_id=batch.id if batch else None,
                source_table_title=batch.source_table_title if batch else None,
                source_row=source_row.source_row if source_row else None,
                source_field_name=observation.source_field_name,
            ))
            restored_values += 1

    db.add(GovernanceReversal(
        decision_batch_id=decision_batch_id,
        reversed_by=req.reversed_by.strip() or "local-user",
        reason=req.reason,
    ))
    try:
        db.commit()
    except Exception:
        db.rollback()
        raise
    return {
        "decision_batch_id": decision_batch_id,
        "restored_observation_count": len(decisions),
        "restored_value_count": restored_values,
    }


@router.get("/import/observations/{observation_id}/decisions")
def list_import_observation_decisions(observation_id: int, db: Session = Depends(get_db)):
    if not db.query(FieldObservation).filter(FieldObservation.id == observation_id).first():
        raise NotFoundException("待治理字段观察不存在")
    decisions = db.query(GovernanceDecision).filter(
        GovernanceDecision.observation_id == observation_id,
    ).order_by(GovernanceDecision.id.desc()).all()
    batch_ids = {decision.decision_batch_id for decision in decisions if decision.decision_batch_id}
    reversed_batch_ids = {
        reversal.decision_batch_id
        for reversal in db.query(GovernanceReversal).filter(
            GovernanceReversal.decision_batch_id.in_(batch_ids)
        ).all()
    } if batch_ids else set()
    return [
        {
            "id": decision.id,
            "observation_id": decision.observation_id,
            "decision_batch_id": decision.decision_batch_id,
            "action": decision.action,
            "scope": decision.scope,
            "canonical_field_key": decision.canonical_field_key,
            "mapping_version": decision.mapping_version,
            "adopted_value": decision.adopted_value,
            "decided_by": decision.decided_by,
            "reason": decision.reason,
            "reversed": decision.decision_batch_id in reversed_batch_ids,
            "created_at": decision.created_at.isoformat() if decision.created_at else None,
        }
        for decision in decisions
    ]


@router.get("/import/unmapped")
def list_unmapped_observations(
    batch_id: Optional[int] = None,
    source_field: Optional[str] = None,
    patent_id: Optional[int] = None,
    source_row_id: Optional[int] = None,
    status: Optional[str] = Query("unmapped_retained"),
    offset: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
    db: Session = Depends(get_db),
):
    query = _unmapped_observation_query(db, batch_id, source_field, patent_id, source_row_id, status)
    total = query.count()
    rows = query.order_by(FieldObservation.id.desc()).offset(offset).limit(limit).all()
    return {
        "total": total,
        "offset": offset,
        "limit": limit,
        "items": [_observation_to_dict(observation, source_row, batch) for observation, source_row, batch in rows],
    }


@router.get("/import/unmapped/export")
def export_unmapped_observations(
    batch_id: Optional[int] = None,
    source_field: Optional[str] = None,
    patent_id: Optional[int] = None,
    source_row_id: Optional[int] = None,
    status: Optional[str] = Query("all"),
    db: Session = Depends(get_db),
):
    rows = _unmapped_observation_query(db, batch_id, source_field, patent_id, source_row_id, status).order_by(FieldObservation.id.asc()).all()
    output = StringIO(newline="")
    writer = csv.writer(output)
    writer.writerow([
        "batch_id", "filename", "source_table_title", "worksheet_name",
        "source_row", "patent_id", "source_field_name", "canonical_field_key",
        "raw_value", "normalized_value", "current_value", "candidate_value",
        "difference_type", "field_resolution", "proposed_action",
        "final_decision", "created_at",
    ])
    for observation, source_row, batch in rows:
        item = _observation_to_dict(observation, source_row, batch)
        writer.writerow([
            item["batch_id"], item["filename"], item["source_table_title"],
            item["worksheet_name"], item["source_row"], item["patent_id"],
            item["source_field_name"], item["canonical_field_key"],
            item["raw_value"], item["normalized_value"], item["current_value"],
            item["candidate_value"], item["difference_type"],
            item["field_resolution"], item["proposed_action"],
            item["final_decision"], item["created_at"],
        ])
    return StreamingResponse(
        BytesIO(output.getvalue().encode("utf-8-sig")),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="patwiki_unmapped_observations.csv"'},
    )


@router.get("/import/batches/{batch_id}/artifact")
def download_import_artifact(batch_id: int, db: Session = Depends(get_db)):
    batch = db.query(ImportBatch).filter(ImportBatch.id == batch_id).first()
    if not batch:
        raise NotFoundException("???????")
    if not batch.artifact_path or not Path(batch.artifact_path).is_file():
        raise NotFoundException("???????????")
    return FileResponse(batch.artifact_path, filename=batch.filename)
def _process_relations(db: Session, patent: Patent, virtual: dict, database_id: Optional[int] = None):
    from app.services.relation_service import (
        process_family_members,
        process_citations,
        process_citing_patents,
    )
    family_links = 0
    citation_links = 0
    if virtual["family_numbers"]:
        family_result = process_family_members(db, patent, virtual["family_numbers"], database_id=database_id)
        family_links += family_result["members_linked"]
    if virtual["cited_numbers"]:
        citation_result = process_citations(db, patent, virtual["cited_numbers"], database_id=database_id)
        citation_links += citation_result["links"]
    if virtual["citing_numbers"]:
        citation_result = process_citing_patents(db, patent, virtual["citing_numbers"], database_id=database_id)
        citation_links += citation_result["links"]
    return {"family_links": family_links, "citation_links": citation_links}


@router.get("/stats", response_model=StatsResponse)
def get_stats(
    database_id: Optional[int] = None,
    product_id: Optional[int] = None,
    db: Session = Depends(get_db),
):
    return PatentService.get_stats(db, database_id=database_id, product_id=product_id)


@router.get("/export")
def export_patents(
    search: Optional[str] = None,
    database_id: Optional[int] = None,
    product_id: Optional[int] = None,
    project_id: Optional[int] = None,
    tag_id: Optional[int] = None,
    legal_status: Optional[str] = None,
    category: Optional[str] = None,
    has_risk: Optional[bool] = None,
    db: Session = Depends(get_db),
):
    from app.services.export_service import ExportService

    try:
        data = ExportService.export_to_excel(
            db,
            search=search,
            database_id=database_id,
            product_id=product_id,
            project_id=project_id,
            tag_ids=[tag_id] if tag_id else None,
            legal_status=legal_status,
            category=category,
            has_risk=has_risk,
        )
    except ValueError as exc:
        raise BadRequestException(str(exc)) from exc
    return StreamingResponse(
        BytesIO(data),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": 'attachment; filename="patwiki_export.xlsx"'},
    )
