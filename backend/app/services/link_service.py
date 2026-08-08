"""Link / Lookup / Rollup 关联字段服务。

关联字段的目标表使用白名单映射，避免把用户配置直接拼接为 SQL 表名。
当前支持专利、项目、产品、人员、部门、产品线和标签作为目标记录。
"""
from datetime import date, datetime
from typing import Any

from sqlalchemy.orm import Session

from app.models import (
    CrossTableLink,
    CustomField,
    CustomFieldType,
    Department,
    Person,
    Patent,
    Product,
    ProductLine,
    Project,
    Tag,
)


SOURCE_TABLE_MODELS = {"patents": Patent}
TARGET_TABLE_MODELS = {
    "patents": Patent,
    "projects": Project,
    "products": Product,
    "people": Person,
    "departments": Department,
    "product-lines": ProductLine,
    "tags": Tag,
}
TABLE_ALIASES = {
    "patent": "patents",
    "project": "projects",
    "product": "products",
    "person": "people",
    "department": "departments",
    "product_line": "product-lines",
    "product-line": "product-lines",
    "tag": "tags",
}


def normalize_table_name(table: str) -> str:
    normalized = (table or "").strip().lower()
    return TABLE_ALIASES.get(normalized, normalized)


def _get_model(table: str, source: bool = False):
    normalized = normalize_table_name(table)
    models = SOURCE_TABLE_MODELS if source else TARGET_TABLE_MODELS
    return normalized, models.get(normalized)


def _get_field(db: Session, field_key: str, field_type: CustomFieldType | None = None) -> CustomField:
    field = db.query(CustomField).filter(CustomField.key == field_key).first()
    if not field:
        raise ValueError(f"关联字段不存在：{field_key}")
    actual_type = field.field_type.value if hasattr(field.field_type, "value") else str(field.field_type)
    if field_type and actual_type != field_type.value:
        raise ValueError(f"字段类型不匹配：{field_key}")
    return field


def _get_record(db: Session, table: str, record_id: int, source: bool = False):
    normalized, model = _get_model(table, source=source)
    if model is None:
        raise ValueError(f"不支持的表：{table}")
    record = db.query(model).filter(model.id == record_id).first()
    if not record:
        raise ValueError(f"记录不存在：{normalized}/{record_id}")
    return normalized, record


def _serialize_value(value: Any) -> Any:
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    return value


def get_record_value(record: Any, field_key: str) -> Any:
    if field_key.startswith("custom_fields."):
        field_key = field_key.split(".", 1)[1]
    if hasattr(record, field_key):
        return _serialize_value(getattr(record, field_key))
    custom_fields = getattr(record, "custom_fields", None) or {}
    return _serialize_value(custom_fields.get(field_key))


def get_record_label(record: Any, display_field: str = "name") -> str:
    value = get_record_value(record, display_field)
    if value in (None, ""):
        for fallback in ("name", "title", "application_number", "code"):
            value = get_record_value(record, fallback)
            if value not in (None, ""):
                break
    return str(value if value not in (None, "") else f"记录 #{record.id}")


def _target_config(field: CustomField) -> dict[str, Any]:
    config = field.link_config or {}
    target_table = normalize_table_name(str(config.get("target_table") or "projects"))
    if target_table not in TARGET_TABLE_MODELS:
        raise ValueError(f"不支持的目标表：{target_table}")
    return {**config, "target_table": target_table}


def create_link(
    db: Session,
    field_key: str,
    source_record_id: int,
    target_record_id: int,
    source_table: str = "patents",
    created_by: str | None = None,
) -> CrossTableLink:
    field = _get_field(db, field_key, CustomFieldType.LINK)
    source_name, _ = _get_record(db, source_table, source_record_id, source=True)
    config = _target_config(field)
    target_name, _ = _get_record(db, config["target_table"], target_record_id)

    existing = db.query(CrossTableLink).filter(
        CrossTableLink.link_field_key == field_key,
        CrossTableLink.source_table == source_name,
        CrossTableLink.source_record_id == source_record_id,
        CrossTableLink.target_table == target_name,
        CrossTableLink.target_record_id == target_record_id,
    ).first()
    if existing:
        return existing

    if not bool(config.get("allow_multiple", True)):
        db.query(CrossTableLink).filter(
            CrossTableLink.link_field_key == field_key,
            CrossTableLink.source_table == source_name,
            CrossTableLink.source_record_id == source_record_id,
        ).delete(synchronize_session=False)

    link = CrossTableLink(
        link_field_key=field_key,
        source_table=source_name,
        source_record_id=source_record_id,
        target_table=target_name,
        target_record_id=target_record_id,
        created_by=created_by,
    )
    db.add(link)
    db.commit()
    db.refresh(link)
    return link


