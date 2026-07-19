from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Any
from datetime import date

from app.database import get_db
from app.models import Patent
from app.services.field_registry import get_all_fields_meta, SYSTEM_FIELD_KEYS
from app.services.patent_service import PatentService

router = APIRouter(tags=["fields"])


@router.get("/fields")
def list_fields(db: Session = Depends(get_db)):
    return get_all_fields_meta(db)


class CellUpdateRequest(BaseModel):
    value: Any


@router.patch("/patents/{patent_id}/field/{field_key}")
def update_cell(
    patent_id: int,
    field_key: str,
    req: CellUpdateRequest,
    db: Session = Depends(get_db),
):
    patent = db.query(Patent).filter(Patent.id == patent_id).first()
    if not patent:
        raise HTTPException(status_code=404, detail="Patent not found")

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
        setattr(patent, field_key, value)
    else:
        current = patent.custom_fields or {}
        current[field_key] = req.value
        patent.custom_fields = current

    db.add(patent)
    db.commit()
    db.refresh(patent)
    return {"success": True}


@router.post("/patents/{patent_id}/fields")
def update_fields_batch(
    patent_id: int,
    updates: dict[str, Any],
    db: Session = Depends(get_db),
):
    patent = db.query(Patent).filter(Patent.id == patent_id).first()
    if not patent:
        raise HTTPException(status_code=404, detail="Patent not found")
    PatentService.update_patent(db, patent, updates)
    return {"success": True}
