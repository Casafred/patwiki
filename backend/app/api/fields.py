from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Any, Literal
from datetime import date

from app.database import get_db
from app.models import CustomField, CustomFieldType, Patent, PatentHistory
from app.services.field_registry import get_all_fields_meta, RELATION_FIELD_KEYS, SYSTEM_FIELD_KEYS, get_system_field_meta
from app.services.patent_service import PatentService, _is_value_changed, _stringify_value
from app.services.formula_service import FormulaService
from app.core.exceptions import BadRequestException, NotFoundException

router = APIRouter(tags=["fields"])


class FieldPolicyRequest(BaseModel):
    value_source: Literal["system", "manual"]
    value_stability: Literal["fixed", "variable"]
    merge_policy: Literal["version_latest", "keep_existing", "fill_empty", "quarantine"]
    validation_rules: dict[str, Any] = {}


def require_field(db, key):
    field = next((field for field in get_all_fields_meta(db) if field["key"] == key), None)
    if not field:
        raise NotFoundException("字段不存在")
    return field


@router.put("/fields/{field_key}/policy")
def set_field_policy(field_key: str, req: FieldPolicyRequest, db: Session = Depends(get_db)):
    from app.models import FieldDefinition
    from app.services.field_policy_service import IDENTITY_FIELDS
    field = require_field(db, field_key)
    if field_key in IDENTITY_FIELDS and req.merge_policy == "version_latest":
        raise BadRequestException("身份字段需要保留或隔离冲突，不能自动采用不同号码")
    rules = req.validation_rules
    if set(rules) - {"required", "max_length", "minimum", "maximum"}:
        raise BadRequestException("不支持的校验规则")
    if "required" in rules and not isinstance(rules["required"], bool):
        raise BadRequestException("required 必须为布尔值")
    if "max_length" in rules and (not isinstance(rules["max_length"], int) or rules["max_length"] < 1):
        raise BadRequestException("最大长度必须为正整数")
    for bound in ("minimum", "maximum"):
        if bound in rules and not isinstance(rules[bound], (int, float)):
            raise BadRequestException("数值范围必须为数字")
    if rules.get("minimum", float("-inf")) > rules.get("maximum", float("inf")):
        raise BadRequestException("最小值不能大于最大值")
    row = db.query(FieldDefinition).filter_by(canonical_key=f"runtime:{field_key}").first()
    if not row:
        row = FieldDefinition(canonical_key=f"runtime:{field_key}", display_name=field["name"],
                              storage_kind="runtime_policy", storage_locator=field_key)
        db.add(row)
    row.source_type, row.volatility = req.value_source, req.value_stability
    row.update_policy, row.validation_schema = req.merge_policy, rules
    db.commit()
    return require_field(db, field_key)