def remove_link(
    db: Session,
    field_key: str,
    source_record_id: int,
    target_record_id: int,
    source_table: str = "patents",
) -> bool:
    _get_field(db, field_key, CustomFieldType.LINK)
    source_name = normalize_table_name(source_table)
    link = db.query(CrossTableLink).filter(
        CrossTableLink.link_field_key == field_key,
        CrossTableLink.source_table == source_name,
        CrossTableLink.source_record_id == source_record_id,
        CrossTableLink.target_record_id == target_record_id,
    ).first()
    if not link:
        return False
    db.delete(link)
    db.commit()
    return True


def list_links_batch(
    db: Session,
    field_key: str,
    source_record_ids: list[int],
    source_table: str = "patents",
) -> dict[int, list[dict[str, Any]]]:
    """一次读取一组源记录的 Link，供表格页避免逐单元格请求。"""
    field = _get_field(db, field_key, CustomFieldType.LINK)
    config = _target_config(field)
    source_name = normalize_table_name(source_table)
    record_ids = sorted({int(record_id) for record_id in source_record_ids})
    result: dict[int, list[dict[str, Any]]] = {record_id: [] for record_id in record_ids}
    if not record_ids:
        return result

    links = db.query(CrossTableLink).filter(
        CrossTableLink.link_field_key == field_key,
        CrossTableLink.source_table == source_name,
        CrossTableLink.source_record_id.in_(record_ids),
    ).order_by(CrossTableLink.id).all()
    if not links:
        return result

    model = TARGET_TABLE_MODELS[config["target_table"]]
    targets = db.query(model).filter(
        model.id.in_({link.target_record_id for link in links})
    ).all()
    target_by_id = {target.id: target for target in targets}
    display_field = str(config.get("display_field") or "name")
    for link in links:
        target = target_by_id.get(link.target_record_id)
        if not target:
            continue
        result.setdefault(link.source_record_id, []).append({
            "id": link.id,
            "field_key": link.link_field_key,
            "source_table": link.source_table,
            "source_record_id": link.source_record_id,
            "target_table": link.target_table,
            "target_record_id": link.target_record_id,
            "label": get_record_label(target, display_field),
            "created_at": link.created_at,
        })
    return result


def list_links(db: Session, field_key: str, source_record_id: int, source_table: str = "patents") -> list[dict[str, Any]]:
    return list_links_batch(db, field_key, [source_record_id], source_table).get(source_record_id, [])


def search_targets(db: Session, field_key: str, search: str = "", limit: int = 50) -> list[dict[str, Any]]:
    field = _get_field(db, field_key, CustomFieldType.LINK)
    config = _target_config(field)
    model = TARGET_TABLE_MODELS[config["target_table"]]
    display_field = str(config.get("display_field") or "name")
    records = db.query(model).order_by(model.id.desc()).limit(min(max(limit, 1), 100)).all()
    term = search.strip().lower()
    result = []
    for record in records:
        label = get_record_label(record, display_field)
        if term and term not in label.lower() and term not in str(record.id):
            continue
        result.append({"id": record.id, "label": label, "target_table": config["target_table"]})
    return result[: min(max(limit, 1), 100)]


def resolve_lookup(db: Session, field_key: str, record_id: int, source_table: str = "patents") -> dict[str, Any]:
    field = _get_field(db, field_key, CustomFieldType.LOOKUP)
    config = field.lookup_config or {}
    link_field_key = str(config.get("link_field_key") or "")
    source_field = str(config.get("source_field") or "name")
    if not link_field_key:
        raise ValueError(f"Lookup 字段未配置关联字段：{field_key}")
    links = list_links(db, link_field_key, record_id, source_table)
    values = []
    model = TARGET_TABLE_MODELS[_target_config(_get_field(db, link_field_key, CustomFieldType.LINK))["target_table"]]
    for link in links:
        target = db.query(model).filter(model.id == link["target_record_id"]).first()
        if target:
            values.append(get_record_value(target, source_field))
    result = values if bool(config.get("allow_multiple", True)) else (values[0] if values else None)
    return {"field_key": field_key, "record_id": record_id, "value": result}


