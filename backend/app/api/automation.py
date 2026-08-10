"""Automation rule management and execution API."""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import AutomationLog, AutomationRule, Patent, PatentDatabase
from app.schemas.schemas import AutomationManualExecuteRequest, AutomationRuleCreate, AutomationRuleUpdate
from app.services.automation_service import AutomationEngine
from app.core.exceptions import BadRequestException, NotFoundException


router = APIRouter(prefix="/automation", tags=["automation"])


def _rule_dict(rule: AutomationRule) -> dict:
    return {
        "id": rule.id,
        "database_id": rule.database_id,
        "name": rule.name,
        "description": rule.description,
        "is_enabled": rule.is_enabled,
        "priority": rule.priority,
        "trigger_config": rule.trigger_config or {},
        "condition_config": rule.condition_config or [],
        "action_config": rule.action_config or [],
        "last_executed_at": rule.last_executed_at.isoformat() if rule.last_executed_at else None,
        "execution_count": rule.execution_count or 0,
        "failure_count": rule.failure_count or 0,
        "created_at": rule.created_at.isoformat() if rule.created_at else None,
        "updated_at": rule.updated_at.isoformat() if rule.updated_at else None,
    }


def _validate_rule(rule_data: dict) -> tuple[dict, list[dict], list[dict]]:
    return AutomationEngine.validate_config(
        rule_data.get("trigger_config") or {},
        rule_data.get("condition_config") or [],
        rule_data.get("action_config") or [],
    )


@router.get("/rules")
def list_rules(database_id: Optional[int] = None, include_disabled: bool = True, db: Session = Depends(get_db)):
    query = db.query(AutomationRule)
    if database_id is not None:
        query = query.filter(AutomationRule.database_id == database_id)
    if not include_disabled:
        query = query.filter(AutomationRule.is_enabled == True)
    return [_rule_dict(rule) for rule in query.order_by(AutomationRule.priority, AutomationRule.id).all()]


@router.post("/rules")
def create_rule(body: AutomationRuleCreate, db: Session = Depends(get_db)):
    if not db.query(PatentDatabase).filter(PatentDatabase.id == body.database_id).first():
        raise NotFoundException("Database not found")
    try:
        trigger, conditions, actions = _validate_rule(body.model_dump())
    except ValueError as exc:
        raise BadRequestException(str(exc)) from exc
    rule = AutomationRule(
        database_id=body.database_id,
        name=body.name.strip(),
        description=body.description,
        is_enabled=body.is_enabled,
        priority=body.priority,
        trigger_config=trigger,
        condition_config=conditions,
        action_config=actions,
    )
    db.add(rule)
    db.commit()
    db.refresh(rule)
    return _rule_dict(rule)


@router.get("/rules/{rule_id}")
def get_rule(rule_id: int, db: Session = Depends(get_db)):
    rule = db.query(AutomationRule).filter(AutomationRule.id == rule_id).first()
    if not rule:
        raise NotFoundException("Automation rule not found")
    return _rule_dict(rule)


@router.put("/rules/{rule_id}")
def update_rule(rule_id: int, body: AutomationRuleUpdate, db: Session = Depends(get_db)):
    rule = db.query(AutomationRule).filter(AutomationRule.id == rule_id).first()
    if not rule:
        raise NotFoundException("Automation rule not found")
    updates = body.model_dump(exclude_unset=True)
    try:
        trigger, conditions, actions = AutomationEngine.validate_config(
            updates.get("trigger_config", rule.trigger_config or {}),
            updates.get("condition_config", rule.condition_config or []),
            updates.get("action_config", rule.action_config or []),
        )
    except ValueError as exc:
        raise BadRequestException(str(exc)) from exc
    updates["trigger_config"] = trigger
    updates["condition_config"] = conditions
    updates["action_config"] = actions
    for key, value in updates.items():
        if key == "name" and value is not None:
            value = value.strip()
        setattr(rule, key, value)
    db.add(rule)
    db.commit()
    db.refresh(rule)
    return _rule_dict(rule)


@router.delete("/rules/{rule_id}")
def delete_rule(rule_id: int, db: Session = Depends(get_db)):
    rule = db.query(AutomationRule).filter(AutomationRule.id == rule_id).first()
    if not rule:
        raise NotFoundException("Automation rule not found")
    db.delete(rule)
    db.commit()
    return {"success": True}


@router.post("/rules/{rule_id}/toggle")
def toggle_rule(rule_id: int, db: Session = Depends(get_db)):
    rule = db.query(AutomationRule).filter(AutomationRule.id == rule_id).first()
    if not rule:
        raise NotFoundException("Automation rule not found")
    rule.is_enabled = not rule.is_enabled
    db.add(rule)
    db.commit()
    db.refresh(rule)
    return _rule_dict(rule)


@router.post("/rules/{rule_id}/execute")
def execute_rule(rule_id: int, body: AutomationManualExecuteRequest, db: Session = Depends(get_db)):
    rule = db.query(AutomationRule).filter(AutomationRule.id == rule_id).first()
    if not rule:
        raise NotFoundException("Automation rule not found")
    if not rule.is_enabled:
        raise BadRequestException("自动化规则已禁用")
    if body.patent_id is None:
        raise BadRequestException("手动执行需要 patent_id")
    database = db.query(PatentDatabase).filter(PatentDatabase.id == rule.database_id).first()
    if not database:
        raise NotFoundException("Database not found")
    patent = db.query(Patent).filter(
        Patent.id == body.patent_id,
        Patent.database_id == rule.database_id,
    ).first()
    if not patent:
        raise NotFoundException("Patent not found in rule database")
    result = AutomationEngine.on_event(db, "manual", patent_id=body.patent_id)
    return {"rule_id": rule.id, "results": [item for item in result if item["rule_id"] == rule.id]}


@router.post("/schedule/tick")
def run_schedule_tick(database_id: Optional[int] = None, db: Session = Depends(get_db)):
    return {"results": AutomationEngine.run_scheduled(db, database_id=database_id)}


@router.get("/logs")
def list_logs(
    database_id: Optional[int] = None,
    rule_id: Optional[int] = None,
    patent_id: Optional[int] = None,
    status: Optional[str] = Query(None, pattern="^(success|failed|skipped)$"),
    limit: int = Query(100, ge=1, le=500),
    db: Session = Depends(get_db),
):
    query = db.query(AutomationLog).join(AutomationRule)
    if database_id is not None:
        query = query.filter(AutomationRule.database_id == database_id)
    if rule_id is not None:
        query = query.filter(AutomationLog.rule_id == rule_id)
    if patent_id is not None:
        query = query.filter(AutomationLog.patent_id == patent_id)
    if status:
        query = query.filter(AutomationLog.status == status)
    return [{
        "id": log.id,
        "rule_id": log.rule_id,
        "patent_id": log.patent_id,
        "trigger_type": log.trigger_type,
        "status": log.status,
        "error_message": log.error_message,
        "details": log.details or {},
        "executed_at": log.executed_at.isoformat() if log.executed_at else None,
    } for log in query.order_by(AutomationLog.id.desc()).limit(limit).all()]
