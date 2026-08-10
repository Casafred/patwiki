from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Any
from datetime import date

from app.database import get_db
from app.models import CustomField, CustomFieldType, Patent, PatentHistory
from app.services.field_registry import get_all_fields_meta, SYSTEM_FIELD_KEYS, get_system_field_meta
from app.services.patent_service import PatentService, _is_value_changed, _stringify_value
from app.services.formula_service import FormulaService
from app.core.exceptions import BadRequestException, NotFoundException

router = APIRouter(tags=["fields"])


@router.get("/fields")
def list_fields(db: Session = Depends(get_db)):
    return get_all_fields_meta(db)


class CellUpdateRequest(BaseModel):
    value: Any


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


@router.patch("/patents/{patent_id}/field/{field_key}")
def update_cell(
    patent_id: int,
    field_key: str,
    req: CellUpdateRequest,
    db: Session = Depends(get_db),
):
    patent = db.query(Patent).filter(Patent.id == patent_id).first()
    if not patent:
        raise NotFoundException("Patent not found")

    history_entry = None
    if field_key in SYSTEM_FIELD_KEYS:
        if field_key in ("id", "created_at", "updated_at"):
            raise BadRequestException(f"Field '{field_key}' is read-only")
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
                source="manual",
            )
        setattr(patent, field_key, value)
    else:
        custom_field = db.query(CustomField).filter(CustomField.key == field_key).first()
        if custom_field and custom_field.field_type == CustomFieldType.FORMULA:
            raise BadRequestException("公式字段为只读字段，不能直接编辑")
        # JSON 列没有 MutableDict 追踪，先复制再赋值才能稳定触发更新。
        current = dict(patent.custom_fields or {})
        old_v = current.get(field_key)
        if _is_value_changed(old_v, req.value):
            history_entry = PatentHistory(
                patent_id=patent.id,
                field_key=f"custom_fields.{field_key}",
                field_display_name=_resolve_field_display_name(db, field_key),
                old_value=_stringify_value(old_v),
                new_value=_stringify_value(req.value),
                source="manual",
            )
        current[field_key] = req.value
        patent.custom_fields = current

    db.add(patent)
    if history_entry:
        db.add(history_entry)
    db.commit()
    db.refresh(patent)
    FormulaService.on_field_changed(db, patent, [field_key])
    return {"success": True}


@router.post("/patents/{patent_id}/fields")
def update_fields_batch(
    patent_id: int,
    updates: dict[str, Any],
    db: Session = Depends(get_db),
):
    patent = db.query(Patent).filter(Patent.id == patent_id).first()
    if not patent:
        raise NotFoundException("Patent not found")
    PatentService.update_patent(db, patent, updates, source="manual")
    return {"success": True}
