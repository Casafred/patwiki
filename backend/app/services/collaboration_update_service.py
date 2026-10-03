"""Saved sharing scopes and administrator review of pooled external updates."""
from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.models import ConnectorDefinition, Patent, PatentDatabase, SyncUpdateBatch
from app.models.collaboration_sync import SyncAggregationBatch, SyncPackage, SyncPackageRecord, SyncSharingPreference
from app.services.collaboration_identity_service import audit, require_admin
from app.services.sync_update_service import EXPLICIT_UPDATE_FIELDS, SyncUpdateService


def sharing_preference(db: Session, user_id: int) -> dict:
    row = db.get(SyncSharingPreference, user_id)
    return {key: getattr(row, key) if row else ([] if key != "update_fields" else ["legal_status"])
            for key in ("shared_database_ids", "update_database_ids", "update_fields")}


def save_sharing_preference(db: Session, user_id: int, request) -> dict:
    from app.services.collaboration_sync_service import _owned_export_databases, PRIVILEGED
    from app.services.collaboration_identity_service import roles
    selected = set(request.shared_database_ids) | set(request.update_database_ids)
    databases = db.query(PatentDatabase).filter(PatentDatabase.id.in_(selected), PatentDatabase.is_archived.is_(False)).all()
    if len(databases) != len(selected):
        raise HTTPException(404, "配置中的数据库不存在或已归档")
    if not roles(db, user_id) & PRIVILEGED and not selected.issubset(_owned_export_databases(db, user_id)):
        raise HTTPException(403, "没有配置所选数据库的权限")
    if set(request.update_fields) - EXPLICIT_UPDATE_FIELDS:
        raise HTTPException(400, "更新范围包含非公共事实字段")
    row = db.get(SyncSharingPreference, user_id)
    if row is None:
        row = SyncSharingPreference(user_id=user_id)
        db.add(row)
    for key in ("shared_database_ids", "update_database_ids", "update_fields"):
        setattr(row, key, list(dict.fromkeys(getattr(request, key))))
    db.commit()
    return sharing_preference(db, user_id)


def _batch(db: Session, user_id: int, batch_uid: str) -> SyncAggregationBatch:
    require_admin(db, user_id)
    batch = db.query(SyncAggregationBatch).filter_by(batch_uid=batch_uid).first()
    if not batch or batch.status != "submitted":
        raise HTTPException(409, "请先提交汇总批次，再统一更新")
    return batch


def pooled_requests(db: Session, batch: SyncAggregationBatch) -> list[dict]:
    from app.services.collaboration_sync_service import _batch_local_patents
    pooled = {}
    for package in db.query(SyncPackage).filter(SyncPackage.package_uid.in_(batch.package_uids or [])).all():
        requests = {item.get("entity_uid"): item for item in (package.manifest_json or {}).get("update_requests", [])}
        rows = db.query(SyncPackageRecord).filter(SyncPackageRecord.package_id == package.id,
            SyncPackageRecord.entity_uid.in_(requests)).all() if requests else []
        matched = _batch_local_patents(db, rows, package.manifest_json["origin_node_uid"])
        for row in rows:
            patent = matched.get(row.id)
            if patent is None or patent.deleted_at:
                continue
            if not SyncUpdateService._patent_in_database(db, patent, batch.target_database_id):
                continue
            item = pooled.setdefault(patent.id, {"patent_id": patent.id, "entity_uid": patent.entity_uid,
                "title": patent.title, "fields": set(), "sources": []})
            item["fields"].update(set(requests[row.entity_uid].get("fields", [])) & EXPLICIT_UPDATE_FIELDS)
            item["sources"].append({"package_uid": package.package_uid, "created_by": package.manifest_json.get("created_by")})
    return [{**item, "fields": sorted(item["fields"])} for item in pooled.values() if item["fields"]]


def preview_updates(db: Session, user_id: int, batch_uid: str, connector_id: int) -> dict:
    batch = _batch(db, user_id, batch_uid)
    requests = pooled_requests(db, batch)
    if not requests:
        raise HTTPException(400, "本批次没有可更新的专利请求")
    connector = db.get(ConnectorDefinition, connector_id)
    if not connector or not connector.enabled:
        raise HTTPException(404, "数据连接器不存在或未启用")
    fields = sorted({field for item in requests for field in item["fields"]})
    update = SyncUpdateService.preview(db, connector, batch.target_database_id,
        [item["patent_id"] for item in requests], fields)
    # Each patent keeps its requested scope even when a pooled query fetches a union.
    requested_fields = {item["patent_id"]: set(item["fields"]) for item in requests}
    for item in update.items:
        item.changed_fields = [field for field in item.changed_fields or [] if field in requested_fields.get(item.patent_id, set())]
        item.selected_fields = []
    batch.preview_json = {**(batch.preview_json or {}), "external_update_batch_id": update.id,
                          "update_requests": requests}
    audit(db, user_id, "aggregation_update_preview", detail={"batch_uid": batch_uid, "update_batch_id": update.id})
    db.commit()
    return SyncUpdateService._batch_dict(update)


def confirm_updates(db: Session, user_id: int, batch_uid: str, choices: list[dict]) -> dict:
    from app.models import User
    batch = _batch(db, user_id, batch_uid)
    update_id = (batch.preview_json or {}).get("external_update_batch_id")
    update = db.get(SyncUpdateBatch, update_id) if update_id else None
    if not update or update.database_id != batch.target_database_id:
        raise HTTPException(409, "尚未生成本批次的统一更新预览")
    if update.status != "confirmed":
        update = SyncUpdateService.confirm(db, update, choices, db.get(User, user_id).username)
    results = SyncUpdateService._batch_dict(update)
    batch.preview_json = {**(batch.preview_json or {}), "external_update_results": results}
    audit(db, user_id, "aggregation_update_confirmed", detail={"batch_uid": batch_uid, "update_batch_id": update.id})
    db.commit()
    return results
