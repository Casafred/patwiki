"""公式字段定义、依赖图和专利值重算服务。"""
from __future__ import annotations

import re
from datetime import date, datetime
from typing import Any, Iterable, Optional

from sqlalchemy.orm import Session

from app.models import CustomField, CustomFieldType, FormulaDependency, Patent
from app.services.field_registry import SYSTEM_FIELD_KEYS, get_all_fields_meta
from app.services.formula_engine import (
    FUNCTION_DEFINITIONS,
    SAFE_FUNCTIONS,
    FormulaEngine,
    FormulaError,
)


FIELD_KEY_PATTERN = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
RETURN_TYPES = {"text", "number", "date", "boolean"}


def _json_value(value: Any) -> Any:
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, dict):
        return {str(key): _json_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_value(item) for item in value]
    if hasattr(value, "value"):
        return value.value
    return value


class FormulaService:
    """公式字段的唯一业务入口。"""

    @staticmethod
    def _formula_fields(db: Session) -> list[CustomField]:
        return db.query(CustomField).filter(
            CustomField.field_type == CustomFieldType.FORMULA,
            CustomField.is_active == True,
        ).order_by(CustomField.sort_order, CustomField.name).all()

    @staticmethod
    def _all_field_keys(db: Session) -> set[str]:
        system_columns = set(Patent.__table__.columns.keys()) - {"custom_fields", "ai_fields", "search_vector"}
        custom_keys = {field.key for field in db.query(CustomField).all()}
        return system_columns | SYSTEM_FIELD_KEYS | custom_keys

    @staticmethod
    def _validate_key(key: str) -> str:
        normalized = str(key or "").strip()
        if not FIELD_KEY_PATTERN.fullmatch(normalized):
            raise FormulaError("公式字段 key 只能包含英文字母、数字和下划线，且不能以数字开头")
        if normalized.upper() in SAFE_FUNCTIONS:
            raise FormulaError(f"公式字段 key 不能使用函数名：{normalized}")
        return normalized

    @classmethod
    def validate_expression(
        cls,
        db: Session,
        expression: str,
        formula_key: Optional[str] = None,
    ) -> tuple[Any, set[str]]:
        tree = FormulaEngine.parse(expression)
        dependencies = FormulaEngine.extract_dependencies(tree)
        unknown = sorted(dependencies - cls._all_field_keys(db))
        if unknown:
            raise FormulaError(f"公式引用了不存在的字段：{', '.join(unknown)}")
        if formula_key and formula_key in dependencies:
            raise FormulaError(f"公式字段不能引用自身：{formula_key}")
        return tree, dependencies

    @classmethod
    def _dependency_graph(cls, db: Session, candidate_key: Optional[str] = None, candidate_dependencies: Optional[set[str]] = None) -> dict[str, set[str]]:
        formula_fields = cls._formula_fields(db)
        formula_keys = {field.key for field in formula_fields}
        graph: dict[str, set[str]] = {}
        for field in formula_fields:
            rows = db.query(FormulaDependency.depends_on_field_key).filter(
                FormulaDependency.formula_field_key == field.key,
            ).all()
            dependencies = {row[0] for row in rows}
            if not dependencies:
                expression = (field.formula_config or {}).get("expression", "")
                try:
                    tree = FormulaEngine.parse(expression)
                    dependencies = FormulaEngine.extract_dependencies(tree)
                except FormulaError:
                    dependencies = set()
            graph[field.key] = dependencies & formula_keys
        if candidate_key is not None:
            graph[candidate_key] = set(candidate_dependencies or set()) & (formula_keys | {candidate_key})
        return graph

    @classmethod
    def _ensure_acyclic(
        cls,
        db: Session,
        candidate_key: Optional[str] = None,
        candidate_dependencies: Optional[set[str]] = None,
    ) -> None:
        graph = cls._dependency_graph(db, candidate_key, candidate_dependencies)
        visiting: list[str] = []
        visited: set[str] = set()

        def visit(node: str) -> None:
            if node in visiting:
                cycle = visiting[visiting.index(node):] + [node]
                raise FormulaError(f"公式字段存在循环依赖：{' -> '.join(cycle)}")
            if node in visited:
                return
            visiting.append(node)
            for dependency in graph.get(node, set()):
                visit(dependency)
            visiting.pop()
            visited.add(node)

        for key in graph:
            visit(key)

    @classmethod
    def _formula_order(cls, db: Session) -> list[CustomField]:
        formula_fields = cls._formula_fields(db)
        by_key = {field.key: field for field in formula_fields}
        graph = cls._dependency_graph(db)
        cls._ensure_acyclic(db)
        order: list[str] = []
        visited: set[str] = set()

        def visit(key: str) -> None:
            if key in visited:
                return
            visited.add(key)
            for dependency in graph.get(key, set()):
                visit(dependency)
            order.append(key)

        for field in formula_fields:
            visit(field.key)
        return [by_key[key] for key in order]

    @staticmethod
    def _dependencies_for(db: Session, field_key: str) -> set[str]:
        return {
            row[0]
            for row in db.query(FormulaDependency.depends_on_field_key).filter(
                FormulaDependency.formula_field_key == field_key,
            ).all()
        }

    @classmethod
    def _set_dependencies(cls, db: Session, field_key: str, dependencies: Iterable[str]) -> None:
        db.query(FormulaDependency).filter(
            FormulaDependency.formula_field_key == field_key,
        ).delete(synchronize_session=False)
        all_custom = {field.key for field in db.query(CustomField).all()}
        for dependency in sorted(set(dependencies)):
            depends_on_type = "custom" if dependency in all_custom else "system"
            if db.query(CustomField).filter(
                CustomField.key == dependency,
                CustomField.field_type == CustomFieldType.FORMULA,
            ).first():
                depends_on_type = "formula"
            db.add(FormulaDependency(
                formula_field_key=field_key,
                depends_on_field_key=dependency,
                depends_on_type=depends_on_type,
            ))

    @classmethod
    def create_formula_field(
        cls,
        db: Session,
        *,
        key: str,
        name: str,
        expression: str,
        return_type: str = "text",
        group_name: str = "公式",
        description: Optional[str] = None,
        sort_order: int = 0,
        is_active: bool = True,
    ) -> CustomField:
        key = cls._validate_key(key)
        return_type = str(return_type or "text").lower()
        if return_type not in RETURN_TYPES:
            raise FormulaError(f"不支持的公式返回类型：{return_type}")
        if db.query(CustomField).filter(CustomField.key == key).first():
            raise FormulaError(f"字段 key 已存在：{key}")
        _, dependencies = cls.validate_expression(db, expression, formula_key=key)
        cls._ensure_acyclic(db, candidate_key=key, candidate_dependencies=dependencies)
        field = CustomField(
            key=key,
            name=name.strip(),
            field_type=CustomFieldType.FORMULA,
            group_name=group_name or "公式",
            description=description,
            is_active=is_active,
            sort_order=sort_order,
            formula_config={"expression": expression.strip(), "return_type": return_type},
        )
        db.add(field)
        db.flush()
        cls._set_dependencies(db, key, dependencies)
        db.commit()
        db.refresh(field)
        if field.is_active:
            cls.recalculate_all(db, formula_key=key)
        return field

    @classmethod
    def update_formula_field(cls, db: Session, field: CustomField, updates: dict[str, Any]) -> CustomField:
        converting_to_formula = field.field_type != CustomFieldType.FORMULA
        config = dict(field.formula_config or {})
        incoming_config = updates.pop("formula_config", None)
        if isinstance(incoming_config, dict):
            config.update(incoming_config)
        if "expression" in updates:
            config["expression"] = updates.pop("expression")
        expression = str(config.get("expression") or "")
        return_type = str(config.get("return_type") or "text").lower()
        if return_type not in RETURN_TYPES:
            raise FormulaError(f"不支持的公式返回类型：{return_type}")
        _, dependencies = cls.validate_expression(db, expression, formula_key=field.key)
        cls._ensure_acyclic(db, candidate_key=field.key, candidate_dependencies=dependencies)
        for key in ("name", "group_name", "description", "sort_order", "is_active"):
            if key in updates:
                setattr(field, key, updates[key])
        if converting_to_formula:
            field.field_type = CustomFieldType.FORMULA
            field.options = None
            field.default_value = None
            field.ai_config = None
            field.link_config = None
            field.lookup_config = None
            field.rollup_config = None
        field.formula_config = {"expression": expression.strip(), "return_type": return_type}
        cls._set_dependencies(db, field.key, dependencies)
        db.add(field)
        db.commit()
        db.refresh(field)
        if field.is_active:
            cls.recalculate_all(db, formula_key=field.key)
        return field

    @classmethod
    def remove_formula_dependencies(cls, db: Session, field_key: str) -> None:
        db.query(FormulaDependency).filter(
            FormulaDependency.formula_field_key == field_key,
        ).delete(synchronize_session=False)

    @classmethod
    def delete_formula_field(cls, db: Session, field: CustomField) -> None:
        cls.remove_formula_dependencies(db, field.key)
        db.delete(field)
        db.commit()

    @staticmethod
    def _get_field_values(patent: Patent) -> dict[str, Any]:
        values: dict[str, Any] = {}
        for key in Patent.__table__.columns.keys():
            if key in {"custom_fields", "ai_fields", "search_vector"}:
                continue
            values[key] = getattr(patent, key, None)
        for key, value in (patent.custom_fields or {}).items():
            values[key] = value
        return values

    @staticmethod
    def _coerce_result(value: Any, return_type: str) -> Any:
        if value is None:
            return None
        if return_type == "text":
            return _json_value(value) if isinstance(value, (date, datetime)) else str(value)
        if return_type == "number":
            try:
                number = float(value)
            except (TypeError, ValueError) as exc:
                raise FormulaError(f"结果不是数字：{value}") from exc
            return int(number) if number.is_integer() else number
        if return_type == "boolean":
            return bool(value)
        if return_type == "date":
            if isinstance(value, datetime):
                return value.date().isoformat()
            if isinstance(value, date):
                return value.isoformat()
            return str(value)
        return _json_value(value)

    @classmethod
    def _recalculate_values(
        cls,
        db: Session,
        patent: Patent,
        formulas: list[CustomField],
    ) -> dict[str, str]:
        values = cls._get_field_values(patent)
        current = dict(patent.custom_fields or {})
        errors: dict[str, str] = {}
        for field in formulas:
            config = field.formula_config or {}
            try:
                tree = FormulaEngine.parse(str(config.get("expression") or ""))
                result = FormulaEngine.evaluate(tree, values)
                result = cls._coerce_result(result, str(config.get("return_type") or "text"))
                current[field.key] = result
                values[field.key] = result
            except FormulaError as exc:
                current[field.key] = None
                values[field.key] = None
                errors[field.key] = str(exc)
        patent.custom_fields = current
        db.add(patent)
        return errors

    @classmethod
    def recalculate_patent(
        cls,
        db: Session,
        patent: Patent,
        formula_keys: Optional[set[str]] = None,
    ) -> dict[str, Any]:
        ordered = cls._formula_order(db)
        if formula_keys is not None:
            ordered = [field for field in ordered if field.key in formula_keys]
        errors = cls._recalculate_values(db, patent, ordered)
        db.commit()
        db.refresh(patent)
        return {"updated": len(ordered), "errors": errors}

    @classmethod
    def recalculate_all(
        cls,
        db: Session,
        formula_key: Optional[str] = None,
        patent_ids: Optional[list[int]] = None,
        database_id: Optional[int] = None,
    ) -> dict[str, Any]:
        ordered = cls._formula_order(db)
        if formula_key:
            affected = cls._affected_formula_keys(db, [formula_key])
            if not affected:
                raise FormulaError(f"公式字段不存在：{formula_key}")
            ordered = [field for field in ordered if field.key in affected]
        query = db.query(Patent)
        if patent_ids:
            query = query.filter(Patent.id.in_(patent_ids))
        if database_id is not None:
            query = query.filter(Patent.database_id == database_id)
        patents = query.all()
        errors: dict[str, int] = {}
        for patent in patents:
            row_errors = cls._recalculate_values(db, patent, ordered)
            for key in row_errors:
                errors[key] = errors.get(key, 0) + 1
        db.commit()
        return {"patent_count": len(patents), "formula_count": len(ordered), "errors": errors}

    @classmethod
    def on_field_changed(
        cls,
        db: Session,
        patent: Patent,
        changed_fields: Iterable[str],
    ) -> dict[str, Any]:
        changed = {field.replace("custom_fields.", "", 1) for field in changed_fields}
        affected = cls._affected_formula_keys(db, changed)
        if not affected:
            return {"updated": 0, "errors": {}}
        return cls.recalculate_patent(db, patent, affected)

    @classmethod
    def _affected_formula_keys(
        cls,
        db: Session,
        changed_fields: Iterable[str],
    ) -> set[str]:
        """Return changed formula fields and all active formulas depending on them."""
        formula_keys = {field.key for field in cls._formula_fields(db)}
        reverse: dict[str, set[str]] = {}
        for row in db.query(FormulaDependency).all():
            reverse.setdefault(row.depends_on_field_key, set()).add(row.formula_field_key)
        changed = set(changed_fields)
        affected = changed & formula_keys
        pending = list(changed)
        while pending:
            field = pending.pop()
            for dependent in reverse.get(field, set()):
                if dependent not in affected:
                    affected.add(dependent)
                    pending.append(dependent)
        return affected

    @classmethod
    def serialize_field(cls, db: Session, field: CustomField) -> dict[str, Any]:
        config = field.formula_config or {}
        return {
            "id": field.id,
            "key": field.key,
            "name": field.name,
            "field_type": "formula",
            "group_name": field.group_name or "公式",
            "description": field.description,
            "formula_config": config,
            "dependencies": sorted(cls._dependencies_for(db, field.key)),
            "is_active": field.is_active,
            "sort_order": field.sort_order,
            "created_at": field.created_at.isoformat() if field.created_at else None,
            "updated_at": field.updated_at.isoformat() if field.updated_at else None,
        }

    @staticmethod
    def functions() -> list[dict[str, str]]:
        return FUNCTION_DEFINITIONS
