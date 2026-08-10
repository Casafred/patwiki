"""表单视图配置、提交和公开分享服务。"""
from __future__ import annotations

import secrets
from datetime import date, datetime, timedelta, timezone
from typing import Any, Optional

from sqlalchemy.orm import Session

from app.models import FormShareLink, Patent, PatentView
from app.schemas.schemas import PatentCreate
from app.services.field_registry import SYSTEM_FIELD_KEYS, get_all_fields_meta
from app.services.patent_service import SYSTEM_FIELDS, PatentService
from app.services.view_service import (
    ViewService,
    _get_item_field_value,
    _matches_condition,
    _patent_to_dict,
)


DEFAULT_FORM_FIELDS = [
    {"key": "application_number", "required": False, "col_span": 1},
    {"key": "title", "required": True, "col_span": 2},
    {"key": "applicant", "required": False, "col_span": 1},
    {"key": "inventor", "required": False, "col_span": 1},
    {"key": "filing_date", "required": False, "col_span": 1},
    {"key": "patent_type", "required": False, "col_span": 1},
    {"key": "legal_status", "required": False, "col_span": 1},
    {"key": "risk_level", "required": False, "col_span": 1},
    {"key": "category", "required": False, "col_span": 1},
    {"key": "notes", "required": False, "col_span": 2},
]