@router.get("/patents/{patent_id}/field/{field_key}/versions")
def field_versions(patent_id: int, field_key: str, db: Session = Depends(get_db)):
    from app.models import FieldObservation, ImportBatch, ImportFieldGovernanceAudit
    from app.services.patent_service import _stringify_value
    patent = db.get(Patent, patent_id)
    if not patent or patent.deleted_at:
        raise NotFoundException("Patent not found")
    field = require_field(db, field_key)
    history_key = field_key if field_key in SYSTEM_FIELD_KEYS else f"custom_fields.{field_key}"
    history = db.query(PatentHistory).filter_by(patent_id=patent_id, field_key=history_key).order_by(PatentHistory.id.desc()).all()
    candidates = db.query(FieldObservation, ImportBatch).join(ImportBatch, ImportBatch.id == FieldObservation.import_batch_id).filter(
        FieldObservation.patent_id == patent_id, FieldObservation.canonical_field_key == field_key,
    ).order_by(FieldObservation.id.desc()).all()
    current = getattr(patent, field_key, None) if field_key in SYSTEM_FIELD_KEYS else (patent.custom_fields or {}).get(field_key)
    audits = db.query(ImportFieldGovernanceAudit).filter(
        ImportFieldGovernanceAudit.patent_id == patent_id,
        ImportFieldGovernanceAudit.field_key.in_([field_key, history_key]),
        ImportFieldGovernanceAudit.source_kind != "file_import",
    ).order_by(ImportFieldGovernanceAudit.id.desc()).all()
    return {"field": field, "current_value": _stringify_value(current), "versions": [
        {"id": h.id, "old_value": h.old_value, "value": h.new_value, "source": h.source,
         "import_batch_id": h.import_batch_id, "source_label": h.source_table_title or h.source_view_name,
         "source_row": h.source_row, "created_at": h.created_at.isoformat() if h.created_at else None}
        for h in history], "imports": [
        {"id": item.id, "value": item.candidate_value or item.raw_value, "decision": item.final_decision or item.proposed_action,
         "batch_id": batch.id, "filename": batch.filename, "status": batch.status.value,
         "created_at": item.created_at.isoformat() if item.created_at else None}
        for item, batch in candidates] + [
        {"id": -audit.id, "value": _stringify_value(audit.incoming_value), "decision": audit.resolution,
         "batch_id": audit.import_batch_id, "filename": audit.source_label or audit.source_kind,
         "status": audit.resolution, "created_at": audit.created_at.isoformat() if audit.created_at else None}
        for audit in audits]}


class ConsolidateFieldRequest(BaseModel):
    target_field: str
    conflict_action: Literal["version_latest", "keep_existing", "merge"] = "keep_existing"
    apply: bool = False


class FieldVersionRequest(BaseModel):
    value: Any
    expected_value: str | None


@router.put("/patents/{patent_id}/field/{field_key}/versions")
def save_field_version(patent_id: int, field_key: str, req: FieldVersionRequest, db: Session = Depends(get_db)):
    from app.services.field_policy_service import validate_field_value
    from app.services.import_review_service import coerce_value
    patent = db.get(Patent, patent_id)
    if not patent or patent.deleted_at:
        raise NotFoundException("Patent not found")
    meta = require_field(db, field_key)
    if not meta.get("versioned") or not meta.get("editable"):
        raise BadRequestException("该字段不支持版本编辑")
    current = getattr(patent, field_key, None) if field_key in SYSTEM_FIELD_KEYS else (patent.custom_fields or {}).get(field_key)
    if _stringify_value(current) != req.expected_value:
        raise BadRequestException("该字段已被其他操作更新，请刷新后重新编辑")
    value = req.value
    if field_key in SYSTEM_FIELD_KEYS and value is not None and value != "":
        value = coerce_value(field_key, str(value))
    elif meta["field_type"] == "number" and value not in (None, ""):
        try:
            value = float(value)
        except (ValueError, TypeError) as exc:
            raise BadRequestException("请输入有效数字") from exc
    elif meta["field_type"] == "boolean" and isinstance(value, str):
        if value not in {"true", "false"}:
            raise BadRequestException("布尔值必须为 true 或 false")
        value = value == "true"
    elif meta["field_type"] in {"multiselect", "multi_select"} and isinstance(value, str):
        import json
        try:
            value = json.loads(value)
        except ValueError as exc:
            raise BadRequestException("多选值必须是 JSON 数组") from exc
        if not isinstance(value, list):
            raise BadRequestException("多选值必须是 JSON 数组")
    validate_field_value(meta, value)
    updates = {field_key: value} if field_key in SYSTEM_FIELD_KEYS else {"custom_fields": {field_key: value}}
    PatentService.update_patent(db, patent, updates, source="manual", changed_by="local-user")
    return field_versions(patent_id, field_key, db)


