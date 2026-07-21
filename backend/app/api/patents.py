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
    group_by_family: bool = Query(False, description="同族聚拢模式：同族专利排在一起，附加 family_size"),
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
        group_by_family=group_by_family,
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


@router.post("/bulk-delete")
def bulk_delete_patents(
    patent_ids: list[int],
    db: Session = Depends(get_db),
):
    """批量删除专利。请求体直接为 [id1, id2, ...] 数组。"""
    if not patent_ids:
        return {"success": True, "deleted_count": 0}
    from app.models.patent import Patent as PatentModel
    patents = db.query(PatentModel).filter(PatentModel.id.in_(patent_ids)).all()
    for p in patents:
        db.delete(p)
    db.commit()
    return {"success": True, "deleted_count": len(patents)}


@router.delete("/by-database/{database_id}")
def delete_all_patents_in_database(
    database_id: int,
    db: Session = Depends(get_db),
):
    """清空指定库下的所有专利（整库清空，不删库本身）。"""
    from app.models.patent import Patent as PatentModel
    count = db.query(PatentModel).filter(PatentModel.database_id == database_id).count()
    if count == 0:
        return {"success": True, "deleted_count": 0}
    # 批量删除（SQLite 单条 delete 较慢，用 delete 语句）
    db.query(PatentModel).filter(PatentModel.database_id == database_id).delete(
        synchronize_session=False
    )
    db.commit()
    return {"success": True, "deleted_count": count}


@router.post("/cleanup/invalid-placeholders")
def cleanup_invalid_placeholders(
    dry_run: bool = Query(True, description="dry_run=True 仅返回将被删除的列表，不真正删除"),
    db: Session = Depends(get_db),
):
    """清理无效的占位专利（title="待补全" 且申请号/公开号格式不合法的记录）。

    这些占位专利通常由同族/引用列解析时，因分隔符识别错误或日期+专利号合并乱码导致。
    修复 relation_service 后，历史残留的无效占位可用本端点清理。
    """
    from app.services.relation_service import _PATENT_NUM_RE, _DATE_PREFIX_RE
    from app.models.patent import Patent as PatentModel

    candidates = db.query(PatentModel).filter(PatentModel.title == "待补全").all()

    def _is_invalid(num) -> bool:
        """判断单个号是否不合法（应被清理）。"""
        if not num:
            return False
        num = num.strip() if isinstance(num, str) else num
        if not num:
            return False
        if len(num) < 5 or len(num) > 30:
            return True
        if not _PATENT_NUM_RE.match(num):
            return True
        # 日期前缀乱码（如 20061102AU2005201606A1）
        if _DATE_PREFIX_RE.match(num):
            return True
        return False

    to_delete = []
    for p in candidates:
        app_invalid = _is_invalid(p.application_number)
        pub_invalid = _is_invalid(p.publication_number)
        # 申请号和公开号都不合法 → 删除
        if app_invalid and pub_invalid:
            to_delete.append(p)
        # 申请号不合法且无公开号 → 删除
        elif app_invalid and not p.publication_number:
            to_delete.append(p)
        # 公开号不合法且无申请号 → 删除
        elif pub_invalid and not p.application_number:
            to_delete.append(p)

    items = [
        {
            "id": p.id,
            "application_number": p.application_number,
            "publication_number": p.publication_number,
            "notes": p.notes,
            "created_at": p.created_at.isoformat() if p.created_at else None,
        }
        for p in to_delete
    ]

    if not dry_run:
        for p in to_delete:
            db.delete(p)
        db.commit()

    return {"deleted_count": len(items), "deleted_items": items, "dry_run": dry_run}


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
