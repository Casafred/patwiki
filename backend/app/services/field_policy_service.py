"""Runtime field policy shared by mapping, review and manual writes."""
from app.models import FieldDefinition

MANUAL_FIELDS = frozenset({"category", "subcategory", "technical_problem", "technical_solution", "technical_effect", "module", "application_status", "scope_description", "notes", "has_risk", "risk_level", "risk_description"})
VARIABLE_FIELDS = MANUAL_FIELDS | {"legal_status", "legal_status_date", "legal_status_details", "claims", "assignee"}
IDENTITY_FIELDS = frozenset({"application_number", "publication_number", "grant_number", "country"})


def enrich_field_policies(db, fields):
    overrides = {row.storage_locator: row for row in db.query(FieldDefinition).filter(
        FieldDefinition.storage_kind == "runtime_policy",
    ).all()} if db is not None else {}
    result = []
    for field in fields:
        key = field["key"]
        manual = key in MANUAL_FIELDS or not field.get("is_system")
        versioned = field.get("field_type") not in {"attachment", "formula", "lookup", "rollup", "link"} and key not in {"family_members", "cited_patents", "citing_patents", "id", "created_at", "updated_at"}
        policy = {
            "value_source": "manual" if manual else "system",
            "value_stability": "variable" if manual or key in VARIABLE_FIELDS else "fixed",
            "merge_policy": "keep_existing" if key in IDENTITY_FIELDS else "version_latest",
            "validation_rules": {}, "versioned": versioned,
        }
        row = overrides.get(key)
        if row:
            policy.update(value_source=row.source_type, value_stability=row.volatility,
                          merge_policy=row.update_policy, validation_rules=row.validation_schema or {})
        result.append({**field, **policy})
    return result


def validate_field_value(meta, value):
    from app.core.exceptions import BadRequestException
    rules = meta.get("validation_rules") or {}
    if (rules.get("required") or meta.get("key") == "title") and (value is None or value == ""):
        raise BadRequestException(f"{meta['name']}不能为空")
    if value is None or value == "":
        return
    if rules.get("max_length") and len(str(value)) > rules["max_length"]:
        raise BadRequestException(f"{meta['name']}超过最大长度 {rules['max_length']}")
    for bound in ("minimum", "maximum"):
        if rules.get(bound) is not None:
            try:
                number = float(value)
            except (TypeError, ValueError) as exc:
                raise BadRequestException(f"{meta['name']}必须为数字") from exc
            if (bound == "minimum" and number < rules[bound]) or (bound == "maximum" and number > rules[bound]):
                raise BadRequestException(f"{meta['name']}超出允许范围")
