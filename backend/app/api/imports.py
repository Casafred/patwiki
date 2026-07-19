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
from app.schemas.schemas import StatsResponse, PatentCreate as _PatentCreate
from app.services.import_service import ImportService
from app.services.patent_service import PatentService
from app.services.merge_service import merge_patent_data
from app.services.relation_service import (
    process_family_members,
    process_citations,
    process_citing_patents,
)
from app.services.database_service import DatabaseService
from app.config import settings

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


@router.post("/import/confirm")
async def confirm_import(
    req: ConfirmImportRequest,
    db: Session = Depends(get_db),
):
    if req.import_id not in TEMP_FILES:
        raise HTTPException(status_code=400, detail="导入会话已过期，请重新上传文件")

    # P0-11：必须指定库；未指定则使用默认库
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
    options = {
        "update_on_duplicate": req.update_on_duplicate,
        "dedupe_by": req.dedupe_by,
    }

    errors = []
    inserted = 0
    updated = 0
    duplicates_count = 0
    skipped = 0
    error_count = 0
    family_links = 0
    citation_links = 0

    try:
        df, _ = ImportService.parse_excel(content, filename)

        for idx, (_, row) in enumerate(df.iterrows()):
            try:
                row_dict = row.to_dict()
                # P0-10：_row_to_patent_data 返回 (patent_data, virtual_data)
                patent_data, virtual = ImportService._row_to_patent_data(row_dict, mapping, db)

                if not patent_data.get("title"):
                    skipped += 1
                    continue

                # 库归属
                patent_data["database_id"] = database_id

                if req.product_id:
                    patent_data["product_id"] = req.product_id

                country = patent_data.get("country", "CN")
                app_num = patent_data.get("application_number", "")
                pub_num = patent_data.get("publication_number", "")

                existing = None
                if req.dedupe_by in ("both", "application_number") and app_num:
                    existing = PatentService.get_patent_by_application_number(db, app_num.strip(), country)
                if not existing and req.dedupe_by in ("both", "publication_number") and pub_num:
                    existing = PatentService.get_patent_by_publication_number(db, pub_num.strip(), country)

                if existing:
                    duplicates_count += 1
                    if req.update_on_duplicate:
                        # P0-10：Wiki 式字段级合并，标注类字段非空才覆盖
                        merged = merge_patent_data(existing, patent_data)
                        PatentService.update_patent(db, existing, merged)
                        updated += 1
                        current_patent = existing
                    else:
                        skipped += 1
                        current_patent = None
                else:
                    patent = PatentService.create_patent(db, _PatentCreate(**patent_data))
                    inserted += 1
                    current_patent = patent

                # P0-10：同族/引用关系入库
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
                    except Exception:
                        # 关系入库失败不影响主表导入
                        pass

            except Exception as e:
                errors.append({
                    "row": idx + 2,
                    "error": str(e),
                })
                error_count += 1

        db.commit()

        # 刷新库内专利计数
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
