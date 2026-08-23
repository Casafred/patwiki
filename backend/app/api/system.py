"""Read-only diagnostics for migration and field-governance evidence."""
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.database import engine, get_db
from app.services.field_governance_service import (
    governance_summary,
    list_field_definitions,
    list_source_mappings,
    list_source_tables,
)
from app.services.migration_service import get_integrity_report, list_migration_runs


router = APIRouter(tags=["system"])


@router.get("/system/migrations")
def get_migration_runs(
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
):
    return {"items": list_migration_runs(db, limit=limit)}


@router.get("/system/integrity")
def get_database_integrity():
    return get_integrity_report(engine)


@router.get("/system/field-governance/summary")
def get_field_governance_summary(db: Session = Depends(get_db)):
    return governance_summary(db)


@router.get("/system/field-governance/tables")
def get_source_tables(db: Session = Depends(get_db)):
    return {"items": list_source_tables(db)}


@router.get("/system/field-governance/fields")
def get_canonical_fields(
    limit: int = Query(500, ge=1, le=2000),
    db: Session = Depends(get_db),
):
    return {"items": list_field_definitions(db, limit=limit)}


@router.get("/system/field-governance/mappings")
def get_source_field_mappings(
    status: str | None = Query(None),
    limit: int = Query(1000, ge=1, le=5000),
    db: Session = Depends(get_db),
):
    return {"items": list_source_mappings(db, status=status, limit=limit)}
