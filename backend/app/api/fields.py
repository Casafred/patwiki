from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Any, Optional
from datetime import date

from app.database import get_db
from app.models import Patent, PatentHistory
from app.services.field_registry import get_all_fields_meta, SYSTEM_FIELD_KEYS, get_system_field_meta
from app.services.patent_service import PatentService, _is_value_changed, _stringify_value

router = APIRouter(tags=["fields"])


@router.get("/fields")
def list_fields(
    view_id: Optional[int] = Query(None, description="视图 ID：传入则附加该视图的本地字段元数据"),
    db: Session = Depends(get_db),
):
    """列出所有字段元数据（系统字段 + 自定义字段）。

    P1-12 扩展：传入 view_id 时附加该视图的 view_local_fields，
    每项标注 source（system / custom / view_local）。
    """
    return get_all_fields_meta(db, view_id=view_id)


class CellUpdateRequest(BaseModel):
    """单元格更新请求（P1-10 扩展：支持 source_view_id）。

    - value: 新值
    - changed_by: 修改人用户名（可选）
    - source_view_id: 来源视图 ID（可选）。传入时表示在小表中编辑共享字段，
      会自动写入 PatentHistory.source_view_id/source_view_name，并将 source 标记为 view_edit。
    """
    value: Any
    changed_by: Optional[str] = None
    source_view_id: Optional[int] = None


def _resolve_field_display_name(db: Session, field_key: str) -> str:
    """根据 field_key 解析可读的显示名"""
    sys_meta = get_system_field_meta(field_key)
    if sys_meta:
        return sys_meta.get("name") or field_key
    # 自定义字段
    from app.models import CustomField
    cf = db.query(CustomField).filter(CustomField.key == field_key).first()
    if cf:
        return cf.name
    return field_key


def _resolve_view_info(db: Session, view_id: Optional[int]) -> tuple[Optional[int], Optional[str], str]:
    """P1-10：解析 source_view_id 为 (view_id, view_name, source)。

    - view_id 为空 → (None, None, "manual")  大表直接编辑
    - view_id 有效 → (id, name, "view_edit")  小表编辑共享字段
    - view_id 无效 → 抛 400
    """
    if view_id is None:
        return None, None, "manual"
    from app.models import PatentView
    view = db.query(PatentView).filter(PatentView.id == view_id).first()
    if not view:
        raise HTTPException(status_code=400, detail=f"视图不存在：{view_id}")
    return view.id, view.name, "view_edit"


@router.patch("/patents/{patent_id}/field/{field_key}")
def update_cell(
    patent_id: int,
    field_key: str,
    req: CellUpdateRequest,
    db: Session = Depends(get_db),
):
    """更新单个字段值（P1-10：合并了 views.py 中的重复端点）。

    - 系统字段直接 setattr；custom_fields.{key} 更新 Patent.custom_fields
    - 自动写入 PatentHistory；source 由 source_view_id 决定（manual / view_edit）
    - 若传入 source_view_id，会同时记录 source_view_name，便于追溯"从哪个小表改的"
    """
    patent = db.query(Patent).filter(Patent.id == patent_id).first()
    if not patent:
        raise HTTPException(status_code=404, detail="Patent not found")

    source_view_id, source_view_name, source = _resolve_view_info(db, req.source_view_id)

    history_entry = None
    if field_key in SYSTEM_FIELD_KEYS:
        if field_key in ("id", "created_at", "updated_at"):
            raise HTTPException(status_code=400, detail=f"Field '{field_key}' is read-only")
        value = req.value
        if field_key in ("filing_date", "publication_date", "grant_date", "priority_date", "legal_status_date") and value:
            try:
                value = date.fromisoformat(value)
            except (ValueError, TypeError):
                pass
        if field_key == "has_risk":
            value = bool(value) if value is not None else False
        old_value = getattr(patent, field_key)
        if _is_value_changed(old_value, value):
            history_entry = PatentHistory(
                patent_id=patent.id,
                field_key=field_key,
                field_display_name=_resolve_field_display_name(db, field_key),
                old_value=_stringify_value(old_value),
                new_value=_stringify_value(value),
                source=source,
                changed_by=req.changed_by,
                source_view_id=source_view_id,
                source_view_name=source_view_name,
            )
        setattr(patent, field_key, value)
    else:
        current = patent.custom_fields or {}
        old_v = current.get(field_key)
        if _is_value_changed(old_v, req.value):
            history_entry = PatentHistory(
                patent_id=patent.id,
                field_key=f"custom_fields.{field_key}",
                field_display_name=_resolve_field_display_name(db, field_key),
                old_value=_stringify_value(old_v),
                new_value=_stringify_value(req.value),
                source=source,
                changed_by=req.changed_by,
                source_view_id=source_view_id,
                source_view_name=source_view_name,
            )
        current[field_key] = req.value
        patent.custom_fields = current

    db.add(patent)
    if history_entry:
        db.add(history_entry)
    db.commit()
    db.refresh(patent)
    return {
        "success": True,
        "patent_id": patent.id,
        "field_key": field_key,
        "source_view_id": source_view_id,
        "source_view_name": source_view_name,
    }


@router.post("/patents/{patent_id}/fields")
def update_fields_batch(
    patent_id: int,
    updates: dict[str, Any],
    db: Session = Depends(get_db),
):
    patent = db.query(Patent).filter(Patent.id == patent_id).first()
    if not patent:
        raise HTTPException(status_code=404, detail="Patent not found")
    PatentService.update_patent(db, patent, updates, source="manual")
    return {"success": True}
