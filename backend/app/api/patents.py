from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy.orm import Session
from typing import Optional
from datetime import date, datetime
import json

from app.database import get_db
from app.api.deps import get_pagination_params
from app.schemas.schemas import (
    Patent, PatentCreate, PatentUpdate, PatentListResponse, BulkUpdateRequest
)
from app.services.patent_service import PatentService
from app.services.view_service import ViewService
from app.models import PatentHistory, AIFieldValue, CustomField
from pydantic import BaseModel

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
    req: BulkUpdateRequest,
    db: Session = Depends(get_db),
):
    updates = req.updates or {}
    count = PatentService.bulk_update(
        db,
        req.patent_ids,
        updates,
        changed_by=req.changed_by,
        source=req.source or "bulk",
    )
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


# ============================================================
# P2-3：AI 字段值人工覆盖
# ============================================================

class AIValueOverrideRequest(BaseModel):
    """人工覆盖 AI 字段值。"""
    value: Optional[str] = None  # None 表示取消覆盖
    changed_by: Optional[str] = None


@router.get("/{patent_id}/ai-values")
def get_ai_values(patent_id: int, db: Session = Depends(get_db)):
    """P2-3：列出该专利所有 AI 字段的当前值与覆盖状态。"""
    patent = PatentService.get_patent(db, patent_id)
    if not patent:
        raise HTTPException(status_code=404, detail="Patent not found")

    rows = (
        db.query(AIFieldValue)
        .filter(AIFieldValue.patent_id == patent_id)
        .all()
    )
    # 字段名映射
    field_name_map: dict[str, str] = {}
    for cf in db.query(CustomField).all():
        field_name_map[cf.key] = cf.name

    return [
        {
            "id": r.id,
            "field_key": r.field_key,
            "field_name": field_name_map.get(r.field_key, r.field_key),
            "ai_value": r.value,
            "model_name": r.model_name,
            "is_overridden": bool(r.is_overridden),
            "display_value": r.overridden_value if r.is_overridden else r.value,
            "overridden_value": r.overridden_value if r.is_overridden else None,
            "overridden_at": r.overridden_at.isoformat() if r.overridden_at else None,
            "created_at": r.created_at.isoformat() if r.created_at else None,
            "updated_at": r.updated_at.isoformat() if r.updated_at else None,
        }
        for r in rows
    ]


@router.put("/{patent_id}/ai-values/{field_key}")
def override_ai_value(
    patent_id: int,
    field_key: str,
    req: AIValueOverrideRequest,
    db: Session = Depends(get_db),
):
    """P2-3：人工覆盖某个 AI 字段值（写入 overridden_value，is_overridden=True）。

    若 req.value 为 None，则取消覆盖，恢复显示 AI 原值。
    同时把覆盖写回 Patent.ai_fields（与显示保持一致）并记一条历史。
    """
    patent = PatentService.get_patent(db, patent_id)
    if not patent:
        raise HTTPException(status_code=404, detail="Patent not found")

    row = (
        db.query(AIFieldValue)
        .filter(
            AIFieldValue.patent_id == patent_id,
            AIFieldValue.field_key == field_key,
        )
        .first()
    )
    if not row:
        raise HTTPException(
            status_code=404,
            detail=f"AI 字段值不存在：patent_id={patent_id}, field_key={field_key}（请先运行 AI 提取）",
        )

    ai_value = row.value
    old_display = row.overridden_value if row.is_overridden else row.value

    if req.value is None:
        # 取消覆盖
        row.is_overridden = False
        row.overridden_value = None
        row.overridden_at = None
        new_display = ai_value
    else:
        row.is_overridden = True
        row.overridden_value = req.value
        row.overridden_at = datetime.utcnow()
        new_display = req.value

    # 同步写回 patent.ai_fields（便于在列表/筛选中看到覆盖后的值）
    current_ai = dict(patent.ai_fields or {})
    current_ai[field_key] = new_display
    patent.ai_fields = current_ai

    # 记录历史
    field_display_name = field_key
    cf = db.query(CustomField).filter(CustomField.key == field_key).first()
    if cf:
        field_display_name = cf.name

    hist = PatentHistory(
        patent_id=patent_id,
        field_key=f"ai_fields.{field_key}",
        field_display_name=field_display_name,
        old_value=old_display or "",
        new_value=new_display or "",
        source="manual",
        changed_by=req.changed_by or "manual",
    )
    db.add(hist)
    db.add(row)
    db.add(patent)
    db.commit()
    db.refresh(row)

    return {
        "id": row.id,
        "field_key": row.field_key,
        "ai_value": row.value,
        "is_overridden": bool(row.is_overridden),
        "display_value": row.overridden_value if row.is_overridden else row.value,
        "overridden_value": row.overridden_value if row.is_overridden else None,
        "overridden_at": row.overridden_at.isoformat() if row.overridden_at else None,
    }


@router.delete("/{patent_id}/ai-values/{field_key}/override")
def clear_ai_override(
    patent_id: int,
    field_key: str,
    db: Session = Depends(get_db),
):
    """P2-3：取消 AI 字段的人工覆盖，恢复显示 AI 原值。"""
    patent = PatentService.get_patent(db, patent_id)
    if not patent:
        raise HTTPException(status_code=404, detail="Patent not found")

    row = (
        db.query(AIFieldValue)
        .filter(
            AIFieldValue.patent_id == patent_id,
            AIFieldValue.field_key == field_key,
        )
        .first()
    )
    if not row:
        raise HTTPException(
            status_code=404,
            detail=f"AI 字段值不存在：patent_id={patent_id}, field_key={field_key}",
        )

    old_display = row.overridden_value if row.is_overridden else row.value
    row.is_overridden = False
    row.overridden_value = None
    row.overridden_at = None

    # 同步回 patent.ai_fields
    current_ai = dict(patent.ai_fields or {})
    current_ai[field_key] = row.value
    patent.ai_fields = current_ai

    field_display_name = field_key
    cf = db.query(CustomField).filter(CustomField.key == field_key).first()
    if cf:
        field_display_name = cf.name

    hist = PatentHistory(
        patent_id=patent_id,
        field_key=f"ai_fields.{field_key}",
        field_display_name=field_display_name,
        old_value=old_display or "",
        new_value=row.value or "",
        source="manual",
        changed_by="manual",
    )
    db.add(hist)
    db.add(row)
    db.add(patent)
    db.commit()

    return {
        "id": row.id,
        "field_key": row.field_key,
        "ai_value": row.value,
        "is_overridden": False,
        "display_value": row.value,
    }
