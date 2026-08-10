import threading
import uuid
import tempfile
import os
import time
from datetime import datetime
from pathlib import Path
from fastapi import APIRouter, Depends, UploadFile, File, Form, HTTPException, Query
from fastapi.responses import FileResponse, StreamingResponse
from sqlalchemy.orm import Session
from sqlalchemy import func, text, or_
from typing import Optional
import json
import pandas as pd
from io import BytesIO
from pydantic import BaseModel

from app.database import get_db, SessionLocal, engine
from app.schemas.schemas import ImportBatchResponse, StatsResponse
from app.services.import_service import ImportService
from app.services.patent_service import PatentService
from app.services.merge_service import merge_patent_data, _is_empty
from app.config import settings
from app.models import CustomField, ImportBatch, ImportBatchStatus, Patent

router = APIRouter(tags=["import"])

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


@router.post("/import/preview")
async def preview_import(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    content = await file.read()
    df, columns = ImportService.parse_excel(content, file.filename or "upload.xlsx")
    suggested_mapping = ImportService.suggest_mapping(columns, db)

    preview_rows_list = []
    for _, row in df.head(3).iterrows():
        preview_rows_list.append({str(k): str(v) for k, v in row.to_dict().items()})

    import_id = str(uuid.uuid4())
    # 持久化到磁盘文件，避免后端重启或内存清理导致会话过期
    temp_path = TEMP_DIR / f"{import_id}.bin"
    with open(temp_path, "wb") as f:
        f.write(content)
    TEMP_FILES[import_id] = {
        "path": str(temp_path),
        "filename": file.filename or "upload.xlsx",
        "created_at": time.time(),
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
        "databases": [DatabaseService.to_dict(d) for d in databases],
        "default_database_id": default_db.id if default_db else None,
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


@router.post("/import/confirm")
def confirm_import(
    req: ConfirmImportRequest,
    db: Session = Depends(get_db),
):
    # 从磁盘读取会话文件（不再依赖内存索引，避免后端重启导致会话丢失）
    temp_path = TEMP_DIR / f"{req.import_id}.bin"
    if not temp_path.exists():
        raise HTTPException(
            status_code=400,
            detail="导入会话已过期或文件不存在，请重新上传文件"
        )
    # 基于文件 mtime 检查 TTL，避免后端重启后 created_at 被重置
    file_mtime = temp_path.stat().st_mtime
    if time.time() - file_mtime > TEMP_TTL:
        try:
            os.remove(temp_path)
        except OSError:
            pass
        raise HTTPException(
            status_code=400,
            detail=f"导入会话已过期（超过{TEMP_TTL // 3600}小时），请重新上传文件"
        )
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
            raise HTTPException(status_code=400, detail="未指定库且系统无默认库，请先创建库")
        database_id = default_db.id
    else:
        from app.services.database_service import DatabaseService
        if not DatabaseService.get_database(db, database_id):
            raise HTTPException(status_code=400, detail=f"库不存在：{database_id}")

    with open(info["path"], "rb") as f:
        content = f.read()
    filename = info["filename"]

    mapping = {m.source_column: m.target_field for m in req.field_mappings if m.target_field}

    errors = []
    inserted = 0
    updated = 0
    duplicates_count = 0
    skipped = 0
    error_count = 0
    BATCH_SIZE = 500
    batch: ImportBatch | None = None

    try:
        _optimize_sqlite_connection(db)

        batch = ImportBatch(
            filename=filename,
            status=ImportBatchStatus.PROCESSING,
            started_at=datetime.utcnow(),
        )
        db.add(batch)
        db.flush()

        df, _ = ImportService.parse_excel(content, filename)
        total_rows = len(df)
        batch.total_rows = total_rows
        print(f"[PatWiki] 开始导入 {total_rows} 条数据...", flush=True)

        custom_fields_cache = {cf.key: cf for cf in db.query(CustomField).all()}

        rows_data = []
        for idx, (_, row) in enumerate(df.iterrows()):
            try:
                row_dict = row.to_dict()
                patent_data, virtual = ImportService._row_to_patent_data(
                    row_dict, mapping, db, custom_fields_cache=custom_fields_cache
                )
                patent_data["database_id"] = database_id
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
                    "row_num": idx + 2,
                })
            except Exception as e:
                errors.append({"row": idx + 2, "error": str(e)})
                error_count += 1

        all_app_nums: dict[tuple[str, str], Patent] = {}
        all_pub_nums: dict[tuple[str, str], Patent] = {}

        app_nums_to_check = list({(rd["app_num"], rd["country"]) for rd in rows_data if rd["app_num"]})
        pub_nums_to_check = list({(rd["pub_num"], rd["country"]) for rd in rows_data if rd["pub_num"]})

        if app_nums_to_check:
            app_conditions = [
                (Patent.application_number == num) & (Patent.country == ctry)
                for num, ctry in app_nums_to_check
            ]
            existing_patents = db.query(Patent).filter(or_(*app_conditions)).all()
            for p in existing_patents:
                if p.application_number:
                    all_app_nums[(p.application_number.strip(), p.country or "CN")] = p

        if pub_nums_to_check:
            pub_conditions = [
                (Patent.publication_number == num) & (Patent.country == ctry)
                for num, ctry in pub_nums_to_check
            ]
            existing_patents_pub = db.query(Patent).filter(or_(*pub_conditions)).all()
            for p in existing_patents_pub:
                if p.publication_number:
                    all_pub_nums[(p.publication_number.strip(), p.country or "CN")] = p

        print(f"[PatWiki] 预查重完成: 库中已有申请号记录 {len(all_app_nums)} 条, 公开号记录 {len(all_pub_nums)} 条", flush=True)

        seen_app_nums: set[tuple[str, str]] = set()
        seen_pub_nums: set[tuple[str, str]] = set()
        pending_relations: list[tuple[Patent, dict]] = []
        imported_patent_ids: set[int] = set()

        for i, rd in enumerate(rows_data):
            try:
                with db.begin_nested():
                    patent_data = rd["patent_data"]
                    virtual = rd["virtual"]
                    country = rd["country"]
                    app_num = rd["app_num"]
                    pub_num = rd["pub_num"]

                    if not patent_data.get("title"):
                        skipped += 1
                    else:
                        existing = None
                        if req.dedupe_by in ("both", "application_number") and app_num:
                            key = (app_num, country)
                            existing = all_app_nums.get(key)
                        if not existing and req.dedupe_by in ("both", "publication_number") and pub_num:
                            key = (pub_num, country)
                            existing = all_pub_nums.get(key)

                        current_patent = None
                        if existing:
                            duplicates_count += 1
                            if req.update_on_duplicate:
                                merged = merge_patent_data(existing, patent_data)
                                _apply_patent_update(existing, merged)
                                updated += 1
                                current_patent = existing
                            else:
                                skipped += 1
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
                                        _apply_patent_update(existing_in_batch, merged)
                                        updated += 1
                                        current_patent = existing_in_batch
                                    else:
                                        skipped += 1
                                else:
                                    skipped += 1
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
                                inserted += 1
                                current_patent = patent
                                if app_num:
                                    all_app_nums[(app_num, country)] = patent
                                if pub_num:
                                    all_pub_nums[(pub_num, country)] = patent

                        if current_patent is not None:
                            imported_patent_ids.add(current_patent.id)
                            has_rel = virtual["family_numbers"] or virtual["cited_numbers"] or virtual["citing_numbers"]
                            if has_rel:
                                pending_relations.append((current_patent, virtual))

                if (i + 1) % BATCH_SIZE == 0:
                    db.commit()
                    for cp, vv in pending_relations:
                        try:
                            _process_relations(db, cp, vv, database_id)
                        except Exception as rel_err:
                            print(f"[PatWiki] 关系处理警告(patent_id={cp.id}): {rel_err}", flush=True)
                    db.commit()
                    pending_relations.clear()
                    progress = i + 1
                    pct = int(progress / total_rows * 100) if total_rows > 0 else 100
                    print(f"[PatWiki] 已处理 {progress}/{total_rows} ({pct}%) 新增:{inserted} 更新:{updated} 跳过:{skipped} 错误:{error_count}", flush=True)

            except Exception as e:
                errors.append({"row": rd["row_num"], "error": str(e)})
                error_count += 1
                if error_count <= 10:
                    print(f"[PatWiki] 第 {rd['row_num']} 行错误: {e}", flush=True)

        db.commit()
        for cp, vv in pending_relations:
            try:
                _process_relations(db, cp, vv, database_id)
            except Exception as rel_err:
                print(f"[PatWiki] 关系处理警告(patent_id={cp.id}): {rel_err}", flush=True)
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
            batch.errors = errors[:20] if errors else None
            batch.status = ImportBatchStatus.COMPLETED
            batch.completed_at = datetime.utcnow()
            db.add(batch)
            db.commit()
    except Exception as exc:
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
        "total": inserted + updated + skipped + error_count,
        "created": inserted,
        "updated": updated,
        "skipped": skipped,
        "errors": error_count,
        "error_details": errors[:20] if errors else [],
        "database_id": database_id,
        "family_links": 0,
        "citation_links": 0,
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
            raise HTTPException(status_code=400, detail=f"不支持的导入状态：{status}") from exc
    return query.order_by(ImportBatch.created_at.desc(), ImportBatch.id.desc()).limit(limit).all()


@router.get("/import/batches/{batch_id}", response_model=ImportBatchResponse)
def get_import_batch(batch_id: int, db: Session = Depends(get_db)):
    batch = db.query(ImportBatch).filter(ImportBatch.id == batch_id).first()
    if not batch:
        raise HTTPException(status_code=404, detail="导入批次不存在")
    return batch


def _process_relations(db: Session, patent: Patent, virtual: dict, database_id: Optional[int] = None):
    from app.services.relation_service import (
        process_family_members,
        process_citations,
        process_citing_patents,
    )
    if virtual["family_numbers"]:
        process_family_members(db, patent, virtual["family_numbers"], database_id=database_id)
    if virtual["cited_numbers"]:
        process_citations(db, patent, virtual["cited_numbers"], database_id=database_id)
    if virtual["citing_numbers"]:
        process_citing_patents(db, patent, virtual["citing_numbers"], database_id=database_id)


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
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return StreamingResponse(
        BytesIO(data),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": 'attachment; filename="patwiki_export.xlsx"'},
    )