def _utc_now() -> datetime:
    """Return a naive UTC timestamp compatible with the existing DateTime columns."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


class FormService:
    """表单视图的唯一业务入口。"""

    @staticmethod
    def _field_meta(db: Session, view: PatentView) -> dict[str, dict[str, Any]]:
        result = {field["key"]: dict(field) for field in get_all_fields_meta(db)}
        for field in view.local_fields:
            result[f"view_local.{field.key}"] = {
                "key": f"view_local.{field.key}",
                "name": field.name,
                "field_type": field.field_type,
                "options": field.options,
                "description": field.description,
                "is_required": field.is_required,
                "editable": True,
                "is_system": False,
                "is_local": True,
            }
        return result

    @classmethod
    def normalize_config(cls, db: Session, view: PatentView) -> tuple[dict[str, Any], dict[str, dict[str, Any]]]:
        config = ViewService.validate_form_config(view.form_config)
        if not config["sections"]:
            config["sections"] = [{"title": "专利信息", "fields": list(DEFAULT_FORM_FIELDS)}]
        field_meta = cls._field_meta(db, view)
        seen: set[str] = set()
        for section in config["sections"]:
            for field in section["fields"]:
                key = field["key"]
                if key not in field_meta:
                    raise ValueError(f"表单字段不存在：{key}")
                if not field_meta[key].get("editable", True) or field_meta[key].get("is_formula"):
                    raise ValueError(f"字段不可在表单中编辑：{key}")
                if key in seen:
                    raise ValueError(f"表单字段重复：{key}")
                seen.add(key)
        return config, field_meta

    @staticmethod
    def _public_field(meta: dict[str, Any]) -> dict[str, Any]:
        return {
            "key": meta.get("key"),
            "name": meta.get("name"),
            "field_type": meta.get("field_type"),
            "options": meta.get("options"),
            "description": meta.get("description"),
            "is_required": bool(meta.get("is_required", False)),
        }

    @classmethod
    def get_definition(cls, db: Session, view: PatentView, public: bool = False) -> dict[str, Any]:
        config, field_meta = cls.normalize_config(db, view)
        keys = [field["key"] for section in config["sections"] for field in section["fields"]]
        return {
            "view_id": view.id,
            "view_name": view.name,
            "database_id": view.database_id,
            "config": config,
            "fields": [cls._public_field(field_meta[key]) for key in keys],
            "public": public,
        }

    @staticmethod
    def _current_values(db: Session, view: PatentView, patent: Optional[Patent]) -> dict[str, Any]:
        if not patent:
            return {}
        item = ViewService.get_view_patent_with_local_fields(db, view, patent)
        values = dict(_patent_to_dict(patent))
        values.update(item)
        for key in SYSTEM_FIELD_KEYS:
            if hasattr(patent, key):
                value = getattr(patent, key)
                if hasattr(value, "value"):
                    value = value.value
                elif isinstance(value, (date, datetime)):
                    value = value.isoformat()
                values[key] = value
        for key, value in (patent.custom_fields or {}).items():
            values[key] = value
        for key, value in (item.get("view_local_fields") or {}).items():
            values[f"view_local.{key}"] = value
        return values

    @staticmethod
    def _is_empty(value: Any) -> bool:
        return value is None or value == "" or value == []

    @staticmethod
    def _is_visible(field_config: dict[str, Any], values: dict[str, Any]) -> bool:
        condition = field_config.get("visible_when")
        if not condition:
            return True
        field_key = condition.get("field")
        if not field_key:
            return True
        return _matches_condition(values.get(field_key), condition)

    @staticmethod
    def _coerce_value(meta: dict[str, Any], value: Any) -> Any:
        if FormService._is_empty(value):
            return None
        field_type = str(meta.get("field_type") or "text")
        if field_type == "date":
            try:
                parsed = date.fromisoformat(str(value)[:10])
            except (TypeError, ValueError) as exc:
                raise ValueError(f"字段“{meta.get('name')}”日期格式无效") from exc
            return parsed if not meta.get("is_local") else parsed.isoformat()
        if field_type == "number":
            try:
                number = float(value)
            except (TypeError, ValueError) as exc:
                raise ValueError(f"字段“{meta.get('name')}”必须是数字") from exc
            return int(number) if number.is_integer() else number
        if field_type == "boolean":
            if isinstance(value, str):
                return value.strip().lower() in {"true", "1", "yes", "y", "是"}
            return bool(value)
        if field_type in {"multi_select", "multiselect"}:
            if not isinstance(value, list):
                raise ValueError(f"字段“{meta.get('name')}”必须是数组")
            return value
        if field_type == "select" and meta.get("options") and value not in meta["options"]:
            raise ValueError(f"字段“{meta.get('name')}”的选项无效")
        return value if isinstance(value, (str, int, float, bool, list, dict)) else str(value)

    @classmethod
    def submit(
        cls,
        db: Session,
        view: PatentView,
        data: dict[str, Any],
        patent_id: Optional[int] = None,
        changed_by: Optional[str] = None,
        allow_update: bool = True,
    ) -> Patent:
        config, field_meta = cls.normalize_config(db, view)
        field_configs = {
            field["key"]: field
            for section in config["sections"]
            for field in section["fields"]
        }
        unknown = sorted(set(data) - set(field_configs))
        if unknown:
            raise ValueError(f"表单包含未配置字段：{', '.join(unknown)}")

        patent = None
        if patent_id is not None:
            if not allow_update:
                raise ValueError("公开表单只能新增专利")
            patent = db.query(Patent).filter(
                Patent.id == patent_id,
                Patent.database_id == view.database_id,
            ).first()
            if not patent:
                raise ValueError("待编辑专利不属于当前视图所在的库")

        values = cls._current_values(db, view, patent)
        submitted: dict[str, Any] = {}
        for key, field_config in field_configs.items():
            if key in data:
                submitted[key] = data[key]
            elif patent is None and "default" in field_config:
                submitted[key] = field_config["default"]
            elif patent is None and field_meta[key].get("default_value") is not None:
                submitted[key] = field_meta[key]["default_value"]
        values.update(submitted)

        missing = []
        for key, field_config in field_configs.items():
            if field_config.get("required") and cls._is_visible(field_config, values):
                if cls._is_empty(values.get(key)):
                    missing.append(field_meta[key].get("name") or key)
        if missing:
            raise ValueError(f"请填写必填字段：{'、'.join(missing)}")

        system_updates: dict[str, Any] = {}
        custom_updates: dict[str, Any] = {}
        local_updates: dict[str, Any] = {}
        for key, value in submitted.items():
            normalized = cls._coerce_value(field_meta[key], value)
            if key.startswith("view_local."):
                local_updates[key[len("view_local."):]] = normalized
            elif key in SYSTEM_FIELDS and key not in {"id", "created_at", "updated_at"}:
                system_updates[key] = normalized
            else:
                custom_updates[key] = normalized

        if patent is None:
            system_updates["database_id"] = view.database_id
            system_updates["title"] = str(system_updates.get("title") or "未命名专利")
            system_updates["custom_fields"] = custom_updates
            patent = PatentService.create_patent(db, PatentCreate(**system_updates))
        else:
            if custom_updates:
                merged_custom_fields = dict(patent.custom_fields or {})
                merged_custom_fields.update(custom_updates)
                system_updates["custom_fields"] = merged_custom_fields
            patent = PatentService.update_patent(
                db,
                patent,
                system_updates,
                source="form",
                changed_by=changed_by,
                source_view_id=view.id,
                source_view_name=view.name,
            )

        for field_key, value in local_updates.items():
            ViewService.set_local_field_value(db, view, patent.id, field_key, value, changed_by=changed_by)
        db.refresh(patent)
        return patent

    @staticmethod
    def create_share_link(db: Session, view: PatentView, expires_days: Optional[int] = None) -> FormShareLink:
        if expires_days is not None and not 1 <= expires_days <= 3650:
            raise ValueError("expires_days 必须在 1 到 3650 天之间")
        expires_at = _utc_now() + timedelta(days=expires_days) if expires_days else None
        link = FormShareLink(
            view_id=view.id,
            token=secrets.token_urlsafe(32),
            expires_at=expires_at,
        )
        db.add(link)
        db.commit()
        db.refresh(link)
        return link

    @staticmethod
    def get_active_share(db: Session, token: str) -> Optional[FormShareLink]:
        link = db.query(FormShareLink).filter(
            FormShareLink.token == token,
            FormShareLink.is_active == True,
        ).first()
        if not link or (link.expires_at and link.expires_at < _utc_now()):
            return None
        if not link.view or link.view.is_archived:
            return None
        return link

    @staticmethod
    def serialize_share(link: FormShareLink) -> dict[str, Any]:
        return {
            "id": link.id,
            "view_id": link.view_id,
            "token": link.token,
            "is_active": link.is_active,
            "expires_at": link.expires_at.isoformat() if link.expires_at else None,
            "created_at": link.created_at.isoformat() if link.created_at else None,
        }
