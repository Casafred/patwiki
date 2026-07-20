import threading
import uuid
import tempfile
from pathlib import Path
from fastapi import APIRouter, Depends, UploadFile, File, Form, HTTPException, Query
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session
from sqlalchemy import func
from typing import Optional
import json
import pandas as pd
from io import BytesIO
from pydantic import BaseModel

from app.database import get_db, SessionLocal
from app.schemas.schemas import StatsResponse
from app.services.import_service import ImportService
from app.services.patent_service import PatentService
from app.services.merge_service import merge_patent_data, _is_empty
from app.services.relation_service import (
    process_family_members,
    process_citations,
    process_citing_patents,
)
from app.services.database_service import DatabaseService
from app.config import settings
from app.models import Patent, CustomField

router = APIRouter(tags=["import"])

TEMP_FILES: dict[str, bytes] = {}
TEMP_FILENAMES: dict[str, str] = {}


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
    database_id: Optional[int] = None  # P0-10：导入必须指定库


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
    TEMP_FILES[import_id] = content
    TEMP_FILENAMES[import_id] = file.filename or "upload.xlsx"

    import os
    def cleanup():
        import time
        time.sleep(1800)
        TEMP_FILES.pop(import_id, None)
        TEMP_FILENAMES.pop(import_id, None)
    threading.Thread(target=cleanup, daemon=True).start()

    # P0-11：返回当前库列表供前端选择
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
    if req.import_id not in TEMP_FILES:
        raise HTTPException(status_code=400, detail="导入会话已过期，请重新上传文件")

    database_id = req.database_id
    if database_id is None:
        default_db = DatabaseService.get_default_database(db)
        if not default_db:
            raise HTTPException(status_code=400, detail="未指定库且系统无默认库，请先创建库")
        database_id = default_db.id
    else:
        if not DatabaseService.get_database(db, database_id):
            raise HTTPException(status_code=400, detail=f"库不存在：{database_id}")

    content = TEMP_FILES[req.import_id]
    filename = TEMP_FILENAMES[req.import_id]

    mapping = {m.source_column: m.target_field for m in req.field_mappings if m.target_field}

    errors = []
    inserted = 0
    updated = 0
    duplicates_count = 0
    skipped = 0
    error_count = 0
    family_links = 0
    citation_links = 0
    BATCH_SIZE = 200

    try:
        df, _ = ImportService.parse_excel(content, filename)
        total_rows = len(df)
        print(f"[PatWiki] 开始导入 {total_rows} 条数据...", flush=True)

        custom_fields_cache = {cf.key: cf for cf in db.query(CustomField).all()}

        for idx, (_, row) in enumerate(df.iterrows()):
            try:
                with db.begin_nested():
                    row_dict = row.to_dict()
                    patent_data, virtual = ImportService._row_to_patent_data(
                        row_dict, mapping, db, custom_fields_cache=custom_fields_cache
                    )

                    if not patent_data.get("title"):
                        skipped += 1
                    else:
                        patent_data["database_id"] = database_id
                        if req.product_id:
                            patent_data["product_id"] = req.product_id

                        country = patent_data.get("country", "CN")
                        app_num = patent_data.get("application_number", "")
                        pub_num = patent_data.get("publication_number", "")

                        existing = None
                        if req.dedupe_by in ("both", "application_number") and app_num:
                            existing = db.query(Patent).filter(
                                Patent.application_number == app_num.strip(),
                                Patent.country == country,
                            ).first()
                        if not existing and req.dedupe_by in ("both", "publication_number") and pub_num:
                            existing = db.query(Patent).filter(
                                Patent.publication_number == pub_num.strip(),
                                Patent.country == country,
                            ).first()

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
                            custom_fields = patent_data.pop("custom_fields", {}) or {}
                            patent = Patent(**patent_data)
                            patent.custom_fields = custom_fields
                            db.add(patent)
                            db.flush()
                            inserted += 1
                            current_patent = patent

                        if current_patent is not None:
                            try:
                                if virtual["family_numbers"]:
                                    result = process_family_members(
                                        db, current_patent, virtual["family_numbers"],
                                        database_id=database_id,
                                    )
                                    family_links += result.get("members_linked", 0)
                                if virtual["cited_numbers"]:
                                    result = process_citations(
                                        db, current_patent, virtual["cited_numbers"],
                                        database_id=database_id,
                                    )
                                    citation_links += result.get("links", 0)
                                if virtual["citing_numbers"]:
                                    result = process_citing_patents(
                                        db, current_patent, virtual["citing_numbers"],
                                        database_id=database_id,
                                    )
                                    citation_links += result.get("links", 0)
                            except Exception as rel_err:
                                print(f"[PatWiki] 关系处理警告: {rel_err}", flush=True)

                if (idx + 1) % BATCH_SIZE == 0:
                    db.commit()
                    progress = idx + 1
                    pct = int(progress / total_rows * 100) if total_rows > 0 else 100
                    print(f"[PatWiki] 已处理 {progress}/{total_rows} ({pct}%) 新增:{inserted} 更新:{updated} 跳过:{skipped} 错误:{error_count}", flush=True)

            except Exception as e:
                errors.append({
                    "row": idx + 2,
                    "error": str(e),
                })
                error_count += 1
                if error_count <= 10:
                    print(f"[PatWiki] 第 {idx + 2} 行错误: {e}", flush=True)

        db.commit()
        print(f"[PatWiki] 导入完成: 新增:{inserted} 更新:{updated} 跳过:{skipped} 错误:{error_count}", flush=True)

        if database_id is not None:
            DatabaseService.refresh_patent_count(db, database_id)
    finally:
        TEMP_FILES.pop(req.import_id, None)
        TEMP_FILENAMES.pop(req.import_id, None)

    return {
        "total": inserted + updated + skipped + error_count,
        "created": inserted,
        "updated": updated,
        "skipped": skipped,
        "errors": error_count,
        "error_details": errors[:20] if errors else [],
        "database_id": database_id,
        "family_links": family_links,
        "citation_links": citation_links,
    }