@router.post("/fields/{field_key}/consolidate")
def consolidate_field(field_key: str, req: ConsolidateFieldRequest, db: Session = Depends(get_db)):
    from app.models import FieldMapping, ViewLocalField
    from app.services.import_review_service import coerce_value, merge_import_value, MERGE_BLOCKED_FIELDS, MERGE_BLOCKED_FIELD_TYPES
    from app.services.field_policy_service import validate_field_value
    field = db.query(CustomField).filter_by(key=field_key).first()
    if not field or req.target_field == field_key:
        raise BadRequestException("请选择不同的自定义来源字段与目标字段")
    target = require_field(db, req.target_field)
    if not target.get("editable") or req.target_field in {"attachments", "patent_figures", "has_risk", "risk_level", "risk_description"}:
        raise BadRequestException("目标字段不支持归并")
    if req.conflict_action == "merge" and (req.target_field in MERGE_BLOCKED_FIELDS or target["field_type"] in MERGE_BLOCKED_FIELD_TYPES):
        raise BadRequestException("该字段类型不支持拼接合并")
    rows, changed, conflicts, issues = [], 0, 0, []
    for patent in db.query(Patent).filter(Patent.deleted_at.is_(None)).all():
        value = (patent.custom_fields or {}).get(field_key)
        if value is None or value == "":
            continue
        old = getattr(patent, req.target_field, None) if req.target_field in SYSTEM_FIELD_KEYS else (patent.custom_fields or {}).get(req.target_field)
        conflict = old is not None and old != "" and _is_value_changed(old, value)
        conflicts += int(conflict)
        try:
            converted = coerce_value(req.target_field, str(value)) if req.target_field in SYSTEM_FIELD_KEYS else value
            if conflict and req.conflict_action == "merge":
                converted = merge_import_value(old, converted)
            validate_field_value(target, converted)
        except Exception as exc:
            issues.append({"patent_id": patent.id, "reason": str(exc)})
            continue
        if conflict and req.conflict_action == "keep_existing":
            converted = old
        rows.append((patent, converted))
        changed += int(_is_value_changed(old, converted))
    result = {"records": len(rows), "changed": changed, "conflicts": conflicts, "issues": issues, "applied": False}
    if not req.apply:
        return result
    if issues:
        raise BadRequestException("归并校验失败，请修复后重试", detail=result)
    for patent, value in rows:
        updates = {req.target_field: value} if req.target_field in SYSTEM_FIELD_KEYS else {"custom_fields": {req.target_field: value}}
        PatentService.update_patent(db, patent, updates, source="field_consolidation", commit=False,
                                   run_post_update_hooks=False, source_table_title=f"{field.name} → {target['name']}")
    for template in db.query(FieldMapping).all():
        template.mapping_config = {key: req.target_field if value == field_key else value for key, value in (template.mapping_config or {}).items()}
    for alias in db.query(ViewLocalField).filter_by(promoted_field_key=field_key).all():
        alias.promoted_field_key = req.target_field
    field.is_active = False
    field.ai_config = {**(field.ai_config or {}), "consolidated_target": req.target_field}
    db.commit()
    result["applied"] = True
    return result


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

    from app.services.field_policy_service import validate_field_value
    meta = require_field(db, field_key)
    if not meta.get("editable"):
        raise BadRequestException("该字段只读")
    validate_field_value(meta, req.value)

    if field_key in RELATION_FIELD_KEYS:
        raise BadRequestException("同族/引用原始列是导入来源投影，请在关系面板维护结构化关系")

    history_entry = None
    if field_key in SYSTEM_FIELD_KEYS:
        if field_key in ("id", "created_at", "updated_at"):
            raise BadRequestException(f"Field '{field_key}' is read-only")
        if field_key in {"has_risk", "risk_level", "risk_description"}:
            raise BadRequestException("风险兼容投影不可直接编辑，请通过风险案例追加结构化评估")
        value = req.value
        if field_key == "publication_number" and value:
            from app.services.patent_identity_service import normalize_publication_number
            value = normalize_publication_number(value)
            if not value:
                raise BadRequestException("公开号格式无法识别，应为国别字母+数字+文献类型代码（可含字母系列，如 USRE46827E1）")
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
    from app.services.patent_identity_service import ensure_patent_identifiers
    ensure_patent_identifiers(db, patent, source_system="manual")
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
