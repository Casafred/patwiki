"""Event-driven automation engine for patent records."""
from __future__ import annotations

from contextvars import ContextVar
from datetime import date, datetime, timedelta, timezone
from typing import Any, Optional

from sqlalchemy.orm import Session

from app.models import (
    AutomationLog,
    AutomationRule,
    Patent,
    Project,
    Tag,
    patent_project,
)
from app.services.patent_service import PatentService, SYSTEM_FIELDS


_execution_stack: ContextVar[tuple[tuple[int, int], ...]] = ContextVar(
    "automation_execution_stack", default=()
)


def _field_value(patent: Patent, field_key: str) -> Any:
    if field_key.startswith("custom_fields."):
        return (patent.custom_fields or {}).get(field_key[len("custom_fields."):])
    if field_key.startswith("ai_fields."):
        return (patent.ai_fields or {}).get(field_key[len("ai_fields."):])
    if field_key in SYSTEM_FIELDS or hasattr(patent, field_key):
        value = getattr(patent, field_key, None)
        return value.value if hasattr(value, "value") else value
    return (patent.custom_fields or {}).get(field_key)


def _empty(value: Any) -> bool:
    return value is None or value == "" or value == []


def _matches(value: Any, condition: dict[str, Any]) -> bool:
    op = condition.get("op", "==")
    expected = condition.get("value")
    if op == "is_empty":
        return _empty(value)
    if op == "is_not_empty":
        return not _empty(value)
    if _empty(value):
        return False
    if op == "contains":
        if isinstance(value, list):
            return any(str(expected).casefold() in str(item).casefold() for item in value)
        return str(expected).casefold() in str(value).casefold()
    if op == "starts_with":
        return str(value).casefold().startswith(str(expected).casefold())
    if op == "ends_with":
        return str(value).casefold().endswith(str(expected).casefold())
    if op in {">", "<", ">=", "<="}:
        try:
            left, right = float(value), float(expected)
        except (TypeError, ValueError):
            left, right = str(value), str(expected)
        return {">": left > right, "<": left < right, ">=": left >= right, "<=": left <= right}[op]
    if op == "!=":
        return str(value).casefold() != str(expected).casefold()
    return str(value).casefold() == str(expected).casefold()


