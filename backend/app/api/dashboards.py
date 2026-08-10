"""Configurable dashboard API."""
from __future__ import annotations

from typing import Optional
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Dashboard, PatentDatabase
from app.schemas.schemas import DashboardCard, DashboardCardUpdate, DashboardCreate, DashboardUpdate
from app.services.dashboard_service import DashboardService


router = APIRouter(prefix="/dashboards", tags=["dashboards"])


def _dashboard_dict(dashboard: Dashboard) -> dict:
    return {
        "id": dashboard.id,
        "database_id": dashboard.database_id,
        "name": dashboard.name,
        "description": dashboard.description,
        "layout": DashboardService.normalize_layout(dashboard.layout or []),
        "created_at": dashboard.created_at.isoformat() if dashboard.created_at else None,
        "updated_at": dashboard.updated_at.isoformat() if dashboard.updated_at else None,
    }


def _get_dashboard(db: Session, dashboard_id: int) -> Dashboard:
    dashboard = db.query(Dashboard).filter(Dashboard.id == dashboard_id).first()
    if not dashboard:
        raise HTTPException(status_code=404, detail="Dashboard not found")
    return dashboard


@router.get("")
def list_dashboards(database_id: Optional[int] = None, db: Session = Depends(get_db)):
    query = db.query(Dashboard)
    if database_id is not None:
        query = query.filter(Dashboard.database_id == database_id)
    return [_dashboard_dict(item) for item in query.order_by(Dashboard.id).all()]


@router.post("")
def create_dashboard(body: DashboardCreate, db: Session = Depends(get_db)):
    if not db.query(PatentDatabase).filter(PatentDatabase.id == body.database_id).first():
        raise HTTPException(status_code=404, detail="Database not found")
    try:
        layout = DashboardService.normalize_layout(body.layout)
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    dashboard = Dashboard(
        database_id=body.database_id,
        name=body.name.strip(),
        description=body.description,
        layout=layout,
    )
    db.add(dashboard)
    db.commit()
    db.refresh(dashboard)
    return _dashboard_dict(dashboard)


@router.get("/{dashboard_id}")
def get_dashboard(dashboard_id: int, db: Session = Depends(get_db)):
    return _dashboard_dict(_get_dashboard(db, dashboard_id))


@router.put("/{dashboard_id}")
def update_dashboard(dashboard_id: int, body: DashboardUpdate, db: Session = Depends(get_db)):
    dashboard = _get_dashboard(db, dashboard_id)
    updates = body.model_dump(exclude_unset=True)
    if "layout" in updates:
        try:
            updates["layout"] = DashboardService.normalize_layout(updates["layout"])
        except (TypeError, ValueError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
    for key, value in updates.items():
        if key == "name" and value is not None:
            value = value.strip()
        setattr(dashboard, key, value)
    db.add(dashboard)
    db.commit()
    db.refresh(dashboard)
    return _dashboard_dict(dashboard)


@router.delete("/{dashboard_id}")
def delete_dashboard(dashboard_id: int, db: Session = Depends(get_db)):
    dashboard = _get_dashboard(db, dashboard_id)
    db.delete(dashboard)
    db.commit()
    return {"success": True}


@router.get("/{dashboard_id}/data")
def get_dashboard_data(dashboard_id: int, view_id: Optional[int] = Query(None), db: Session = Depends(get_db)):
    dashboard = _get_dashboard(db, dashboard_id)
    try:
        return DashboardService.get_data(db, dashboard, view_id=view_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/{dashboard_id}/cards")
def add_dashboard_card(dashboard_id: int, body: DashboardCard, db: Session = Depends(get_db)):
    dashboard = _get_dashboard(db, dashboard_id)
    raw = body.model_dump()
    raw["id"] = raw.get("id") or f"card_{uuid4().hex[:10]}"
    try:
        card = DashboardService.normalize_card(raw, len(dashboard.layout or []))
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    dashboard.layout = [*(dashboard.layout or []), card]
    db.add(dashboard)
    db.commit()
    db.refresh(dashboard)
    return card


@router.put("/{dashboard_id}/cards/{card_id}")
def update_dashboard_card(dashboard_id: int, card_id: str, body: DashboardCardUpdate, db: Session = Depends(get_db)):
    dashboard = _get_dashboard(db, dashboard_id)
    cards = list(dashboard.layout or [])
    current = next((item for item in cards if item.get("id") == card_id), None)
    if current is None:
        raise HTTPException(status_code=404, detail="Dashboard card not found")
    raw = {**current, **body.model_dump(exclude_unset=True)}
    raw["id"] = card_id
    try:
        updated = DashboardService.normalize_card(raw, cards.index(current))
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    cards[cards.index(current)] = updated
    dashboard.layout = cards
    db.add(dashboard)
    db.commit()
    db.refresh(dashboard)
    return updated


@router.delete("/{dashboard_id}/cards/{card_id}")
def delete_dashboard_card(dashboard_id: int, card_id: str, db: Session = Depends(get_db)):
    dashboard = _get_dashboard(db, dashboard_id)
    cards = [item for item in (dashboard.layout or []) if item.get("id") != card_id]
    if len(cards) == len(dashboard.layout or []):
        raise HTTPException(status_code=404, detail="Dashboard card not found")
    dashboard.layout = cards
    db.add(dashboard)
    db.commit()
    return {"success": True}
