from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy.orm import Session
from typing import Optional
from datetime import date
import json

from app.database import get_db
from app.api.deps import get_pagination_params
from app.schemas.schemas import (
    Patent, PatentCreate, PatentUpdate, PatentListResponse
)
from app.services.patent_service import PatentService
from app.services.view_service import ViewService
from app.models import PatentHistory

router = APIRouter(prefix="/patents", tags=["patents"])


@router.get("", response_model=PatentListResponse)
def list_patents(
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=1000),
    search: Optional[str] = None,
    database_id: Optional[int] = None,
    product_id: Optional[int] = None,
    project_id: Optional[int] = None,
    tag_id: Optional[int] = None,
    legal_status: Optional[str] = None,
    category: Optional[str] = None,
    has_risk: Optional[bool] = None,
    risk_level: Optional[str] = None,
    patent_type: Optional[str] = None,
    country: Optional[str] = None,
    filing_date_from: Optional[date] = None,
    filing_date_to: Optional[date] = None,
    sort_by: Optional[str] = None,
    sort_order: Optional[str] = "asc",
    custom_filters: Optional[str] = Query(None, description="JSON string of custom field filters"),
    filters: Optional[str] = Query(None, description="JSON string of unified field filters, supports {field: {contains: 'xxx'}, field2: {eq: 'yyy'}}"),
    db: Session = Depends(get_db),
):
    tag_ids = [tag_id] if tag_id else None
    cf = None
    if custom_filters:
        try:
            cf = json.loads(custom_filters)
        except (json.JSONDecodeError, TypeError):
            cf = None
    uf = None
    if filters:
        try:
            uf = json.loads(filters)
        except (json.JSONDecodeError, TypeError):
            uf = None
    patents, total = PatentService.list_patents(
        db,
        page=page,
        page_size=page_size,
        search=search,
        database_id=database_id,
        product_id=product_id,
        project_id=project_id,
        tag_ids=tag_ids,
        legal_status=legal_status,
        category=category,
        has_risk=has_risk,
        risk_level=risk_level,
        patent_type=patent_type,
        country=country,
        filing_date_from=filing_date_from,
        filing_date_to=filing_date_to,
        sort_by=sort_by,
        sort_order=sort_order,
        custom_filters=cf,
        filters=uf,
    )
    return {
        "total": total,
        "items": patents,
        "page": page,
        "page_size": page_size,
    }


@router.get("/{patent_id}", response_model=Patent)
def get_patent(patent_id: int, db: Session = Depends(get_db)):
    patent = PatentService.get_patent(db, patent_id)
    if not patent:
        raise HTTPException(status_code=404, detail="Patent not found")
    return patent


@router.post("", response_model=Patent)
def create_patent(patent_in: PatentCreate, db: Session = Depends(get_db)):
    return PatentService.create_patent(db, patent_in)


@router.put("/{patent_id}", response_model=Patent)
def update_patent(patent_id: int, patent_in: PatentUpdate, db: Session = Depends(get_db)):
    patent = PatentService.get_patent(db, patent_id)
    if not patent:
        raise HTTPException(status_code=404, detail="Patent not found")
    return PatentService.update_patent(db, patent, patent_in)


@router.delete("/{patent_id}")
def delete_patent(patent_id: int, db: Session = Depends(get_db)):
    if not PatentService.delete_patent(db, patent_id):
        raise HTTPException(status_code=404, detail="Patent not found")
    return {"success": True}


@router.post("/bulk-update")
def bulk_update_patents(
    patent_ids: list[int],
    updates: dict,
    db: Session = Depends(get_db),
):
    count = PatentService.bulk_update(db, patent_ids, updates)
    return {"success": True, "updated_count": count}


@router.get("/{patent_id}/history")
def get_patent_history(
    patent_id: int,
    limit: int = Query(100, ge=1, le=500),
    db: Session = Depends(get_db),
):
    """查询专利的修改历史记录，按时间倒序。"""
    patent = PatentService.get_patent(db, patent_id)
    if not patent:
        raise HTTPException(status_code=404, detail="Patent not found")

    records = (
        db.query(PatentHistory)
        .filter(PatentHistory.patent_id == patent_id)
        .order_by(PatentHistory.id.desc())
        .limit(limit)
        .all()
    )
    return [
        {
            "id": h.id,
            "patent_id": h.patent_id,
            "field_key": h.field_key,
            "field_display_name": h.field_display_name,
            "old_value": h.old_value,
            "new_value": h.new_value,
            "source": h.source,
            "changed_by": h.changed_by,
            "source_view_id": h.source_view_id,
            "source_view_name": h.source_view_name,
            "created_at": h.created_at.isoformat() if h.created_at else None,
        }
        for h in records
    ]


@router.get("/{patent_id}/field-sources")
def get_field_sources(patent_id: int, db: Session = Depends(get_db)):
    """字段来源追溯：返回该专利每个字段的最后一次修改来源信息。

    用于详情页展示"这个值是从哪个小表/导入/AI 来的"。
    """
    patent = PatentService.get_patent(db, patent_id)
    if not patent:
        raise HTTPException(status_code=404, detail="Patent not found")
    return ViewService.get_field_sources(db, patent_id)