def _serialize(value: Any) -> Any:
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if hasattr(value, "value"):
        return value.value
    if isinstance(value, dict):
        return {str(key): _serialize(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_serialize(item) for item in value]
    return value


class AutomationEngine:
    """Execute enabled rules while preventing same-rule recursion."""

    TRIGGERS = {"field_changed", "record_created", "record_imported", "schedule", "manual"}
    ACTIONS = {"set_field", "link_to_project", "send_notification", "add_tag", "remove_tag", "move_to_view"}

    @staticmethod
    def _now() -> datetime:
        """Use a naive UTC value because the existing SQLite DateTime columns are naive."""
        return datetime.now(timezone.utc).replace(tzinfo=None)

    @classmethod
    def validate_config(
        cls,
        trigger_config: dict[str, Any],
        condition_config: list[dict[str, Any]],
        action_config: list[dict[str, Any]],
    ) -> tuple[dict[str, Any], list[dict[str, Any]], list[dict[str, Any]]]:
        if not isinstance(trigger_config, dict):
            raise ValueError("trigger_config must be an object")
        trigger_type = str(trigger_config.get("type", "manual"))
        if trigger_type not in cls.TRIGGERS:
            raise ValueError(f"不支持的自动化触发器：{trigger_type}")
        trigger = {"type": trigger_type}
        if trigger_type == "field_changed":
            field = str(trigger_config.get("field", "")).strip()
            if not field:
                raise ValueError("字段变更触发器需要 field")
            trigger["field"] = field
        if trigger_type == "schedule":
            schedule = str(trigger_config.get("schedule", "")).strip()
            if not schedule:
                raise ValueError("定时触发器需要 schedule")
            trigger["schedule"] = schedule
            interval = trigger_config.get("interval_minutes")
            if interval is None and schedule.startswith("every:"):
                interval = schedule.removeprefix("every:")
            if interval is not None:
                try:
                    interval = int(interval)
                except (TypeError, ValueError) as exc:
                    raise ValueError("interval_minutes 必须是正整数") from exc
                if interval <= 0 or interval > 60 * 24 * 365:
                    raise ValueError("interval_minutes 必须在 1 到 525600 之间")
                trigger["interval_minutes"] = interval

        if not isinstance(condition_config, list) or len(condition_config) > 20:
            raise ValueError("自动化条件必须是最多 20 项的数组")
        conditions = []
        allowed_ops = {"==", "!=", ">", "<", ">=", "<=", "contains", "starts_with", "ends_with", "is_empty", "is_not_empty"}
        for condition in condition_config:
            if not isinstance(condition, dict) or not str(condition.get("field", "")).strip():
                raise ValueError("自动化条件需要 field")
            op = str(condition.get("op", "=="))
            if op not in allowed_ops:
                raise ValueError(f"不支持的自动化条件：{op}")
            conditions.append({"field": str(condition["field"]).strip(), "op": op, "value": condition.get("value")})

        if not isinstance(action_config, list) or not action_config or len(action_config) > 20:
            raise ValueError("自动化动作必须是 1 到 20 项的数组")
        actions = []
        for action in action_config:
            if not isinstance(action, dict):
                raise ValueError("自动化动作必须是对象")
            action_type = str(action.get("type", "")).strip()
            if action_type not in cls.ACTIONS:
                raise ValueError(f"不支持的自动化动作：{action_type}")
            normalized = {"type": action_type}
            if action_type == "set_field":
                field = str(action.get("field", "")).strip()
                if not field:
                    raise ValueError("set_field 动作需要 field")
                normalized.update(field=field, value=action.get("value"))
            elif action_type == "link_to_project":
                try:
                    normalized["project_id"] = int(action["project_id"])
                except (KeyError, TypeError, ValueError) as exc:
                    raise ValueError("link_to_project 动作需要有效 project_id") from exc
            elif action_type in {"add_tag", "remove_tag"}:
                if action.get("tag_id") is None and not str(action.get("tag", "")).strip():
                    raise ValueError(f"{action_type} 动作需要 tag 或 tag_id")
                if action.get("tag_id") is not None:
                    try:
                        normalized["tag_id"] = int(action["tag_id"])
                    except (TypeError, ValueError) as exc:
                        raise ValueError("tag_id 必须是整数") from exc
                if action.get("tag"):
                    normalized["tag"] = str(action["tag"]).strip()
            elif action_type == "send_notification":
                normalized["message"] = str(action.get("message", "专利自动化规则已执行"))[:2000]
                normalized["channel"] = str(action.get("channel", "in_app"))
            elif action_type == "move_to_view":
                try:
                    normalized["view_id"] = int(action["view_id"])
                except (KeyError, TypeError, ValueError) as exc:
                    raise ValueError("move_to_view 动作需要有效 view_id") from exc
                normalized["action"] = str(action.get("action", "add"))
            actions.append(normalized)
        return trigger, conditions, actions

    @classmethod
    def _matches_trigger(cls, rule: AutomationRule, event_type: str, field_changes: set[str]) -> bool:
        trigger = rule.trigger_config or {}
        trigger_type = trigger.get("type")
        if trigger_type != event_type:
            return False
        if event_type == "field_changed":
            field = str(trigger.get("field", ""))
            return field in field_changes or field.removeprefix("custom_fields.") in field_changes
        return True

    @classmethod
    def _check_conditions(cls, patent: Patent, conditions: list[dict[str, Any]]) -> bool:
        return all(_matches(_field_value(patent, condition["field"]), condition) for condition in conditions)

    @classmethod
    def _find_tag(cls, db: Session, action: dict[str, Any]) -> Optional[Tag]:
        if action.get("tag_id") is not None:
            return db.query(Tag).filter(Tag.id == action["tag_id"]).first()
        return db.query(Tag).filter(Tag.name == action.get("tag")).first()

    @classmethod
    def _execute_actions(cls, db: Session, patent: Patent, actions: list[dict[str, Any]]) -> dict[str, Any]:
        details: dict[str, Any] = {"actions": [], "notifications": []}
        for action in actions:
            action_type = action["type"]
            if action_type == "set_field":
                field = action["field"]
                update = {field: action.get("value")} if field in SYSTEM_FIELDS else {"custom_fields": {field.removeprefix("custom_fields."): action.get("value")}}
                PatentService.update_patent(db, patent, update, source="automation")
                details["actions"].append({"type": action_type, "field": field})
            elif action_type == "link_to_project":
                project = db.query(Project).filter(Project.id == action["project_id"]).first()
                if not project:
                    raise ValueError(f"项目 {action['project_id']} 不存在")
                if project not in patent.projects:
                    patent.projects.append(project)
                    db.add(patent)
                    db.commit()
                details["actions"].append({"type": action_type, "project_id": project.id})
            elif action_type in {"add_tag", "remove_tag"}:
                tag = cls._find_tag(db, action)
                if not tag:
                    raise ValueError("目标标签不存在")
                if action_type == "add_tag" and tag not in patent.tags:
                    patent.tags.append(tag)
                elif action_type == "remove_tag" and tag in patent.tags:
                    patent.tags.remove(tag)
                db.add(patent)
                db.commit()
                details["actions"].append({"type": action_type, "tag_id": tag.id})
            elif action_type == "send_notification":
                details["notifications"].append({
                    "channel": action.get("channel", "in_app"),
                    "message": action.get("message", ""),
                    "patent_id": patent.id,
                })
                details["actions"].append({"type": action_type})
            elif action_type == "move_to_view":
                # Views are saved queries rather than membership tables. Keep the intent in the log
                # until a dedicated view-membership model is introduced.
                details["actions"].append({"type": action_type, "view_id": action["view_id"], "status": "recorded"})
        return details

    @classmethod
    def on_event(
        cls,
        db: Session,
        event_type: str,
        patent_id: Optional[int] = None,
        database_id: Optional[int] = None,
        field_changes: Optional[set[str]] = None,
        only_rule_id: Optional[int] = None,
    ) -> list[dict[str, Any]]:
        if event_type not in cls.TRIGGERS:
            return []
        if patent_id is not None:
            patent = db.query(Patent).filter(Patent.id == patent_id).first()
            if not patent:
                return []
            database_id = patent.database_id
        rules = db.query(AutomationRule).filter(
            AutomationRule.database_id == database_id,
            AutomationRule.is_enabled == True,
        ).order_by(AutomationRule.priority.asc(), AutomationRule.id.asc()).all()
        if only_rule_id is not None:
            rules = [rule for rule in rules if rule.id == only_rule_id]
        changes = field_changes or set()
        results: list[dict[str, Any]] = []
        for rule in rules:
            if not cls._matches_trigger(rule, event_type, changes):
                continue
            if patent_id is None:
                continue
            patent = db.query(Patent).filter(Patent.id == patent_id).first()
            if not patent or not cls._check_conditions(patent, rule.condition_config or []):
                cls._write_log(db, rule, patent_id, event_type, "skipped", details={"reason": "conditions_not_met"})
                results.append({"rule_id": rule.id, "status": "skipped"})
                continue
            key = (rule.id, patent_id)
            stack = _execution_stack.get()
            if key in stack or len(stack) >= 8:
                cls._write_log(db, rule, patent_id, event_type, "skipped", details={"reason": "recursion_guard"})
                results.append({"rule_id": rule.id, "status": "skipped"})
                continue
            token = _execution_stack.set((*stack, key))
            try:
                details = cls._execute_actions(db, patent, rule.action_config or [])
                rule.execution_count = (rule.execution_count or 0) + 1
                rule.last_executed_at = cls._now()
                db.add(rule)
                db.commit()
                cls._write_log(db, rule, patent_id, event_type, "success", details=details)
                results.append({"rule_id": rule.id, "status": "success", "details": details})
            except Exception as exc:
                db.rollback()
                rule.failure_count = (rule.failure_count or 0) + 1
                db.add(rule)
                db.commit()
                cls._write_log(db, rule, patent_id, event_type, "failed", error_message=str(exc))
                results.append({"rule_id": rule.id, "status": "failed", "error": str(exc)})
            finally:
                _execution_stack.reset(token)
        return results

    @classmethod
    def run_scheduled(
        cls,
        db: Session,
        database_id: Optional[int] = None,
        now: Optional[datetime] = None,
    ) -> list[dict[str, Any]]:
        """Run due schedule rules for every record in the selected database.

        The desktop app does not need a heavyweight scheduler dependency. The API and
        the application lifespan can call this small polling unit periodically.
        """
        current = now or cls._now()
        query = db.query(AutomationRule).filter(
            AutomationRule.is_enabled == True,
            AutomationRule.trigger_config["type"].as_string() == "schedule",
        )
        if database_id is not None:
            query = query.filter(AutomationRule.database_id == database_id)
        results: list[dict[str, Any]] = []
        for rule in query.order_by(AutomationRule.priority.asc(), AutomationRule.id.asc()).all():
            trigger = rule.trigger_config or {}
            interval = trigger.get("interval_minutes")
            if interval is None:
                schedule = str(trigger.get("schedule", "")).casefold()
                interval = {"hourly": 60, "daily": 1440, "weekly": 10080}.get(schedule)
            if interval is None:
                results.append({"rule_id": rule.id, "status": "skipped", "reason": "unsupported_schedule"})
                continue
            last_run = rule.last_executed_at
            if last_run and current - last_run < timedelta(minutes=int(interval)):
                results.append({"rule_id": rule.id, "status": "skipped", "reason": "not_due"})
                continue
            patent_ids = [row.id for row in db.query(Patent.id).filter(Patent.database_id == rule.database_id).all()]
            if not patent_ids:
                rule.last_executed_at = current
                db.add(rule)
                db.commit()
                results.append({"rule_id": rule.id, "status": "success", "processed": 0})
                continue
            rule_results = []
            for patent_id in patent_ids:
                rule_results.extend(cls.on_event(db, "schedule", patent_id=patent_id, only_rule_id=rule.id))
            results.append({"rule_id": rule.id, "status": "success", "processed": len(patent_ids), "results": rule_results})
        return results

    @staticmethod
    def _write_log(
        db: Session,
        rule: AutomationRule,
        patent_id: Optional[int],
        event_type: str,
        status: str,
        error_message: Optional[str] = None,
        details: Optional[dict[str, Any]] = None,
    ) -> AutomationLog:
        log = AutomationLog(
            rule_id=rule.id,
            patent_id=patent_id,
            trigger_type=event_type,
            status=status,
            error_message=error_message,
            details=details or {},
        )
        db.add(log)
        db.commit()
        db.refresh(log)
        return log