@router.get("/stats", response_model=StatsResponse)
def get_stats(db: Session = Depends(get_db)):
    return PatentService.get_stats(db)


@router.get("/export")
def export_patents(
    search: Optional[str] = None,
    product_id: Optional[int] = None,
    project_id: Optional[int] = None,
    tag_id: Optional[int] = None,
    legal_status: Optional[str] = None,
    category: Optional[str] = None,
    has_risk: Optional[bool] = None,
    db: Session = Depends(get_db),
):
    tag_ids = [tag_id] if tag_id else None
    patents, total = PatentService.list_patents(
        db, page=1, page_size=100000,
        search=search, product_id=product_id, project_id=project_id,
        tag_ids=tag_ids, legal_status=legal_status, category=category,
        has_risk=has_risk,
    )

    rows = []
    for p in patents:
        row = {
            "申请号": p.application_number or "",
            "公开号": p.publication_number or "",
            "标题": p.title,
            "摘要": p.abstract or "",
            "申请人": p.applicant or "",
            "发明人": p.inventor or "",
            "申请日": p.filing_date.isoformat() if p.filing_date else "",
            "公开日": p.publication_date.isoformat() if p.publication_date else "",
            "授权日": p.grant_date.isoformat() if p.grant_date else "",
            "法律状态": p.legal_status or "",
            "专利类型": p.patent_type or "",
            "国家": p.country or "",
            "IPC主分类": p.ipc_main or "",
            "分类": p.category or "",
            "子分类": p.subcategory or "",
            "是否有风险": "是" if p.has_risk else "否",
            "风险等级": p.risk_level or "",
            "模块": p.module or "",
            "技术问题": p.technical_problem or "",
            "技术效果": p.technical_effect or "",
            "技术方案": p.technical_solution or "",
            "备注": p.notes or "",
        }
        rows.append(row)

    df = pd.DataFrame(rows)

    output = BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="专利数据")

    output.seek(0)

    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".xlsx")
    tmp.write(output.getvalue())
    tmp.close()

    return FileResponse(
        tmp.name,
        filename=f"patents_export_{pd.Timestamp.now().strftime('%Y%m%d_%H%M%S')}.xlsx",
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
