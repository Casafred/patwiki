"""Library-specific annotations and local edits over an immutable sender baseline."""
from app.models.collaboration_sync import SyncLibraryField

PRIVATE_FIELDS = frozenset({"notes", "scope_description", "category", "subcategory", "module", "technical_problem",
    "technical_effect", "technical_solution", "has_risk", "risk_level", "risk_description", "application_status", "custom_fields"})


def plan_library_fields(db, package, database, record, patent):
    if package.package_type == "department_publication":
        return [], []
    payload = record.payload_json or {}
    sources = (record.scope_json or {}).get("database_uids", [])
    fields = {key: value for key, value in payload.items() if key in PRIVATE_FIELDS and key != "custom_fields"}
    fields.update({f"custom_fields.{key}": value for key, value in (payload.get("custom_fields") or {}).items()
        if key != "attachments"})
    plans, conflicts = [], []
    incoming = {(source, key): remote for source in sources for key, remote in fields.items()}
    for item in (record.field_provenance or {}).get("library_values", []):
        if item.get("database_uid") in sources and (item.get("field_key") in PRIVATE_FIELDS or str(item.get("field_key", "")).startswith("custom_fields.")):
            incoming[(item["database_uid"], item["field_key"])] = item.get("value")
    for (source, key), remote in incoming.items():
            state = db.query(SyncLibraryField).filter_by(database_id=database.id, patent_id=patent.id,
                source_database_uid=source, field_key=key).first() if patent else None
            conflict_key = f"library:{source}:{key}"
            plans.append({"state": state, "source": source, "field": key, "remote": remote, "conflict_key": conflict_key})
            if state and state.has_overlay and state.local_value != remote and state.baseline_value != remote:
                conflicts.append({"entity_uid": record.entity_uid, "field_key": conflict_key,
                    "base_value": state.baseline_value, "local_value": state.local_value, "remote_value": remote})
    return plans, conflicts


def apply_library_fields(db, package, database, record, patent, plans, decisions, details, user_id):
    for plan in plans:
        state = plan["state"]
        if state is None:
            state = SyncLibraryField(database_id=database.id, patent_id=patent.id,
                source_database_uid=plan["source"], field_key=plan["field"], package_uid=package.package_uid)
            db.add(state)
        choice = decisions.get((record.entity_uid, plan["conflict_key"]))
        if choice == "remote" or (state.has_overlay and state.local_value == plan["remote"]):
            state.has_overlay = False
        if choice == "manual":
            state.local_value = details[(record.entity_uid, plan["conflict_key"])].value
            state.has_overlay = True
            state.editor_user_id = user_id
        state.baseline_value = plan["remote"]
        state.package_uid = package.package_uid


def library_fields(db, patent_id):
    from app.models import User, PatentDatabase
    rows = db.query(SyncLibraryField).filter_by(patent_id=patent_id).all()
    result = []
    for row in rows:
        editor = db.get(User, row.editor_user_id) if row.editor_user_id else None
        database = db.get(PatentDatabase, row.database_id)
        result.append({"id": row.id, "database_id": row.database_id, "database_name": database.name,
            "source_database_uid": row.source_database_uid, "field_key": row.field_key,
            "baseline_value": row.baseline_value, "local_value": row.local_value if row.has_overlay else row.baseline_value,
            "state": "self_edit" if row.has_overlay else "other_edit", "reason": row.reason,
            "editor": editor.display_name or editor.username if editor else None})
    return result
