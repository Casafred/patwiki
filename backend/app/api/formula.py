"""公式字段 API。"""
from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import CustomField
from app.services.formula_engine import FormulaError
from app.services.formula_service import FormulaService


router = APIRouter(prefix="/formula", tags=["formula"])


class FormulaFieldCreateRequest(BaseModel):
    key: str = Field(min_length=1, max_length=100)
    name: str = Field(min_length=1, max_length=200)
    expression: str = Field(min_length=1, max_length=2000)
    return_type: str = "text"
    group_name: str = "公式"
    description: Optional[str] = None
    sort_order: int = 0
    is_active: bool = True


class FormulaFieldUpdateRequest(BaseModel):
    name: Optional[str] = None
    expression: Optional[str] = Field(default=None, max_length=2000)
    return_type: Optional[str] = None
    group_name: Optional[str] = None
    description: Optional[str] = None
    sort_order: Optional[int] = None
    is_active: Optional[bool] = None


class FormulaValidateRequest(BaseModel):
    expression: str = Field(min_length=1, max_length=2000)
    formula_key: Optional[str] = None


class FormulaRecalculateRequest(BaseModel):
    patent_ids: Optional[list[int]] = None


def _formula_error(exc: FormulaError) -> HTTPException:
    return HTTPException(status_code=400, detail=str(exc))


@router.get("/fields")
def list_formula_fields(db: Session = Depends(get_db)):
    return [FormulaService.serialize_field(db, field) for field in FormulaService._formula_fields(db)]


@router.post("/fields")
def create_formula_field(body: FormulaFieldCreateRequest, db: Session = Depends(get_db)):
    try:
        field = FormulaService.create_formula_field(db, **body.model_dump())
    except FormulaError as exc:
        raise _formula_error(exc) from exc
    return FormulaService.serialize_field(db, field)


@router.put("/fields/{field_id}")
def update_formula_field(field_id: int, body: FormulaFieldUpdateRequest, db: Session = Depends(get_db)):
    field = db.query(CustomField).filter(CustomField.id == field_id).first()
    if not field:
        raise HTTPException(status_code=404, detail="公式字段不存在")
    updates = body.model_dump(exclude_unset=True)
    if "return_type" in updates:
        config = dict(field.formula_config or {})
        config["return_type"] = updates.pop("return_type")
        updates["formula_config"] = config
    try:
        field = FormulaService.update_formula_field(db, field, updates)
    except FormulaError as exc:
        raise _formula_error(exc) from exc
    return FormulaService.serialize_field(db, field)


@router.delete("/fields/{field_id}")
def delete_formula_field(field_id: int, db: Session = Depends(get_db)):
    field = db.query(CustomField).filter(CustomField.id == field_id).first()
    if not field:
        raise HTTPException(status_code=404, detail="公式字段不存在")
    try:
        FormulaService.delete_formula_field(db, field)
    except FormulaError as exc:
        raise _formula_error(exc) from exc
    return {"success": True}


@router.post("/validate")
def validate_formula(body: FormulaValidateRequest, db: Session = Depends(get_db)):
    try:
        _, dependencies = FormulaService.validate_expression(db, body.expression, body.formula_key)
        FormulaService._ensure_acyclic(db, body.formula_key, dependencies) if body.formula_key else None
    except FormulaError as exc:
        return {"valid": False, "expression": body.expression, "dependencies": [], "error": str(exc)}
    return {
        "valid": True,
        "expression": body.expression,
        "dependencies": sorted(dependencies),
        "error": None,
    }


@router.get("/functions")
def list_formula_functions():
    return FormulaService.functions()


@router.post("/recalculate/{formula_key}")
def recalculate_formula(
    formula_key: str,
    body: FormulaRecalculateRequest = FormulaRecalculateRequest(),
    db: Session = Depends(get_db),
):
    try:
        return FormulaService.recalculate_all(db, formula_key=formula_key, patent_ids=body.patent_ids)
    except FormulaError as exc:
        raise _formula_error(exc) from exc

