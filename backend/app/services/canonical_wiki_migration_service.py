"""Idempotent upgrade of legacy library values and family projections."""
from app.models import FieldDefinition, PatentDatabase, ViewLocalField, PatentView
from app.config import settings


def upgrade_canonical_wiki(db):
    marker_key = "migration:canonical-wiki-2026-10-08.1"
    if db.query(FieldDefinition).filter_by(canonical_key=marker_key).first():
        return
    from app.services.migration_service import _backup_database
    from app.services.view_service import ViewService
    from app.services.relation_service import rebuild_database_families
    backup = _backup_database(db.get_bind(), settings.BACKUPS_DIR, "canonical-wiki-2026-10-08")
    from app.models import Patent, CustomField, CustomFieldType
    from app.models.collaboration_sync import SyncLibraryField
    from app.services.patent_service import PatentService
    from app.services.import_governance_service import record_import_field_change
    from app.services.collaboration_library_field_service import PRIVATE_FIELDS
    seen = set()
    original_times = {}
    for item in db.query(SyncLibraryField).order_by(SyncLibraryField.updated_at.desc(), SyncLibraryField.id.desc()).all():
        patent = db.get(Patent, item.patent_id)
        if not patent or patent.deleted_at:
            continue
        key = item.field_key
        original_times.setdefault(patent.id, patent.updated_at)
        is_custom = key.startswith("custom_fields.")
        short_key = key.removeprefix("custom_fields.")
        if not is_custom and key not in PRIVATE_FIELDS:
            continue
        incoming = item.local_value if item.has_overlay else item.baseline_value
        current = (patent.custom_fields or {}).get(short_key) if is_custom else getattr(patent, key, None)
        identity = (patent.id, key)
        newest = identity not in seen
        seen.add(identity)
        usable = short_key not in {"attachments", "patent_figures", "has_risk", "risk_level", "risk_description"}
        adopt = usable and newest and incoming not in (None, "") and (current in (None, "") or (item.updated_at and original_times[patent.id] and item.updated_at > original_times[patent.id]))
        if adopt:
            if is_custom and not db.query(CustomField).filter_by(key=short_key).first():
                db.add(CustomField(key=short_key, name=short_key, field_type=CustomFieldType.TEXT, group_name="人工扩展"))
                db.flush()
            updates = {"custom_fields": {short_key: incoming}} if is_custom else {key: incoming}
            PatentService.update_patent(db, patent, updates, source="library_migration", commit=False,
                run_post_update_hooks=False, source_table_title=f"历史库字段 {item.database_id}")
        record_import_field_change(db, patent=patent, field_key=key, old_value=current,
            incoming_value=incoming, final_value=incoming if adopt else current, database_id=item.database_id,
            source_kind="legacy_library_sync", source_label=f"历史库字段 {item.database_id}",
            source_reference=item.package_uid, resolution="use_incoming" if adopt else "keep_existing")
    for field in db.query(ViewLocalField).filter(ViewLocalField.is_promoted.is_(False)).all():
        view = db.get(PatentView, field.view_id)
        if view:
            ViewService.promote_local_field(db, view, field, global_group="人工扩展")
    database = db.query(PatentDatabase).filter(PatentDatabase.is_default.is_(True)).first()
    if database:
        rebuild_database_families(db, database.id, commit=False)
    db.add(FieldDefinition(canonical_key=marker_key, display_name="统一 Wiki 数据升级",
        storage_kind="migration", is_active=False, validation_schema={"backup_path": str(backup) if backup else None}))
    db.commit()
