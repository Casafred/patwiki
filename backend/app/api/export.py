"""Excel/CSV 数据导出 API。"""
from __future__ import annotations

import io
from typing import Any, Literal, Optional

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.database import get_db
from app.services.export_service import ExportService
from app.core.exceptions import BadRequestException
from app.models import PatentExportTemplate


router = APIRouter(tags=["export"])


class ExportRequest(BaseModel):
    database_id: Optional[int] = None
    view_id: Optional[int] = None
    field_keys: Optional[list[str]] = Field(default=None, max_length=200)
    filters: dict[str, Any] = Field(default_factory=dict)
    search: Optional[str] = None
    product_id: Optional[int] = None
    project_id: Optional[int] = None
    tag_ids: Optional[list[int]] = None
    legal_status: Optional[str] = None
    category: Optional[str] = None
    has_risk: Optional[bool] = None
    group_by: Optional[str] = None
    template_id: Optional[int] = None


class ExportTemplateRequest(BaseModel):
    database_id: int
    template_key: str
    name: str
    description: Optional[str] = None
    output_format: Literal["excel", "word", "csv"] = "excel"
    field_keys: list[str] = Field(default_factory=list, max_length=200)
    filter_config: dict[str, Any] = Field(default_factory=dict)
    sort_config: dict[str, Any] = Field(default_factory=dict)
    group_by: Optional[str] = None
    view_id: Optional[int] = None


def _template_to_dict(template: PatentExportTemplate) -> dict[str, Any]:
    return {
        "id": template.id,
        "database_id": template.database_id,
        "view_id": template.view_id,
        "template_key": template.template_key,
        "name": template.name,
        "description": template.description,
        "output_format": template.output_format,
        "field_keys": template.field_keys or [],
        "filter_config": template.filter_config or {},
        "sort_config": template.sort_config or {},
        "group_by": template.group_by,
        "version": template.version,
        "is_system": template.is_system,
        "created_at": template.created_at.isoformat() if template.created_at else None,
        "updated_at": template.updated_at.isoformat() if template.updated_at else None,
    }


def _stream(data: bytes, filename: str, media_type: str) -> StreamingResponse:
    return StreamingResponse(
        io.BytesIO(data),
        media_type=media_type,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.post("/export/excel")
def export_excel(body: ExportRequest, db: Session = Depends(get_db)):
    try:
        data = ExportService.export_to_excel(db, **body.model_dump())
    except ValueError as exc:
        raise BadRequestException(str(exc)) from exc
    return _stream(data, "patwiki_export.xlsx", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")


@router.post("/export/csv")
def export_csv(body: ExportRequest, db: Session = Depends(get_db)):
    try:
        data = ExportService.export_to_csv(db, **body.model_dump())
    except ValueError as exc:
        raise BadRequestException(str(exc)) from exc
    return _stream(data, "patwiki_export.csv", "text/csv; charset=utf-8")


@router.post("/export/word")
def export_word(body: ExportRequest, db: Session = Depends(get_db)):
    try:
        data = ExportService.export_to_word(db, **body.model_dump())
    except ValueError as exc:
        raise BadRequestException(str(exc)) from exc
    return _stream(
        data,
        "patwiki_work_file.docx",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    )


@router.get("/export/templates")
def list_export_templates(
    database_id: Optional[int] = None,
    db: Session = Depends(get_db),
):
    query = db.query(PatentExportTemplate)
    if database_id is not None:
        query = query.filter(PatentExportTemplate.database_id == database_id)
    return [_template_to_dict(item) for item in query.order_by(PatentExportTemplate.name).all()]


@router.post("/export/templates")
def create_export_template(body: ExportTemplateRequest, db: Session = Depends(get_db)):
    if not body.template_key.strip():
        raise BadRequestException("模板 key 不能为空")
    from app.models import PatentDatabase
    if not db.query(PatentDatabase).filter(PatentDatabase.id == body.database_id).first():
        raise BadRequestException("数据库不存在")
    if body.view_id is not None:
        from app.models import PatentView
        view = db.query(PatentView).filter(PatentView.id == body.view_id).first()
        if not view or view.database_id != body.database_id:
            raise BadRequestException("视图不存在或不属于指定数据库")
    existing = db.query(PatentExportTemplate).filter(
        PatentExportTemplate.database_id == body.database_id,
        PatentExportTemplate.template_key == body.template_key.strip(),
    ).first()
    if existing:
        raise BadRequestException("模板 key 已存在")
    try:
        if body.field_keys:
            ExportService._resolve_fields(db, body.field_keys)
    except ValueError as exc:
        raise BadRequestException(str(exc)) from exc
    template = PatentExportTemplate(
        database_id=body.database_id,
        view_id=body.view_id,
        template_key=body.template_key.strip(),
        name=body.name.strip(),
        description=body.description,
        output_format=body.output_format,
        field_keys=body.field_keys,
        filter_config=body.filter_config,
        sort_config=body.sort_config,
        group_by=body.group_by,
        version=1,
        is_system=False,
    )
    db.add(template)
    db.commit()
    db.refresh(template)
    return _template_to_dict(template)


@router.get("/export/templates/{template_id}")
def get_export_template(template_id: int, db: Session = Depends(get_db)):
    template = db.query(PatentExportTemplate).filter(PatentExportTemplate.id == template_id).first()
    if not template:
        raise BadRequestException("导出模板不存在")
    return _template_to_dict(template)


@router.put("/export/templates/{template_id}")
def update_export_template(template_id: int, body: ExportTemplateRequest, db: Session = Depends(get_db)):
    template = db.query(PatentExportTemplate).filter(PatentExportTemplate.id == template_id).first()
    if not template:
        raise BadRequestException("导出模板不存在")
    if body.database_id != template.database_id:
        raise BadRequestException("不能修改模板所属数据库")
    duplicate = db.query(PatentExportTemplate).filter(
        PatentExportTemplate.database_id == template.database_id,
        PatentExportTemplate.template_key == body.template_key.strip(),
        PatentExportTemplate.id != template.id,
    ).first()
    if duplicate:
        raise BadRequestException("模板 key 已存在")
    if body.view_id is not None:
        from app.models import PatentView
        view = db.query(PatentView).filter(PatentView.id == body.view_id).first()
        if not view or view.database_id != template.database_id:
            raise BadRequestException("视图不存在或不属于指定数据库")
    try:
        if body.field_keys:
            ExportService._resolve_fields(db, body.field_keys)
    except ValueError as exc:
        raise BadRequestException(str(exc)) from exc
    for field in ("view_id", "template_key", "name", "description", "output_format", "field_keys", "filter_config", "sort_config", "group_by"):
        value = getattr(body, field)
        if field == "template_key":
            value = value.strip()
        setattr(template, field, value)
    template.version = (template.version or 0) + 1
    db.add(template)
    db.commit()
    db.refresh(template)
    return _template_to_dict(template)


@router.delete("/export/templates/{template_id}")
def delete_export_template(template_id: int, db: Session = Depends(get_db)):
    template = db.query(PatentExportTemplate).filter(PatentExportTemplate.id == template_id).first()
    if not template:
        raise BadRequestException("导出模板不存在")
    if template.is_system:
        raise BadRequestException("系统模板不允许删除")
    db.delete(template)
    db.commit()
    return {"success": True}
