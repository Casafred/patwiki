"""Excel/CSV 数据导出 API。"""
from __future__ import annotations

import io
from typing import Any, Optional

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.database import get_db
from app.services.export_service import ExportService
from app.core.exceptions import BadRequestException


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