def resolve_rollup(db: Session, field_key: str, record_id: int, source_table: str = "patents") -> dict[str, Any]:
    field = _get_field(db, field_key, CustomFieldType.ROLLUP)
    config = field.rollup_config or {}
    link_field_key = str(config.get("link_field_key") or "")
    aggregation = str(config.get("aggregation") or "COUNT").upper()
    source_field = str(config.get("source_field") or "")
    if not link_field_key:
        raise ValueError(f"Rollup 字段未配置关联字段：{field_key}")
    if aggregation not in {"COUNT", "SUM", "AVG", "MIN", "MAX"}:
        raise ValueError(f"不支持的聚合函数：{aggregation}")
    links = list_links(db, link_field_key, record_id, source_table)
    if aggregation == "COUNT":
        value: Any = len(links)
    else:
        link_field = _get_field(db, link_field_key, CustomFieldType.LINK)
        model = TARGET_TABLE_MODELS[_target_config(link_field)["target_table"]]
        values: list[float] = []
        for link in links:
            target = db.query(model).filter(model.id == link["target_record_id"]).first()
            raw = get_record_value(target, source_field) if target else None
            try:
                if raw not in (None, ""):
                    values.append(float(raw))
            except (TypeError, ValueError):
                continue
        if aggregation == "SUM":
            value = sum(values)
        elif aggregation == "AVG":
            value = sum(values) / len(values) if values else 0
        elif aggregation == "MIN":
            value = min(values) if values else None
        else:
            value = max(values) if values else None
        if isinstance(value, float) and value.is_integer():
            value = int(value)
    return {"field_key": field_key, "record_id": record_id, "aggregation": aggregation, "value": value}


def resolve_relation_batch(
    db: Session,
    field_key: str,
    record_ids: list[int],
    source_table: str = "patents",
) -> list[dict[str, Any]]:
    """批量解析 Link、Lookup 或 Rollup 字段的当前值。"""
    field = _get_field(db, field_key)
    actual_type = field.field_type.value if hasattr(field.field_type, "value") else str(field.field_type)
    normalized_ids = sorted({int(record_id) for record_id in record_ids})
    if actual_type == CustomFieldType.LINK.value:
        links_by_record = list_links_batch(db, field_key, normalized_ids, source_table)
        return [{"record_id": record_id, "links": links_by_record.get(record_id, [])} for record_id in normalized_ids]

    config = field.lookup_config if actual_type == CustomFieldType.LOOKUP.value else field.rollup_config
    config = config or {}
    link_field_key = str(config.get("link_field_key") or "")
    if not link_field_key:
        raise ValueError(f"关联字段未配置 Link 字段：{field_key}")
    link_field = _get_field(db, link_field_key, CustomFieldType.LINK)
    links_by_record = list_links_batch(db, link_field_key, normalized_ids, source_table)
    target_config = _target_config(link_field)
    model = TARGET_TABLE_MODELS[target_config["target_table"]]
    target_ids = {
        link["target_record_id"]
        for links in links_by_record.values()
        for link in links
    }
    targets = db.query(model).filter(model.id.in_(target_ids)).all() if target_ids else []
    target_by_id = {target.id: target for target in targets}

    if actual_type == CustomFieldType.LOOKUP.value:
        source_field = str(config.get("source_field") or "name")
        allow_multiple = bool(config.get("allow_multiple", True))
        return [
            {
                "record_id": record_id,
                "value": (
                    [
                        get_record_value(target_by_id[link["target_record_id"]], source_field)
                        for link in links_by_record.get(record_id, [])
                        if link["target_record_id"] in target_by_id
                    ]
                    if allow_multiple
                    else next(
                        (
                            get_record_value(target_by_id[link["target_record_id"]], source_field)
                            for link in links_by_record.get(record_id, [])
                            if link["target_record_id"] in target_by_id
                        ),
                        None,
                    )
                ),
            }
            for record_id in normalized_ids
        ]

    aggregation = str(config.get("aggregation") or "COUNT").upper()
    if aggregation not in {"COUNT", "SUM", "AVG", "MIN", "MAX"}:
        raise ValueError(f"不支持的聚合函数：{aggregation}")
    source_field = str(config.get("source_field") or "")
    result: list[dict[str, Any]] = []
    for record_id in normalized_ids:
        links = links_by_record.get(record_id, [])
        if aggregation == "COUNT":
            value: Any = len(links)
        else:
            values: list[float] = []
            for link in links:
                target = target_by_id.get(link["target_record_id"])
                raw = get_record_value(target, source_field) if target else None
                try:
                    if raw not in (None, ""):
                        values.append(float(raw))
                except (TypeError, ValueError):
                    continue
            if aggregation == "SUM":
                value = sum(values)
            elif aggregation == "AVG":
                value = sum(values) / len(values) if values else 0
            elif aggregation == "MIN":
                value = min(values) if values else None
            else:
                value = max(values) if values else None
            if isinstance(value, float) and value.is_integer():
                value = int(value)
        result.append({"record_id": record_id, "aggregation": aggregation, "value": value})
    return result
