"""Offline, read-only patent snapshot export and import."""
from __future__ import annotations

import sqlite3
import base64
import hashlib
import shutil
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4

from fastapi import HTTPException, UploadFile
from sqlalchemy import or_
from sqlalchemy.orm import Session, load_only
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from app.core.time import utc_now_naive
from app.models import DatabaseMembership, LegalStatus, Patent, PatentDatabase, PatentDatabaseMembership, PatentHistory, PatentType, Product, RiskLevel, User
from app.services.patent_identity_service import ensure_patent_identifiers
from app.models.collaboration_sync import (
    CollaborationCredential, PermissionGrant, SyncConflict, SyncEntityFieldState,
    SyncAggregationBatch, SyncChange, SyncPackage, SyncPackageMember, SyncPackageRecord, SyncUidMapping, SyncWorkspace, TrustedSyncDevice, SyncTombstone, SyncFieldOverlay,
)
from app.services.collaboration_identity_service import PASSWORDS, audit, roles, uid, workspace_dir
from app.services.collaboration_package_codec import MAX_BYTES, MAX_RECORDS, decode, decode_stream, encode_to, file_hash
from app.services.collaboration_package_codec import json_bytes
from app.services.patent_identity_service import (
    find_patents_by_identifier_specs_bulk,
    identifier_specs_from_values,
)
from app.services.patent_service import PatentService, _stringify_value
from app.services.patent_database_scope import in_database
from app.services.collaboration_library_field_service import PRIVATE_FIELDS, plan_library_fields, apply_library_fields

EXPORT_FIELDS = frozenset({
    "application_number", "publication_number", "grant_number", "title", "abstract", "claims",
    "description_full", "applicant", "inventor", "assignee", "agent", "filing_date",
    "publication_date", "grant_date", "priority_date", "priority_number", "priority_country",
    "country", "patent_type", "legal_status", "legal_status_date", "legal_status_details",
    "ipc_main", "ipc_all", "cpc_main", "cpc_all", "category", "subcategory",
    "technical_problem", "technical_effect", "technical_solution", "has_risk", "risk_level",
    "risk_description", "module", "application_status", "scope_description", "notes", "custom_fields",
})
PRIVILEGED = {"system_admin", "department_leader"}


def _owned_export_databases(db: Session, user_id: int) -> set[int]:
    owned = {row[0] for row in db.query(PatentDatabase.id).filter(PatentDatabase.owner_id == user_id).all()}
    owned.update(row[0] for row in db.query(DatabaseMembership.database_id).filter(
        DatabaseMembership.user_id == user_id, DatabaseMembership.role.in_(["owner", "editor"])).all())
    return owned


def _value(value):
    if hasattr(value, "value"):
        return value.value
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return value


def _audit_denial(db: Session, user_id: int, action: str, detail: dict) -> None:
    db.rollback()
    audit(db, user_id, action, detail=detail, result="denied")
    db.commit()


def _workspace(db: Session, user_id: int) -> SyncWorkspace:
    workspace = db.query(SyncWorkspace).first()
    if workspace is None:
        workspace = SyncWorkspace(workspace_uid=uid("ws"), node_uid=uid("node"), owner_user_id=user_id)
        db.add(workspace)
        db.flush()
    return workspace


def device_signing_identity(db: Session, user_id: int) -> dict:
    """Load or create this workspace's signing key in the OS credential store."""
    workspace = _workspace(db, user_id)
    try:
        import keyring

        if getattr(keyring.get_keyring(), "priority", 0) <= 0:
            raise RuntimeError("no secure credential store")
        encoded = keyring.get_password("PatWiki.Collaboration.DeviceSigning.v1", workspace.node_uid)
        if encoded:
            private_bytes = base64.b64decode(encoded, validate=True)
            private_key = Ed25519PrivateKey.from_private_bytes(private_bytes)
        else:
            private_key = Ed25519PrivateKey.generate()
            private_bytes = private_key.private_bytes(
                serialization.Encoding.Raw, serialization.PrivateFormat.Raw, serialization.NoEncryption(),
            )
            encoded = base64.b64encode(private_bytes).decode("ascii")
            keyring.set_password("PatWiki.Collaboration.DeviceSigning.v1", workspace.node_uid, encoded)
            if keyring.get_password("PatWiki.Collaboration.DeviceSigning.v1", workspace.node_uid) != encoded:
                raise RuntimeError("credential store did not persist the key")
        public_bytes = private_key.public_key().public_bytes(
            serialization.Encoding.Raw, serialization.PublicFormat.Raw,
        )
    except Exception as exc:
        raise HTTPException(503, "无法访问本机安全凭据库，未生成或签发同步包。请检查 Windows 凭据管理器。") from exc
    fingerprint = hashlib.sha256(public_bytes).hexdigest()
    workspace.public_key = base64.b64encode(public_bytes).decode("ascii")
    db.flush()
    return {
        "node_uid": workspace.node_uid,
        "name": workspace.name,
        "fingerprint": fingerprint,
        "public_key": workspace.public_key,
        "private_key": private_bytes,
    }


def trusted_device_keys(db: Session) -> dict[str, bytes]:
    devices = db.query(TrustedSyncDevice).filter(TrustedSyncDevice.revoked_at.is_(None)).all()
    trusted = {}
    for device in devices:
        try:
            key = base64.b64decode(device.public_key, validate=True)
        except (ValueError, TypeError):
            continue
        if len(key) == 32 and hashlib.sha256(key).hexdigest() == device.fingerprint:
            trusted[device.fingerprint] = key
    workspace = db.query(SyncWorkspace).first()
    if workspace and workspace.public_key:
        try:
            local_key = base64.b64decode(workspace.public_key, validate=True)
        except (ValueError, TypeError):
            local_key = b""
        if len(local_key) == 32:
            trusted[hashlib.sha256(local_key).hexdigest()] = local_key
    return trusted


def package_signer_is_trusted(db: Session, manifest: dict, trusted_keys: dict[str, bytes] | None = None) -> bool:
    fingerprint = manifest.get("signer_fingerprint")
    public_key = manifest.get("signer_public_key")
    if not fingerprint or not public_key:
        return False
    try:
        raw_key = base64.b64decode(public_key, validate=True)
    except (ValueError, TypeError):
        return False
    if len(raw_key) != 32 or hashlib.sha256(raw_key).hexdigest() != fingerprint:
        return False
    return (trusted_keys if trusted_keys is not None else trusted_device_keys(db)).get(fingerprint) == raw_key


def _validate_request(db: Session, user_id: int, request):
    fields = list(dict.fromkeys(request.fields))
    if not fields or "title" not in fields or set(fields) - EXPORT_FIELDS:
        raise HTTPException(400, "字段范围无效，必须包含标题且只能选择首期支持的字段")
    if request.include_attachments:
        raise HTTPException(400, "首期同步包暂不支持附件")
    recipients = list(dict.fromkeys(name.lower() for name in request.recipient_names))
    if any(not name or len(name) > 100 for name in recipients):
        raise HTTPException(400, "必须指定有效接收账号")
    databases = db.query(PatentDatabase).filter(PatentDatabase.id.in_(request.database_ids), PatentDatabase.is_archived.is_(False)).all()
    if len(databases) != len(set(request.database_ids)):
        raise HTTPException(404, "所选数据库不存在或已归档")
    privileged = bool(roles(db, user_id) & PRIVILEGED)
    if not privileged:
        owned_database_ids = _owned_export_databases(db, user_id)
        now = utc_now_naive()
        grants = db.query(PermissionGrant).filter(
            PermissionGrant.subject_user_id == user_id,
            PermissionGrant.scope_type == "database",
            PermissionGrant.revoked_at.is_(None),
            or_(PermissionGrant.expires_at.is_(None), PermissionGrant.expires_at > now),
        ).all()
        for database in databases:
            if database.id in owned_database_ids:
                continue
            matching = [grant for grant in grants if grant.scope_uid == database.database_uid and
                        "export" in (grant.actions or []) and set(fields).issubset(set(grant.field_scope or [])) and
                        (not request.product_ids or not (grant.scope_json or {}).get("product_ids") or
                         set(request.product_ids).issubset(set(grant.scope_json["product_ids"]))) and
                        (request.product_ids is not None or not (grant.scope_json or {}).get("product_ids"))]
            if not matching:
                raise HTTPException(403, f"没有数据库 {database.name} 的协同导出授权")
    return fields, recipients, databases


def _query(db: Session, request):
    scopes = [in_database(database_id) for database_id in request.database_ids]
    query = db.query(Patent).filter(Patent.deleted_at.is_(None)).filter(or_(*scopes))
    if request.patent_ids is not None:
        query = query.filter(Patent.id.in_(request.patent_ids))
    if request.product_ids is not None:
        query = query.filter(Patent.product_id.in_(request.product_ids))
    return query.order_by(Patent.id)


def _assert_record_scope(patent: Patent, request, fields: list[str], privileged: bool,
                         memberships: set[int], grants_by_database: dict[str, list[PermissionGrant]],
                         database_uids: dict[int, str]):
    if privileged:
        return
    if patent.product_id is None:
        raise HTTPException(403, "未分类记录需要领导或管理员导出")
    matching_db_ids = memberships & set(request.database_ids)
    if patent.database_id in request.database_ids:
        matching_db_ids.add(patent.database_id)
    for database_id in matching_db_ids:
        for grant in grants_by_database.get(database_uids.get(database_id, ""), []):
            product_scope = (grant.scope_json or {}).get("product_ids") or []
            if "export" in (grant.actions or []) and set(fields).issubset(set(grant.field_scope or [])) and (
                not product_scope or patent.product_id in product_scope
            ):
                return
    raise HTTPException(403, "所选范围包含未授权品类")


def _record_batch(db: Session, user_id: int, request, fields: list[str], databases: list[PatentDatabase], node_uid: str,
                  *, patent_ids=None, include_tombstones=True):
    query = _query(db, request)
    if patent_ids is not None:
        query = query.filter(Patent.id.in_(patent_ids))
    count = query.count()
    if count > MAX_RECORDS:
        raise HTTPException(413, f"单个同步包最多 {MAX_RECORDS} 条记录，请缩小范围")
    projection = {"id", "product_id", "database_id", "entity_uid", "origin_node_uid", "record_version", "updated_at"}
    projection.update(fields)
    patents = query.options(load_only(*(getattr(Patent, field) for field in projection))).all()
    database_uids = {item.id: item.database_uid for item in databases}
    privileged = bool(roles(db, user_id) & PRIVILEGED)
    owned_database_ids = _owned_export_databases(db, user_id) & set(request.database_ids)
    grants_by_database: dict[str, list[PermissionGrant]] = {}
    if not privileged:
        now = utc_now_naive()
        grants = db.query(PermissionGrant).filter(
            PermissionGrant.subject_user_id == user_id, PermissionGrant.scope_type == "database",
            PermissionGrant.revoked_at.is_(None),
            or_(PermissionGrant.expires_at.is_(None), PermissionGrant.expires_at > now),
        ).all()
        for grant in grants:
            grants_by_database.setdefault(grant.scope_uid, []).append(grant)
    memberships_by_patent: dict[int, set[int]] = {}
    patent_ids = [patent.id for patent in patents]
    if patent_ids:
        for patent_id, database_id in db.query(
            PatentDatabaseMembership.patent_id, PatentDatabaseMembership.database_id
        ).filter(
            PatentDatabaseMembership.patent_id.in_(patent_ids),
            PatentDatabaseMembership.database_id.in_(request.database_ids),
        ).all():
            memberships_by_patent.setdefault(patent_id, set()).add(database_id)
    default_scope_ids = {database.id for database in databases if database.is_default}
    for patent in patents:
        if default_scope_ids:
            memberships_by_patent.setdefault(patent.id, set()).update(default_scope_ids)
    product_ids = {patent.product_id for patent in patents if patent.product_id}
    products = {item.id: item for item in db.query(Product).filter(Product.id.in_(product_ids)).all()} if product_ids else {}
    history_by_patent: dict[int, list[dict]] = {}
    if patent_ids:
        for change in db.query(PatentHistory).filter(PatentHistory.patent_id.in_(patent_ids),
                PatentHistory.source.notin_(["collaboration_sync", "department_publication"])).order_by(PatentHistory.id).all():
            history_by_patent.setdefault(change.patent_id, []).append({
                "change_uid": change.change_uid, "field_key": change.field_key,
                "old_value": change.old_value, "new_value": change.new_value,
                "changed_by": change.changed_by, "actor_uid": change.actor_uid,
                "source": change.source, "created_at": _value(change.created_at),
            })
    records = []
    for patent in patents:
        row_memberships = memberships_by_patent.get(patent.id, set()) | {patent.database_id}
        _assert_record_scope(patent, request, fields, privileged or bool(owned_database_ids & row_memberships), memberships_by_patent.get(patent.id, set()),
                             grants_by_database, database_uids)
        if not patent.entity_uid:
            patent.entity_uid = uid("pat")
        if not patent.origin_node_uid:
            patent.origin_node_uid = node_uid
        memberships = memberships_by_patent.get(patent.id, set())
        if patent.database_id:
            memberships.add(patent.database_id)
        scopes = [database_uids[database_id] for database_id in memberships if database_id in database_uids]
        product = products.get(patent.product_id)
        payload = {field: _value(getattr(patent, field)) for field in fields}
        from app.models.collaboration_sync import SyncLibraryField
        annotations = db.query(SyncLibraryField).filter(SyncLibraryField.patent_id == patent.id,
            SyncLibraryField.database_id.in_(request.database_ids)).all()
        library_values = []
        for annotation in annotations:
            library_values.append({"database_uid": database_uids[annotation.database_id], "source_database_uid": annotation.source_database_uid,
                "field_key": annotation.field_key, "baseline_value": annotation.baseline_value,
                "value": annotation.local_value if annotation.has_overlay else annotation.baseline_value,
                "editor_user_uid": db.get(User, annotation.editor_user_id).user_uid if annotation.editor_user_id else None,
                "reason": annotation.reason})
        if "custom_fields" in payload and isinstance(payload["custom_fields"], dict):
            # Attachment IDs, local paths and download URLs are machine-local.
            payload["custom_fields"] = {
                key: value for key, value in payload["custom_fields"].items()
                if key != "attachments"
            }
        records.append({"entity_type": "patent", "entity_uid": patent.entity_uid,
                        "record_version": patent.record_version or 1,
                        "origin_node_uid": patent.origin_node_uid,
                        "updated_at": _value(patent.updated_at),
                        "scope": {"database_uids": sorted(scopes),
                                  "product": {"code": product.code, "name": product.name} if product else None},
                        "payload": payload, "field_provenance": {"changes": history_by_patent.get(patent.id, []), "library_values": library_values}})
    selected_database_ids = {database.id for database in databases}
    tombstones = db.query(SyncTombstone).filter(SyncTombstone.entity_type == "patent").yield_per(250) if include_tombstones else []
    for tombstone in tombstones:
        scope = tombstone.scope_json or {}
        if scope.get("database_id") not in selected_database_ids:
            continue
        records.append({"entity_type": "patent_tombstone", "operation": "delete",
                        "entity_uid": tombstone.entity_uid, "record_version": max(1, tombstone.base_version),
                        "origin_node_uid": node_uid, "updated_at": _value(tombstone.deleted_at),
                        "scope": {"database_uids": [database_uids[scope["database_id"]]]},
                        "payload": {}, "base_version": tombstone.base_version,
                        "field_provenance": {"deleted_at": _value(tombstone.deleted_at), "base_version": tombstone.base_version,
                            "deletion_scope": scope.get("deletion_scope", "library_exit")}})
    return records


def _iter_records(db: Session, user_id: int, request, fields: list[str], databases: list[PatentDatabase], node_uid: str):
    """Keyset pagination bounds patents, histories and memberships per export batch."""
    last_id = 0
    while True:
        ids = [row[0] for row in _query(db, request).filter(Patent.id > last_id).with_entities(Patent.id).limit(250).all()]
        if not ids:
            break
        yield from _record_batch(db, user_id, request, fields, databases, node_uid, patent_ids=ids, include_tombstones=False)
        last_id = ids[-1]
    yield from _record_batch(db, user_id, request, fields, databases, node_uid, patent_ids=[])


def _records(db: Session, user_id: int, request, fields: list[str], databases: list[PatentDatabase], node_uid: str):
    return list(_iter_records(db, user_id, request, fields, databases, node_uid))


def _validate_export_scope(db: Session, user_id: int, request, fields: list[str], databases: list[PatentDatabase]) -> None:
    """Check row-level grants using scalar columns, keeping preview cheap."""
    if roles(db, user_id) & PRIVILEGED:
        return
    owned_database_ids = _owned_export_databases(db, user_id) & set(request.database_ids)
    database_uids = {item.id: item.database_uid for item in databases}
    now = utc_now_naive()
    grants = db.query(PermissionGrant).filter(
        PermissionGrant.subject_user_id == user_id, PermissionGrant.scope_type == "database",
        PermissionGrant.revoked_at.is_(None),
        or_(PermissionGrant.expires_at.is_(None), PermissionGrant.expires_at > now),
    ).all()
    grants_by_database: dict[str, list[PermissionGrant]] = {}
    for grant in grants:
        grants_by_database.setdefault(grant.scope_uid, []).append(grant)
    rows = _query(db, request).with_entities(Patent.id, Patent.product_id, Patent.database_id).all()
    patent_ids = [row[0] for row in rows]
    memberships: dict[int, set[int]] = {}
    if patent_ids:
        for patent_id, database_id in db.query(PatentDatabaseMembership.patent_id, PatentDatabaseMembership.database_id).filter(
            PatentDatabaseMembership.patent_id.in_(patent_ids),
            PatentDatabaseMembership.database_id.in_(request.database_ids),
        ).all():
            memberships.setdefault(patent_id, set()).add(database_id)
    default_scope_ids = {database.id for database in databases if database.is_default}
    for patent_id, product_id, database_id in rows:
        if owned_database_ids & (memberships.get(patent_id, set()) | default_scope_ids | {database_id}):
            continue
        if product_id is None:
            raise HTTPException(403, "未分类记录需要领导或管理员导出")
        scope_ids = memberships.get(patent_id, set()) | default_scope_ids
        if database_id in request.database_ids:
            scope_ids.add(database_id)
        allowed = False
        for scope_id in scope_ids:
            for grant in grants_by_database.get(database_uids.get(scope_id, ""), []):
                product_scope = (grant.scope_json or {}).get("product_ids") or []
                if "export" in (grant.actions or []) and set(fields).issubset(set(grant.field_scope or [])) and (
                    not product_scope or product_id in product_scope
                ):
                    allowed = True
                    break
            if allowed:
                break
        if not allowed:
            raise HTTPException(403, "所选范围包含未授权品类")


def preview_export(db: Session, user_id: int, request) -> dict:
    try:
        fields, recipients, databases = _validate_request(db, user_id, request)
        query = _query(db, request)
        count = query.count()
        if count > MAX_RECORDS:
            raise HTTPException(413, f"单个同步包最多 {MAX_RECORDS} 条记录，请缩小范围")
        _validate_export_scope(db, user_id, request, fields, databases)
        return {"count": count, "fields": fields, "recipients": recipients, "estimated_bytes": None}
    except HTTPException as exc:
        _audit_denial(db, user_id, "package_export_denied", {"database_ids": request.database_ids,
                       "status_code": exc.status_code, "reason": str(exc.detail)})
        raise


def export_package(db: Session, user_id: int, request) -> dict:
    try:
        fields, recipients, databases = _validate_request(db, user_id, request)
        workspace = _workspace(db, user_id)
        _validate_export_scope(db, user_id, request, fields, databases)
        record_count = _query(db, request).count()
        selected_ids = {item.id for item in databases}
        record_count += sum(1 for row in db.query(SyncTombstone.scope_json).filter(SyncTombstone.entity_type == "patent").yield_per(250)
            if (row[0] or {}).get("database_id") in selected_ids)
        if record_count > MAX_RECORDS:
            raise HTTPException(413, "同步包记录过多，请缩小范围")
        records = _iter_records(db, user_id, request, fields, databases, workspace.node_uid)
        signing_identity = device_signing_identity(db, user_id)
    except HTTPException as exc:
        _audit_denial(db, user_id, "package_export_denied", {"database_ids": request.database_ids,
                       "status_code": exc.status_code, "reason": str(exc.detail)})
        raise
    now = utc_now_naive()
    package_uid = uid("pkg")
    from app.models.collaboration_sync import SyncExportRecordState
    mode = getattr(request, "mode", "full")
    base = None
    scope_uids = sorted(item.database_uid for item in databases)
    if mode == "delta":
        for previous in db.query(SyncPackage).filter_by(direction="outbox", created_by=user_id).order_by(SyncPackage.id.desc()).all():
            data = previous.manifest_json or {}
            if (sorted(item["database_uid"] for item in data.get("databases", [])) == scope_uids and
                data.get("fields") == fields and data.get("recipient_names", []) == recipients and
                data.get("selection") == {"patent_ids": request.patent_ids, "product_ids": request.product_ids}):
                base = previous
                break
        if base is None:
            mode = "full"
    def content_hash(record):
        return hashlib.sha256(json_bytes({key: record.get(key) for key in ("entity_type", "scope", "payload", "field_provenance")})).hexdigest()
    def previous_hash(entity_uid):
        if base is None:
            return None
        row = db.query(SyncExportRecordState.content_hash).filter_by(package_uid=base.package_uid, entity_uid=entity_uid).first()
        return row[0] if row else None
    if mode == "delta":
        record_count = sum(1 for record in _iter_records(db, user_id, request, fields, databases, workspace.node_uid)
            if content_hash(record) != previous_hash(record["entity_uid"]))
    original_records = records
    def checkpointed_records():
        for record in original_records:
            digest = content_hash(record)
            prior = previous_hash(record["entity_uid"])
            db.execute(SyncExportRecordState.__table__.insert().values(package_uid=package_uid,
                entity_uid=record["entity_uid"], content_hash=digest))
            if mode == "full" or prior != digest:
                yield record
    records = checkpointed_records()
    user = db.get(User, user_id)
    manifest = {"package_id": package_uid, "profile": "patent-snapshot-v1", "package_type": getattr(request, "package_type", "snapshot"),
                "created_at": now.isoformat(), "expires_at": (now + timedelta(days=request.expires_days)).isoformat(),
                "created_by": {"user_uid": user.user_uid, "username": user.username},
                "origin_node_uid": workspace.node_uid, "fields": fields, "count": record_count,
                "databases": [{"database_uid": item.database_uid, "name": item.name} for item in databases],
                "signature_status": "signed", "signer_fingerprint": signing_identity["fingerprint"],
                "signer_public_key": signing_identity["public_key"]}
    from app.services.collaboration_update_service import sharing_preference
    preference = sharing_preference(db, user_id)
    update_ids = [item.id for item in databases if item.id in preference["update_database_ids"]]
    manifest["update_requests"] = [{"entity_uid": row[0], "fields": preference["update_fields"]}
        for row in _query(db, request).filter(or_(*(in_database(item) for item in update_ids))).with_entities(Patent.entity_uid).yield_per(250)] if update_ids else []
    manifest["external_update_results"] = getattr(request, "external_update_results", {})
    manifest.update({"export_mode": mode, "base_package_uid": base.package_uid if base else None,
        "recipient_names": recipients, "selection": {"patent_ids": request.patent_ids, "product_ids": request.product_ids}})
    permissions = {"access": "viewer", "recipients": recipients, "fields": fields,
                   "can_edit": False, "can_redistribute": False}
    path = workspace_dir() / "outbox" / f"{package_uid}.pwshare"
    try:
        with path.open("xb") as stream:
            encode_to(stream, manifest, permissions, iter(records), request.password, signing_identity["private_key"])
        if path.stat().st_size > MAX_BYTES:
            raise HTTPException(413, "同步包过大，请缩小范围")
        digest = hashlib.sha256()
        with path.open("rb") as stream:
            for chunk in iter(lambda: stream.read(256 * 1024), b""):
                digest.update(chunk)
    except Exception:
        path.unlink(missing_ok=True)
        raise
    package = SyncPackage(package_uid=package_uid, package_type=manifest["package_type"], direction="outbox",
                          path=str(path), file_hash=digest.hexdigest(), created_by=user_id,
                          status="created", access="viewer", manifest_json=manifest,
                          signature_status="signed",
                          expires_at=now + timedelta(days=request.expires_days))
    db.add(package)
    db.flush()
    recipient_rows = db.query(CollaborationCredential.login_name, CollaborationCredential.user_id).filter(
        CollaborationCredential.active.is_(True), CollaborationCredential.login_name.in_(recipients)
    ).all()
    recipient_ids = {name.lower(): user_id for name, user_id in recipient_rows}
    for recipient in recipients:
        db.add(SyncPackageMember(package_id=package.id, user_id=recipient_ids.get(recipient),
                                 subject_label=recipient, access="viewer", field_scope=fields))
    audit(db, user_id, "package_exported", package_id=package.id, detail={"count": record_count})
    try:
        db.commit()
    except Exception:
        db.rollback()
        path.unlink(missing_ok=True)
        raise
    return {"package_uid": package_uid, "path": str(path), "file_hash": package.file_hash,
            "count": record_count, "expires_at": manifest["expires_at"]}


async def read_upload(upload: UploadFile) -> bytes:
    raw = await upload.read(MAX_BYTES + 1)
    if len(raw) > MAX_BYTES:
        raise HTTPException(413, "同步包超过 100MB")
    return raw


def process_package_stream(db: Session, user_id: int, source, password: str, *, inspect: bool = False) -> dict:
    """Validate before writing, then stream records into one atomic transaction."""
    source.seek(0, 2)
    if source.tell() > MAX_BYTES:
        raise HTTPException(413, "同步包过大")
    source.seek(0)
    digest = hashlib.sha256()
    for chunk in iter(lambda: source.read(256 * 1024), b""):
        digest.update(chunk)
    source.seek(0)
    sample = []
    def sample_record(record):
        if len(sample) < 3:
            sample.append(record)
    manifest, permissions, _ = decode_stream(source, password, trusted_device_keys(db), sample_record)
    if datetime.fromisoformat(manifest["expires_at"]) <= utc_now_naive():
        raise HTTPException(410, "同步包已过期")
    package_uid, checksum = manifest["package_id"], digest.hexdigest()
    if inspect:
        return {"manifest": manifest, "permissions": permissions, "count": manifest["count"],
                "sample": sample, "file_hash": checksum}
    existing = db.query(SyncPackage).filter(or_(SyncPackage.package_uid == package_uid,
        (SyncPackage.file_hash == checksum) & (SyncPackage.direction == "inbox"))).first()
    if existing:
        return {"package_uid": package_uid, "count": manifest["count"], "status": "already_processed"}
    path = workspace_dir() / "inbox" / f"{package_uid}.pwshare"
    try:
        source.seek(0)
        with path.open("xb") as target:
            shutil.copyfileobj(source, target, 256 * 1024)
        package = SyncPackage(package_uid=package_uid, package_type=manifest["package_type"], direction="inbox",
            path=str(path), file_hash=checksum, created_by=user_id, status="imported", access="viewer",
            manifest_json=manifest, signature_status=manifest["signature_status"],
            expires_at=datetime.fromisoformat(manifest["expires_at"]))
        db.add(package)
        db.flush()
        db.add(SyncPackageMember(package_id=package.id, user_id=user_id,
            subject_label=db.get(User, user_id).username, access="viewer", field_scope=permissions["fields"]))
        def save_record(record):
            db.execute(SyncPackageRecord.__table__.insert().values(package_id=package.id,
                entity_type=record["entity_type"], entity_uid=record["entity_uid"],
                record_version=record["record_version"], scope_json=record["scope"],
                payload_json=record["payload"], field_provenance={**record["field_provenance"], "base_version": record.get("base_version", 0)}))
        source.seek(0)
        decode_stream(source, password, trusted_device_keys(db), save_record)
        audit(db, user_id, "package_imported", package_id=package.id, detail={"count": manifest["count"]})
        db.commit()
    except Exception:
        db.rollback()
        path.unlink(missing_ok=True)
        raise
    return {"package_uid": package_uid, "count": manifest["count"], "status": "imported"}


def _validated_import(db: Session, user_id: int, raw: bytes, password: str):
    try:
        manifest, permissions, records = decode(raw, password, trusted_device_keys(db))
        if datetime.fromisoformat(manifest["expires_at"]) <= utc_now_naive():
            raise HTTPException(410, "同步包已过期")
        user = db.get(User, user_id)
        # Recipient labels are provenance only. Target database permissions are
        # checked when applying the package, so a forwarded member file can be
        # reviewed by the department administrator.
        return manifest, permissions, records
    except HTTPException as exc:
        _audit_denial(db, user_id, "package_import_denied", {"file_hash": file_hash(raw),
                       "status_code": exc.status_code, "reason": str(exc.detail)})
        raise


def inspect_package(db: Session, user_id: int, raw: bytes, password: str) -> dict:
    manifest, permissions, records = _validated_import(db, user_id, raw, password)
    return {"manifest": manifest, "permissions": permissions, "count": len(records), "sample": records[:3],
            "file_hash": file_hash(raw)}


def import_package(db: Session, user_id: int, raw: bytes, password: str) -> dict:
    manifest, permissions, records = _validated_import(db, user_id, raw, password)
    package_uid = manifest["package_id"]
    existing = db.query(SyncPackage).filter(
        or_(SyncPackage.package_uid == package_uid,
            (SyncPackage.file_hash == file_hash(raw)) & (SyncPackage.direction == "inbox"))
    ).first()
    if existing:
        audit(db, user_id, "package_import_skipped", package_id=existing.id,
              detail={"package_uid": package_uid, "reason": "already_processed"})
        db.commit()
        return {"package_uid": package_uid, "count": len(records), "status": "already_processed"}
    path = workspace_dir() / "inbox" / f"{package_uid}.pwshare"
    with path.open("xb") as stream:
        stream.write(raw)
    package = SyncPackage(package_uid=package_uid, package_type=manifest["package_type"], direction="inbox",
                          path=str(path), file_hash=file_hash(raw), created_by=user_id,
                          status="imported", access="viewer", manifest_json=manifest,
                          signature_status=manifest.get("signature_status", "not_signed"), applied_at=None,
                          expires_at=datetime.fromisoformat(manifest["expires_at"]))
    db.add(package)
    db.flush()
    db.add(SyncPackageMember(package_id=package.id, user_id=user_id, subject_label=db.get(User, user_id).username,
                             access="viewer", field_scope=permissions["fields"]))
    for record in records:
        db.add(SyncPackageRecord(package_id=package.id, entity_type=record.get("entity_type", "patent"), entity_uid=record["entity_uid"],
                                 record_version=record["record_version"], scope_json=record["scope"],
                                 payload_json=record["payload"], field_provenance={**record["field_provenance"], "base_version": record.get("base_version", 0)}))
    audit(db, user_id, "package_imported", package_id=package.id, detail={"count": len(records)})
    try:
        db.commit()
    except Exception:
        db.rollback()
        path.unlink(missing_ok=True)
        raise
    return {"package_uid": package_uid, "count": len(records), "status": "imported"}


_NO_BASELINE = object()
_DATE_FIELDS = {"filing_date", "publication_date", "grant_date", "priority_date", "legal_status_date"}
_ENUM_FIELDS = {"patent_type": PatentType, "legal_status": LegalStatus, "risk_level": RiskLevel}


def _batch_local_patents(db: Session, records: list[SyncPackageRecord], origin_node_uid: str | None = None) -> dict[int, Patent | None]:
    """Resolve rows by stable UID, then batch-match existing official numbers."""
    entity_uids = list(dict.fromkeys(row.entity_uid for row in records))
    by_entity: dict[str, Patent] = {}
    for offset in range(0, len(entity_uids), 500):
        rows = db.query(Patent).filter(
            Patent.entity_uid.in_(entity_uids[offset:offset + 500]),
        ).all()
        by_entity.update({row.entity_uid: row for row in rows})
        if origin_node_uid:
            aliases = db.query(SyncUidMapping, Patent).join(Patent, Patent.id == SyncUidMapping.patent_id).filter(
                SyncUidMapping.origin_node_uid == origin_node_uid,
                SyncUidMapping.remote_uid.in_(entity_uids[offset:offset + 500]),
            ).all()
            for alias, patent in aliases:
                direct = by_entity.get(alias.remote_uid)
                if direct is not None and direct.id != patent.id:
                    raise HTTPException(409, "同步 UID 映射与本机实体冲突，请先人工处理身份冲突")
                by_entity[alias.remote_uid] = patent

    result: dict[int, Patent | None] = {}
    for row in records:
        patent = by_entity.get(row.entity_uid)
        if patent is None:
            result[row.id] = None
        elif patent.deleted_at:
            raise HTTPException(409, "本机已有同 UID 的已删除专利，请先人工恢复后再同步")
        else:
            result[row.id] = patent

    candidates: dict[int, set[int]] = {row.id: set() for row in records}
    for field_key in ("application_number", "publication_number", "grant_number"):
        values = list(dict.fromkeys(
            str((row.payload_json or {}).get(field_key)) for row in records
            if (row.payload_json or {}).get(field_key)
        ))
        by_value: dict[str, set[int]] = {}
        column = getattr(Patent, field_key)
        for offset in range(0, len(values), 500):
            matches = db.query(Patent).filter(column.in_(values[offset:offset + 500])).all()
            for match in matches:
                by_value.setdefault(str(getattr(match, field_key)), set()).add(match.id)
        for row in records:
            value = (row.payload_json or {}).get(field_key)
            if value:
                candidates[row.id].update(by_value.get(str(value), set()))

    specs_by_row = {
        row.id: identifier_specs_from_values({
            "application": (row.payload_json or {}).get("application_number"),
            "publication": (row.payload_json or {}).get("publication_number"),
            "grant": (row.payload_json or {}).get("grant_number"),
        }, (row.payload_json or {}).get("country"))
        for row in records
    }
    for row_id, matches in find_patents_by_identifier_specs_bulk(db, specs_by_row).items():
        candidates[row_id].update(match.id for match in matches)

    candidate_ids = sorted({patent_id for ids in candidates.values() for patent_id in ids})
    by_id = {
        row.id: row
        for offset in range(0, len(candidate_ids), 500)
        for row in db.query(Patent).filter(Patent.id.in_(candidate_ids[offset:offset + 500])).all()
    }
    for row in records:
        matches = [by_id[patent_id] for patent_id in candidates[row.id] if patent_id in by_id]
        uid_match = by_entity.get(row.entity_uid)
        if uid_match and any(match.id != uid_match.id for match in matches):
            raise HTTPException(409, "同步包中的官方号码与本机其他专利冲突，请先人工处理身份冲突")
        if uid_match:
            continue
        active = [match for match in matches if match.deleted_at is None]
        if len(active) > 1:
            raise HTTPException(409, "本机号码索引命中多条专利，需先人工处理身份冲突")
        if active:
            result[row.id] = active[0]
        elif matches:
            raise HTTPException(409, "本机已有相同专利号码的已删除记录，请先人工恢复后再同步")
        else:
            result[row.id] = None
    return result


def _ensure_database_memberships(db: Session, patent: Patent, target_database: PatentDatabase) -> None:
    database_ids = {target_database.id}
    default_database = db.query(PatentDatabase).filter(PatentDatabase.is_default.is_(True)).first()
    if default_database:
        database_ids.add(default_database.id)
    for database_id in database_ids:
        if not db.query(PatentDatabaseMembership).filter_by(
            patent_id=patent.id, database_id=database_id,
        ).first():
            db.add(PatentDatabaseMembership(patent_id=patent.id, database_id=database_id))


def _local_value(patent: Patent, field_key: str):
    if field_key == "custom_fields":
        return {
            key: value for key, value in (patent.custom_fields or {}).items()
            if key != "attachments"
        }
    return _value(getattr(patent, field_key))


def _matching_apply_grants(db: Session, user_id: int, database: PatentDatabase,
                           password: str | None) -> list[PermissionGrant]:
    now = utc_now_naive()
    grants = db.query(PermissionGrant).filter(
        PermissionGrant.subject_user_id == user_id,
        PermissionGrant.scope_type == "database",
        PermissionGrant.scope_uid == database.database_uid,
        PermissionGrant.revoked_at.is_(None),
        or_(PermissionGrant.expires_at.is_(None), PermissionGrant.expires_at > now),
    ).all()
    matching = []
    for grant in grants:
        if "apply" not in (grant.actions or []) or not password or not grant.password_digest:
            continue
        try:
            if PASSWORDS.verify(grant.password_digest, password):
                matching.append(grant)
        except Exception:
            continue
    return matching


def _has_matching_apply_grant(grants: list[PermissionGrant], product: Product | None,
                              fields: set[str]) -> bool:
    if product is None:
        return False
    for grant in grants:
        product_scope = (grant.scope_json or {}).get("product_ids") or []
        if fields.issubset(set(grant.field_scope or [])) and (
            not product_scope or product.id in product_scope
        ):
            return True
    return False


def _apply_context(db: Session, user_id: int, package_uid: str, database_id: int, source_database_uid=None):
    package = _visible_package(db, user_id, package_uid)
    if package.direction != "inbox" or package.status not in {"imported", "partially_applied"}:
        raise HTTPException(409, "只有已导入且未完成应用的收件包可以写入主表")
    if package.expires_at and package.expires_at <= utc_now_naive():
        raise HTTPException(410, "同步包已过期，不能应用到主表")
    database = db.get(PatentDatabase, database_id)
    if not database or database.is_archived:
        raise HTTPException(404, "目标数据库不存在或已归档")
    if (package.manifest_json or {}).get("export_mode") == "delta":
        base_uid = package.manifest_json.get("base_package_uid")
        baseline = db.query(SyncPackage).filter_by(package_uid=base_uid, direction="inbox", status="applied").first()
        if not baseline:
            raise HTTPException(409, "缺少增量文件的已应用基线，请补齐前序文件或导入完整文件")
        applied_target = (baseline.manifest_json or {}).get("applied_target_database_uid")
        shared_target = (baseline.manifest_json or {}).get("shared_source_results", {}).get(source_database_uid, {}).get("target_database_uid")
        if database.database_uid not in {applied_target, shared_target}:
            raise HTTPException(409, "增量基线未应用到该目标库，请导入完整文件")
    selected_target_uid = (package.manifest_json or {}).get("applied_target_database_uid")
    if selected_target_uid and selected_target_uid != database.database_uid and not source_database_uid:
        raise HTTPException(409, "部分应用的同步包必须继续应用到首次选择的本机数据库")
    records = db.query(SyncPackageRecord).filter(SyncPackageRecord.package_id == package.id).order_by(
        SyncPackageRecord.id
    ).all()
    if source_database_uid:
        source_uids = {item.get("database_uid") for item in (package.manifest_json or {}).get("databases", [])}
        if source_database_uid not in source_uids:
            raise HTTPException(400, "同步包不包含所选来源库")
        records = [row for row in records if source_database_uid in (row.scope_json or {}).get("database_uids", [])]
    return package, database, records


def _merge_plan(db: Session, user_id: int, package: SyncPackage, database: PatentDatabase,
                records: list[SyncPackageRecord], edit_password: str | None) -> tuple[list[dict], list[dict]]:
    manifest = package.manifest_json or {}
    origin_node_uid = manifest.get("origin_node_uid")
    if not origin_node_uid:
        raise HTTPException(400, "同步包缺少來源設備標識")
    privileged = bool(roles(db, user_id) & PRIVILEGED)
    if package.package_type == "department_publication" and not privileged:
        from app.models.collaboration_sync import CollaborationEnrollment
        enrollment = db.get(CollaborationEnrollment, user_id)
        signer = manifest.get("signer_public_key")
        if not ((enrollment and enrollment.issuer_public_key == signer) or package_signer_is_trusted(db, manifest)):
            raise HTTPException(403, "部门发布文件的签发者与管理员配置不匹配")
    if not privileged and "viewer" in roles(db, user_id):
        raise HTTPException(403, "只读协作者不能应用同步包到主表")
    # A normal authenticated editor uses target database permissions. Legacy
    # per-package edit passwords remain accepted for compatibility but are not
    # required by the department workflow.
    apply_grants = [] if privileged else _matching_apply_grants(db, user_id, database, edit_password)
    products = db.query(Product).filter(Product.is_active.is_(True)).all()
    products_by_code = {product.code: product for product in products if product.code}
    products_by_name = {product.name: product for product in products}
    local_patents = _batch_local_patents(db, records, origin_node_uid)
    entity_uids = list(dict.fromkeys(row.entity_uid for row in records))
    baselines: dict[tuple[str, str], SyncEntityFieldState] = {}
    for offset in range(0, len(entity_uids), 500):
        states = db.query(SyncEntityFieldState).filter(
            SyncEntityFieldState.origin_node_uid == origin_node_uid,
            SyncEntityFieldState.entity_uid.in_(entity_uids[offset:offset + 500]),
        ).all()
        baselines.update({(state.entity_uid, state.field_key): state for state in states})
    plans, conflicts = [], []
    for row in records:
        payload = row.payload_json or {}
        if package.package_type == "department_publication":
            payload = {key: value for key, value in payload.items() if key in _PUBLICATION_FIELDS}
        if row.entity_type == "patent_tombstone":
            patent = local_patents[row.id]
            membership = db.query(DatabaseMembership).filter_by(user_id=user_id, database_id=database.id).first()
            if not privileged and not (membership and membership.role in {"owner", "editor"}):
                raise HTTPException(403, "没有目标库的删除权限")
            deletion_scope = (row.field_provenance or {}).get("deletion_scope", "library_exit")
            if database.kind == "department_master" and deletion_scope == "library_exit":
                plans.append({"record": row, "patent": patent, "product": None, "updates": {}, "conflicts": [], "operation": "ignore_delete"})
                continue
            if patent is not None and (database.kind == "department_master" or (patent.record_version or 1) > int((row.field_provenance or {}).get("base_version", row.record_version))):
                conflict = {"entity_uid": row.entity_uid, "field_key": "__delete__", "base_value": (row.field_provenance or {}).get("base_version"), "local_value": patent.record_version, "remote_value": "delete"}
                conflicts.append(conflict)
                plans.append({"record": row, "patent": patent, "product": None, "updates": {}, "conflicts": [conflict], "operation": "delete", "confirmed": privileged and database.kind == "department_master"})
                continue
            if patent is not None and (database.kind or "personal") == "department_master" and not privileged:
                raise HTTPException(403, "部门总库中的删除必须由管理员确认")
            plans.append({"record": row, "patent": patent, "product": None, "updates": {}, "conflicts": [], "operation": "delete", "confirmed": privileged and database.kind == "department_master"})
            continue
        if not payload or set(payload) - EXPORT_FIELDS or "title" not in payload:
            raise HTTPException(400, "共享记录包含不支持的字段")
        product_data = ((row.scope_json or {}).get("product") or {})
        product = products_by_code.get(product_data.get("code")) or products_by_name.get(product_data.get("name"))
        source_product = (row.scope_json or {}).get("product")
        if source_product and product is None:
            raise HTTPException(409, "本机找不到同步包中的品类，请先建立相同品类代码或名称")
        target_membership = db.query(DatabaseMembership).filter_by(user_id=user_id, database_id=database.id).first()
        has_target_edit = bool(target_membership and target_membership.role in {"owner", "editor"})
        if package.package_type != "department_publication" and not privileged and not has_target_edit and not _has_matching_apply_grant(apply_grants, product, set(payload)):
            raise HTTPException(403, "没有匹配此数据库、品类和字段范围的主表应用授权，或编辑密码错误")
        patent = local_patents[row.id]
        if not privileged and database.kind == "department_master" and package.package_type != "department_publication":
            raise HTTPException(403, "普通成员不能直接修改部门已发布基线")
        annotations, annotation_conflicts = plan_library_fields(db, package, database, row, patent)
        payload = {key: value for key, value in payload.items() if key not in PRIVATE_FIELDS}
        record_plan = {"record": row, "patent": patent, "product": product, "updates": {}, "conflicts": annotation_conflicts,
            "annotation_plans": annotations}
        conflicts.extend(annotation_conflicts)
        if patent is None:
            record_plan["updates"] = dict(payload)
            plans.append(record_plan)
            continue
        for field_key, remote_value in payload.items():
            baseline = baselines.get((row.entity_uid, field_key))
            exported_at = _source_exported_at(package)
            if baseline and baseline.source_exported_at and exported_at and exported_at < baseline.source_exported_at:
                raise HTTPException(409, "收到早于已接受基线的同步包，请使用来源设备新导出的文件")
            base_value = baseline.last_value if baseline else _NO_BASELINE
            local_value = _local_value(patent, field_key)
            forced = getattr(package, "_aggregation_conflicts", {}).get((row.entity_uid, field_key))
            if forced:
                conflict = {**forced, "local_value": local_value}
                record_plan["conflicts"].append(conflict)
                conflicts.append(conflict)
                continue
            if local_value == remote_value:
                continue
            if base_value is not _NO_BASELINE and local_value == base_value:
                record_plan["updates"][field_key] = remote_value
                continue
            if base_value is not _NO_BASELINE and remote_value == base_value:
                continue
            conflict = {"entity_uid": row.entity_uid, "field_key": field_key,
                        "base_value": None if base_value is _NO_BASELINE else base_value,
                        "local_value": local_value, "remote_value": remote_value}
            record_plan["conflicts"].append(conflict)
            conflicts.append(conflict)
        plans.append(record_plan)
    return plans, conflicts


def preview_apply(db: Session, user_id: int, package_uid: str, request) -> dict:
    try:
        package, database, records = _apply_context(db, user_id, package_uid, request.database_id, getattr(request, "source_database_uid", None))
        plans, conflicts = _merge_plan(db, user_id, package, database, records, request.edit_password)
        return {"package_uid": package_uid, "database_id": database.id,
                "create_count": sum(1 for plan in plans if plan["patent"] is None),
                "update_count": sum(1 for plan in plans if plan["patent"] is not None and plan["updates"]),
                "unchanged_count": sum(1 for plan in plans if plan["patent"] is not None and not plan["updates"] and not plan["conflicts"]),
                "conflicts": conflicts}
    except HTTPException as exc:
        _audit_denial(db, user_id, "package_apply_preview_denied", {"package_uid": package_uid,
                       "status_code": exc.status_code, "reason": str(exc.detail)})
        raise


def _coerce_remote_value(field_key: str, value):
    if field_key == "custom_fields":
        if not isinstance(value, dict):
            raise HTTPException(400, "自定义字段数据格式无效")
        return value
    if field_key in _DATE_FIELDS and value is not None:
        try:
            return date.fromisoformat(value)
        except (TypeError, ValueError) as exc:
            raise HTTPException(400, f"字段 {field_key} 日期格式无效") from exc
    enum_type = _ENUM_FIELDS.get(field_key)
    if enum_type and value is not None:
        try:
            return enum_type(value)
        except ValueError as exc:
            raise HTTPException(400, f"字段 {field_key} 枚举值无效") from exc
    return value


def _source_exported_at(package: SyncPackage) -> datetime | None:
    value = (package.manifest_json or {}).get("created_at")
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if parsed.tzinfo is not None:
            parsed = parsed.astimezone(timezone.utc).replace(tzinfo=None)
        return parsed
    except (ValueError, TypeError, AttributeError):
        raise HTTPException(400, "同步包导出时间格式无效")


def _save_uid_mapping(db: Session, package: SyncPackage, row: SyncPackageRecord, patent: Patent) -> None:
    origin = package.manifest_json["origin_node_uid"]
    mapping = db.query(SyncUidMapping).filter_by(origin_node_uid=origin, remote_uid=row.entity_uid).first()
    if mapping is not None:
        if mapping.patent_id != patent.id:
            raise HTTPException(409, "同步 UID 已关联其他专利，请先人工处理身份冲突")
        return
    db.add(SyncUidMapping(origin_node_uid=origin, remote_uid=row.entity_uid, patent_id=patent.id,
                         package_id=package.id, match_basis="uid" if patent.entity_uid == row.entity_uid else "official_number"))


def _save_remote_changes(db: Session, package: SyncPackage, row: SyncPackageRecord) -> None:
    for change in (row.field_provenance or {}).get("changes", []):
        change_uid = change.get("change_uid")
        if not change_uid or db.query(SyncChange).filter_by(change_uid=change_uid).first():
            continue
        db.add(SyncChange(change_uid=change_uid, package_id=package.id, entity_uid=row.entity_uid,
                          entity_type=row.entity_type, field_key=change.get("field_key"),
                          base_value=change.get("old_value"), remote_value=change.get("new_value"),
                          operation="upsert"))


def patent_edit_states(db: Session, patent_id: int, user_id: int | None = None) -> list[dict]:
    patent = db.get(Patent, patent_id)
    if not patent:
        raise HTTPException(404, "专利不存在")
    result = []
    states = db.query(SyncEntityFieldState).filter_by(entity_uid=patent.entity_uid).all()
    aliases = [row.remote_uid for row in db.query(SyncUidMapping).filter_by(patent_id=patent_id).all()]
    if aliases:
        states.extend(db.query(SyncEntityFieldState).filter(SyncEntityFieldState.entity_uid.in_(aliases)).all())
    for state in states:
        package = db.query(SyncPackage).filter_by(package_uid=state.accepted_package_uid).first()
        overlay = db.query(SyncFieldOverlay).filter_by(entity_uid=patent.entity_uid, field_key=state.field_key).first()
        editor = db.get(User, overlay.editor_user_id) if overlay and overlay.editor_user_id else None
        result.append({"field_key": state.field_key, "baseline_value": state.last_value,
            "local_value": _local_value(patent, state.field_key), "origin_node_uid": state.origin_node_uid,
            "source": (package.manifest_json or {}).get("created_by") if package else None,
            "source_databases": (package.manifest_json or {}).get("databases") if package else [],
            "editor": {"user_uid": editor.user_uid, "name": editor.display_name or editor.username} if editor else None,
            "reason": overlay.reason if overlay else None,
            "state": "department_confirmed" if package and package.package_type == "department_publication" and (not overlay or overlay.status == "confirmed")
                else "self_edit" if overlay and overlay.editor_user_id == user_id else "other_edit",
            "overlay_status": overlay.status if overlay else None})
    return result


def _save_baseline(db: Session, origin_node_uid: str, row: SyncPackageRecord, field_key: str,
                   remote_value, record_version: int, package: SyncPackage | None = None) -> None:
    state = db.query(SyncEntityFieldState).filter_by(
        origin_node_uid=origin_node_uid, entity_uid=row.entity_uid, field_key=field_key,
    ).first()
    if state is None:
        state = SyncEntityFieldState(origin_node_uid=origin_node_uid, entity_uid=row.entity_uid,
                                     field_key=field_key)
        db.add(state)
    state.last_value = remote_value
    state.last_version = record_version
    if package is not None:
        state.accepted_package_uid = package.package_uid
        state.source_exported_at = _source_exported_at(package)
        overlay = db.query(SyncFieldOverlay).filter_by(entity_uid=row.entity_uid, field_key=field_key).first()
        if overlay is not None:
            overlay.baseline_value = remote_value
            if overlay.local_value == remote_value:
                overlay.status = "confirmed" if package.package_type == "department_publication" else "returned"


def _create_apply_backup(db: Session, package_uid: str) -> Path | None:
    """Create a consistent SQLite snapshot before a package can change the master table."""
    bind = db.get_bind()
    database_url = bind.url
    if database_url.get_backend_name() != "sqlite":
        raise RuntimeError("协同主表应用的自动备份目前只支持 SQLite")
    database_name = database_url.database
    if not database_name or database_name == ":memory:" or "mode=memory" in database_name:
        return None
    source_path = Path(database_name)
    if not source_path.exists() or source_path.stat().st_size == 0:
        raise RuntimeError("无法定位本机 SQLite 数据库，已阻止主表应用")
    backup_dir = source_path.parent / "backups" / "collaboration-sync"
    backup_dir.mkdir(parents=True, exist_ok=True)
    stamp = utc_now_naive().strftime("%Y%m%dT%H%M%S%fZ")
    backup_path = backup_dir / f"patwiki-sync-{package_uid}-{stamp}.db"
    try:
        source = sqlite3.connect(str(source_path))
        target = sqlite3.connect(str(backup_path))
        try:
            source.backup(target)
            result = target.execute("PRAGMA integrity_check").fetchone()
            if not result or result[0] != "ok":
                raise RuntimeError("同步前备份完整性校验失败")
        finally:
            target.close()
            source.close()
    except Exception:
        backup_path.unlink(missing_ok=True)
        raise
    return backup_path


_RISK_PROJECTION_FIELDS = {"has_risk", "risk_level", "risk_description"}
_PUBLICATION_FIELDS = EXPORT_FIELDS - {"custom_fields", "notes", "scope_description", "category", "subcategory", "module",
    "technical_problem", "technical_effect", "technical_solution", "has_risk", "risk_level", "risk_description", "application_status"}


def _apply_risk_projection(db: Session, patent: Patent, updates: dict, actor: User | None) -> None:
    """Keep legacy risk projections auditable when a sync package carries them."""
    for field_key in _RISK_PROJECTION_FIELDS.intersection(updates):
        new_value = _coerce_remote_value(field_key, updates[field_key])
        old_value = getattr(patent, field_key)
        if old_value == new_value:
            continue
        setattr(patent, field_key, new_value)
        db.add(PatentHistory(
            patent_id=patent.id,
            field_key=field_key,
            field_display_name=field_key,
            old_value=_stringify_value(old_value),
            new_value=_stringify_value(new_value),
            source="collaboration_sync",
            changed_by=actor.username if actor else None,
        ))


def apply_package(db: Session, user_id: int, package_uid: str, request, *, commit: bool = True) -> dict:
    try:
        privileged = bool(roles(db, user_id) & PRIVILEGED)
        source_database_uid = getattr(request, "source_database_uid", None)
        package, database, records = _apply_context(db, user_id, package_uid, request.database_id, source_database_uid)
        plans, conflicts = _merge_plan(db, user_id, package, database, records, request.edit_password)
        decisions = {(item.entity_uid, item.field_key): item.choice for item in request.decisions}
        decision_details = {(item.entity_uid, item.field_key): item for item in request.decisions}
        if len(decisions) != len(request.decisions):
            raise HTTPException(400, "冲突决策重复")
        conflict_keys = {(item["entity_uid"], item["field_key"]) for item in conflicts}
        if set(decisions) - conflict_keys:
            raise HTTPException(400, "决策包含当前包中不存在的冲突字段")
        origin_node_uid = package.manifest_json["origin_node_uid"]
        by_conflict_key = {(item["entity_uid"], item["field_key"]): item for item in conflicts}
        backup_path = _create_apply_backup(db, package_uid)
        created = updated = unchanged = pending = 0
        actor = db.get(User, user_id)
        for plan in plans:
            row: SyncPackageRecord = plan["record"]
            patent: Patent | None = plan["patent"]
            product: Product | None = plan["product"]
            payload = row.payload_json or {}
            if package.package_type == "department_publication":
                payload = {key: value for key, value in payload.items() if key in _PUBLICATION_FIELDS}
            payload = {key: value for key, value in payload.items() if key not in PRIVATE_FIELDS}
            if plan.get("operation") == "ignore_delete":
                unchanged += 1
                continue
            if plan.get("operation") == "delete":
                if plan.get("conflicts"):
                    conflict = plan["conflicts"][0]
                    key = (conflict["entity_uid"], conflict["field_key"])
                    if decisions.get(key) not in {"local", "remote"}:
                        prior = db.query(SyncConflict).filter_by(package_id=package.id, entity_uid=row.entity_uid, field_key="__delete__").first()
                        if prior is None:
                            db.add(SyncConflict(conflict_uid=uid("conflict"), package_id=package.id,
                                origin_node_uid=origin_node_uid, entity_uid=row.entity_uid, entity_type="patent",
                                field_key="__delete__", base_value=conflict["base_value"], local_value=conflict["local_value"], remote_value="delete"))
                        pending += 1
                        continue
                    audit(db, user_id, "deletion_decided", package_id=package.id,
                        detail={**conflict, "choice": decisions[key], "reason": getattr(decision_details[key], "reason", None)})
                    prior = db.query(SyncConflict).filter_by(package_id=package.id, entity_uid=row.entity_uid, field_key="__delete__").first()
                    if prior:
                        prior.status = "resolved"
                        prior.decision = decisions[key]
                        prior.decided_by = user_id
                        prior.decided_at = utc_now_naive()
                    if decisions[key] == "local":
                        unchanged += 1
                        continue
                if patent is not None:
                    membership = db.query(PatentDatabaseMembership).filter_by(
                        patent_id=patent.id, database_id=database.id).first()
                    if membership is not None:
                        db.delete(membership)
                    elif patent.database_id == database.id:
                        patent.database_id = None
                    if plan.get("confirmed"):
                        remaining = db.query(PatentDatabaseMembership).filter_by(patent_id=patent.id).count()
                        if remaining == 0 and patent.database_id in {database.id, None}:
                            patent.deleted_at = utc_now_naive()
                        db.add(SyncTombstone(entity_uid=patent.entity_uid, entity_type="patent", deleted_by=user_id,
                            base_version=patent.record_version or 1, scope_json={"database_id": database.id, "deletion_scope": "department_delete"}))
                    from app.services.semantic_index_service import SemanticIndexService
                    SemanticIndexService.enqueue_patent(db, patent.id, "collaboration_sync_deleted")
                unchanged += 1
                continue
            if patent is None:
                data = {key: _coerce_remote_value(key, value) for key, value in payload.items()}
                custom_fields = data.pop("custom_fields", {})
                data["title"] = data.get("title")
                patent = Patent(**data, custom_fields=custom_fields, database_id=database.id,
                                product_id=product.id if product else None, entity_uid=row.entity_uid,
                                origin_node_uid=origin_node_uid, record_version=row.record_version)
                db.add(patent)
                db.flush()
                _ensure_database_memberships(db, patent, database)
                for field_key, remote_value in payload.items():
                    if field_key == "custom_fields":
                        for custom_key, custom_value in (remote_value or {}).items():
                            db.add(PatentHistory(
                                patent_id=patent.id, field_key=f"custom_fields.{custom_key}",
                                field_display_name=custom_key, old_value=None,
                                new_value=_stringify_value(custom_value), source="collaboration_sync",
                                changed_by=actor.username if actor else None))
                    else:
                        db.add(PatentHistory(
                            patent_id=patent.id, field_key=field_key, field_display_name=field_key,
                            old_value=None, new_value=_stringify_value(_coerce_remote_value(field_key, remote_value)),
                            source="collaboration_sync", changed_by=actor.username if actor else None))
                ensure_patent_identifiers(db, patent, source_system="collaboration_sync")
                from app.services.formula_service import FormulaService
                FormulaService.recalculate_patent(db, patent, commit=False)
                from app.services.semantic_index_service import SemanticIndexService
                SemanticIndexService.enqueue_patent(db, patent.id, "collaboration_sync_created")
                created += 1
            else:
                updates = dict(plan["updates"])
                for conflict in plan["conflicts"]:
                    key = (conflict["entity_uid"], conflict["field_key"])
                    choice = decisions.get(key)
                    prior = db.query(SyncConflict).filter_by(
                        package_id=package.id, entity_uid=key[0], field_key=key[1],
                    ).first()
                    if choice == "remote" and not key[1].startswith("library:"):
                        updates[key[1]] = conflict["remote_value"]
                    elif choice == "manual" and not key[1].startswith("library:"):
                        updates[key[1]] = decision_details[key].value
                    if choice:
                        if prior is None:
                            prior = SyncConflict(conflict_uid=uid("conflict"), package_id=package.id,
                                                origin_node_uid=origin_node_uid, entity_uid=key[0],
                                                entity_type="patent", field_key=key[1])
                            db.add(prior)
                        prior.base_value = conflict["base_value"]
                        prior.local_value = conflict["local_value"]
                        prior.remote_value = conflict["remote_value"]
                        prior.status = "resolved"
                        prior.decision = choice
                        prior.final_value = updates.get(key[1], conflict["local_value"])
                        prior.decision_reason = getattr(decision_details[key], "reason", None)
                        prior.decided_by = user_id
                        prior.decided_at = utc_now_naive()
                        audit(db, user_id, "conflict_decided", package_id=package.id, detail={
                            "entity_uid": key[0], "field_key": key[1], "base_value": prior.base_value,
                            "local_value": prior.local_value, "remote_value": prior.remote_value,
                            "final_value": prior.final_value, "choice": choice, "reason": prior.decision_reason})
                    elif prior is None:
                        db.add(SyncConflict(conflict_uid=uid("conflict"), package_id=package.id,
                                            origin_node_uid=origin_node_uid, entity_uid=key[0],
                                            entity_type="patent", field_key=key[1],
                                            base_value=conflict["base_value"], local_value=conflict["local_value"],
                                            remote_value=conflict["remote_value"], status="pending"))
                    else:
                        prior.base_value = conflict["base_value"]
                        prior.local_value = conflict["local_value"]
                        prior.remote_value = conflict["remote_value"]
                    if not choice:
                        pending += 1
                if updates:
                    converted = {key: _coerce_remote_value(key, value) for key, value in updates.items()}
                    risk_updates = {key: converted.pop(key) for key in list(converted) if key in _RISK_PROJECTION_FIELDS}
                    if converted:
                        PatentService.update_patent(db, patent, converted, source="collaboration_sync",
                                                    changed_by=actor.username if actor else None, commit=False,
                                                    run_post_update_hooks=False)
                    if risk_updates:
                        _apply_risk_projection(db, patent, risk_updates, actor)
                    if converted or risk_updates:
                        from app.services.semantic_index_service import SemanticIndexService
                        SemanticIndexService.enqueue_patent(db, patent.id, "collaboration_sync_updated")
                    updated += 1
                elif not plan["conflicts"]:
                    unchanged += 1
                _ensure_database_memberships(db, patent, database)
            _save_uid_mapping(db, package, row, patent)
            apply_library_fields(db, package, database, row, patent, plan.get("annotation_plans", []), decisions, decision_details, user_id)
            _save_remote_changes(db, package, row)
            if package.package_type == "department_publication" and patent is not None and plan.get("operation") != "delete":
                # A department publication updates matching personal copies only;
                # it never creates a new personal-library membership.
                personal_updates = {key: value for key, value in payload.items() if key in _PUBLICATION_FIELDS}
                if personal_updates:
                    personal_patents = db.query(Patent).join(PatentDatabaseMembership,
                        PatentDatabaseMembership.patent_id == Patent.id).join(PatentDatabase,
                        PatentDatabaseMembership.database_id == PatentDatabase.id).filter(
                        Patent.entity_uid == row.entity_uid, Patent.id != patent.id,
                        PatentDatabase.kind == "personal", Patent.deleted_at.is_(None)).all()
                    for personal_patent in personal_patents:
                        PatentService.update_patent(db, personal_patent,
                            {key: _coerce_remote_value(key, value) for key, value in personal_updates.items()},
                            source="department_publication", changed_by=actor.username if actor else None,
                            commit=False, run_post_update_hooks=False)
            for field_key, remote_value in payload.items():
                key = (row.entity_uid, field_key)
                if key in by_conflict_key and key not in decisions:
                    continue
                _save_baseline(db, origin_node_uid, row, field_key, remote_value, row.record_version, package)
        package.status = "partially_applied" if pending else "applied"
        package.applied_at = utc_now_naive()
        manifest = dict(package.manifest_json or {})
        if source_database_uid:
            source_results = dict(manifest.get("shared_source_results") or {})
            source_results[source_database_uid] = {"target_database_uid": database.database_uid, "pending_conflicts": pending}
            manifest["shared_source_results"] = source_results
            source_uids = {item["database_uid"] for item in manifest.get("databases", [])}
            if any(source_uid not in source_results or source_results[source_uid]["pending_conflicts"] for source_uid in source_uids):
                package.status = "partially_applied"
        else:
            manifest["applied_target_database_uid"] = database.database_uid
        manifest["last_apply_backup_path"] = str(backup_path) if backup_path else None
        package.manifest_json = manifest
        audit(db, user_id, "package_applied", package_id=package.id,
              detail={"created": created, "updated": updated, "unchanged": unchanged,
                      "pending_conflicts": pending, "database_uid": database.database_uid,
                      "backup_path": str(backup_path) if backup_path else None})
        db.flush()
        database.patent_count = db.query(Patent.id).filter(in_database(database.id), Patent.deleted_at.is_(None)).count()
        if commit:
            db.commit()
        else:
            db.flush()
        return {"package_uid": package_uid, "status": package.status, "created": created,
                "updated": updated, "unchanged": unchanged, "pending_conflicts": pending,
                "conflicts": conflicts, "backup_path": str(backup_path) if backup_path else None}
    except HTTPException as exc:
        if commit:
            _audit_denial(db, user_id, "package_apply_denied", {"package_uid": package_uid,
                           "status_code": exc.status_code, "reason": str(exc.detail)})
        raise
    except Exception:
        db.rollback()
        raise


def _visible_package(db: Session, user_id: int, package_uid: str) -> SyncPackage:
    package = db.query(SyncPackage).filter(SyncPackage.package_uid == package_uid).first()
    if not package or (package.created_by != user_id and not (roles(db, user_id) & PRIVILEGED)):
        raise HTTPException(404, "同步包不存在")
    return package


def shared_package_sources(db: Session, user_id: int, package_uid: str) -> list[dict]:
    package = _visible_package(db, user_id, package_uid)
    return (package.manifest_json or {}).get("databases", [])


def apply_shared_library(db: Session, user_id: int, package_uid: str, request) -> dict:
    package = _visible_package(db, user_id, package_uid)
    if "viewer" in roles(db, user_id):
        raise HTTPException(403, "只读账号不能导入共享库")
    source = next((item for item in (package.manifest_json or {}).get("databases", [])
                   if item.get("database_uid") == request.source_database_uid), None)
    if not source:
        raise HTTPException(400, "来源库不存在")
    database = next((item for item in db.query(PatentDatabase).filter_by(kind="shared", owner_id=user_id).all()
                     if (item.sync_provenance or {}).get("source_database_uid") == request.source_database_uid
                     and (item.sync_provenance or {}).get("origin_node_uid") == package.manifest_json.get("origin_node_uid")), None)
    try:
        if database is None:
            database = PatentDatabase(name=f"共享 · {source.get('name', '来源库')}", kind="shared", owner_id=user_id,
                sync_provenance={"source_database_uid": request.source_database_uid,
                    "origin_node_uid": package.manifest_json.get("origin_node_uid"),
                    "created_by": package.manifest_json.get("created_by"), "imported_at": utc_now_naive().isoformat()})
            db.add(database)
            db.flush()
            db.add(DatabaseMembership(user_id=user_id, database_id=database.id, role="owner"))
            db.flush()
        prior = (package.manifest_json or {}).get("shared_source_results", {}).get(request.source_database_uid)
        if prior and not prior.get("pending_conflicts"):
            return {"database_id": database.id, "status": "already_processed", "package_uid": package_uid}
        apply_request = type("SharedApply", (), {"database_id": database.id, "source_database_uid": request.source_database_uid,
            "edit_password": None, "decisions": request.decisions})()
        result = apply_package(db, user_id, package_uid, apply_request, commit=False)
        database.sync_provenance = {**(database.sync_provenance or {}), "last_package_uid": package_uid,
            "last_imported_at": utc_now_naive().isoformat()}
        db.commit()
        return {**result, "database_id": database.id}
    except Exception:
        db.rollback()
        raise


def apply_department_publication(db: Session, user_id: int, package_uid: str, decisions) -> dict:
    package = _visible_package(db, user_id, package_uid)
    if package.package_type != "department_publication":
        raise HTTPException(400, "请选择部门总库发布文件")
    source = (package.manifest_json or {}).get("databases", [])
    if len(source) != 1:
        raise HTTPException(400, "部门发布文件必须包含一个总库")
    database = next((item for item in db.query(PatentDatabase).filter_by(kind="department_master").all()
        if (item.sync_provenance or {}).get("source_database_uid") == source[0]["database_uid"]), None)
    try:
        if database is None:
            database = PatentDatabase(name="部门总库 · " + source[0].get("name", "总表"), kind="department_master",
                sync_provenance={"source_database_uid": source[0]["database_uid"],
                    "origin_node_uid": package.manifest_json.get("origin_node_uid")})
            db.add(database)
            db.flush()
            db.add(DatabaseMembership(user_id=user_id, database_id=database.id, role="viewer"))
        request = type("PublicationApply", (), {"database_id": database.id, "edit_password": None, "decisions": decisions})()
        result = apply_package(db, user_id, package_uid, request, commit=False)
        db.commit()
        return {**result, "database_id": database.id}
    except Exception:
        db.rollback()
        raise


def list_packages(db: Session, user_id: int) -> list[dict]:
    query = db.query(SyncPackage)
    if not (roles(db, user_id) & PRIVILEGED):
        query = query.filter(SyncPackage.created_by == user_id)
    result = []
    trusted_keys = trusted_device_keys(db)
    for row in query.order_by(SyncPackage.created_at.desc()).limit(100).all():
        manifest = row.manifest_json or {}
        signature_status = row.signature_status
        if signature_status in {"signed", "trusted"} and not package_signer_is_trusted(db, manifest, trusted_keys):
            signature_status = "signed_untrusted"
        result.append({"package_uid": row.package_uid, "direction": row.direction, "status": row.status,
                       "package_type": row.package_type,
                       "file_hash": row.file_hash, "count": manifest.get("count", 0),
                       "path": row.path, "created_at": row.created_at.isoformat() if row.created_at else None,
                       "signature_status": signature_status,
                       "signer_fingerprint": manifest.get("signer_fingerprint")})
    return result


def package_records(db: Session, user_id: int, package_uid: str) -> list[dict]:
    package = _visible_package(db, user_id, package_uid)
    return [{"entity_type": row.entity_type, "entity_uid": row.entity_uid,
             "record_version": row.record_version, "scope": row.scope_json, "payload": row.payload_json,
             "field_provenance": row.field_provenance}
            for row in db.query(SyncPackageRecord).filter(SyncPackageRecord.package_id == package.id).limit(1000).all()]


def _batch_dict(batch: SyncAggregationBatch) -> dict:
    return {"batch_uid": batch.batch_uid, "name": batch.name, "target_database_id": batch.target_database_id,
            "status": batch.status, "package_uids": batch.package_uids or [], "preview": batch.preview_json or {},
            "created_by": batch.created_by, "created_at": batch.created_at.isoformat() if batch.created_at else None,
            "submitted_at": batch.submitted_at.isoformat() if batch.submitted_at else None,
            "publication_package_uid": batch.publication_package_uid}


def create_aggregation_batch(db: Session, user_id: int, name: str, target_database_id: int,
                             package_uids: list[str]) -> dict:
    if not roles(db, user_id) & PRIVILEGED:
        raise HTTPException(403, "只有部门管理员可以创建汇总批次")
    database = db.get(PatentDatabase, target_database_id)
    if not database or database.is_archived or (database.kind or "personal") != "department_master":
        raise HTTPException(404, "目标部门总库不存在或已归档")
    package_uids = list(dict.fromkeys(package_uids))
    packages = db.query(SyncPackage).filter(SyncPackage.package_uid.in_(package_uids)).all() if package_uids else []
    if len(packages) != len(package_uids):
        raise HTTPException(404, "部分同步包不存在")
    if any(package.direction != "inbox" for package in packages):
        raise HTTPException(400, "汇总批次只能收集已导入的成员同步包")
    batch = SyncAggregationBatch(batch_uid=uid("agg"), name=name.strip(), target_database_id=database.id,
                                 package_uids=package_uids, created_by=user_id)
    db.add(batch)
    db.commit()
    db.refresh(batch)
    return _batch_dict(batch)


def preview_aggregation_batch(db: Session, user_id: int, batch_uid: str) -> dict:
    if not roles(db, user_id) & PRIVILEGED:
        raise HTTPException(403, "只有部门管理员可以预审汇总批次")
    batch = db.query(SyncAggregationBatch).filter_by(batch_uid=batch_uid).first()
    if not batch:
        raise HTTPException(404, "汇总批次不存在")
    database = db.get(PatentDatabase, batch.target_database_id)
    summary = {"auto_merge": 0, "new": 0, "deleted": 0, "conflict": 0, "unmatched": 0, "unchanged": 0, "packages": [], "conflicts": []}
    concurrent = _concurrent_batch_conflicts(db, batch)
    for package_uid in batch.package_uids or []:
        package = db.query(SyncPackage).filter_by(package_uid=package_uid).first()
        if not package:
            continue
        records = db.query(SyncPackageRecord).filter_by(package_id=package.id).order_by(SyncPackageRecord.id).all()
        try:
            plans, conflicts = _merge_plan(db, user_id, package, database, records, None)
            known = {(item["entity_uid"], item["field_key"]) for item in conflicts}
            conflicts.extend(item for item in concurrent.get(package_uid, {}).values()
                if (item["entity_uid"], item["field_key"]) not in known)
            summary["conflicts"].extend({**item, "package_uid": package_uid} for item in conflicts)
            counts = {"auto_merge": sum(1 for item in plans if item["patent"] is not None and item["updates"] and not item["conflicts"]),
                      "new": sum(1 for item in plans if item["patent"] is None and item.get("operation") != "delete"), "conflict": len(conflicts),
                      "unchanged": sum(1 for item in plans if item["patent"] is not None and not item["updates"] and not item["conflicts"]),
                      "deleted": sum(1 for item in plans if item.get("operation") == "delete"), "unmatched": 0}
        except HTTPException as exc:
            counts = {"auto_merge": 0, "new": 0, "deleted": 0, "conflict": 0, "unchanged": 0,
                      "unmatched": len(records), "error": str(exc.detail)}
        for key in ("auto_merge", "new", "deleted", "conflict", "unchanged", "unmatched"):
            summary[key] += counts.get(key, 0)
        summary["packages"].append({"package_uid": package_uid, "count": len(records), **counts})
    batch.preview_json = summary
    db.commit()
    return _batch_dict(batch)


def _concurrent_batch_conflicts(db: Session, batch: SyncAggregationBatch) -> dict:
    candidates = {}
    for package in db.query(SyncPackage).filter(SyncPackage.package_uid.in_(batch.package_uids or []), SyncPackage.status != "applied").all():
        rows = db.query(SyncPackageRecord).filter_by(package_id=package.id, entity_type="patent").all()
        resolved = _batch_local_patents(db, rows, package.manifest_json.get("origin_node_uid"))
        for row in rows:
            patent = resolved[row.id]
            for field, value in (row.payload_json or {}).items():
                baseline = db.query(SyncEntityFieldState).filter_by(origin_node_uid=package.manifest_json.get("origin_node_uid"),
                    entity_uid=row.entity_uid, field_key=field).first()
                local = _local_value(patent, field) if patent else None
                if (baseline and baseline.last_value == value) or (not baseline and value == local):
                    continue
                key = (patent.id if patent else row.entity_uid, field)
                candidates.setdefault(key, []).append((package.package_uid, {"entity_uid": row.entity_uid,
                    "field_key": field, "base_value": baseline.last_value if baseline else None,
                    "local_value": local, "remote_value": value}))
    result = {}
    for items in candidates.values():
        values = [item[1]["remote_value"] for item in items]
        if len({item[0] for item in items}) > 1 and any(value != values[0] for value in values[1:]):
            for package_uid, conflict in items:
                result.setdefault(package_uid, {})[(conflict["entity_uid"], conflict["field_key"])] = conflict
    return result


def submit_aggregation_batch(db: Session, user_id: int, batch_uid: str, request) -> dict:
    if not roles(db, user_id) & PRIVILEGED:
        raise HTTPException(403, "只有部门管理员可以提交汇总批次")
    batch = db.query(SyncAggregationBatch).filter_by(batch_uid=batch_uid).first()
    if not batch:
        raise HTTPException(404, "汇总批次不存在")
    if batch.status == "published" or (batch.status == "submitted" and not request.decisions):
        return _batch_dict(batch)
    database = db.get(PatentDatabase, batch.target_database_id)
    results = []
    concurrent = _concurrent_batch_conflicts(db, batch)
    try:
        for package_uid in batch.package_uids or []:
            package = db.query(SyncPackage).filter_by(package_uid=package_uid).first()
            if not package:
                raise HTTPException(404, "汇总批次中的同步包不存在")
            if package.status == "applied":
                continue
            records = db.query(SyncPackageRecord).filter_by(package_id=package.id).all()
            package._aggregation_conflicts = concurrent.get(package_uid, {})
            _, conflicts = _merge_plan(db, user_id, package, database, records, request.edit_password)
            conflict_keys = {(item["entity_uid"], item["field_key"]) for item in conflicts}
            apply_request = type("BatchApplyRequest", (), {"database_id": database.id, "edit_password": request.edit_password,
                "decisions": [item for item in request.decisions if (item.entity_uid, item.field_key) in conflict_keys
                    and getattr(item, "package_uid", None) in {None, package_uid}]})()
            results.append(apply_package(db, user_id, package_uid, apply_request, commit=False))
            del package._aggregation_conflicts
        batch.status = "submitted"
        batch.submitted_at = utc_now_naive()
        batch.preview_json = {**(batch.preview_json or {}), "submit_results": results}
        db.commit()
    except Exception:
        db.rollback()
        raise
    return _batch_dict(batch)


def publish_aggregation_batch(db: Session, user_id: int, batch_uid: str, request) -> dict:
    if not roles(db, user_id) & PRIVILEGED:
        raise HTTPException(403, "只有部门管理员可以发布部门总库")
    batch = db.query(SyncAggregationBatch).filter_by(batch_uid=batch_uid).first()
    if not batch or batch.status != "submitted":
        raise HTTPException(409, "汇总批次尚未提交，不能发布")
    if batch.publication_package_uid:
        return _batch_dict(batch)
    export_request = type("PublicationRequest", (), {
        "database_ids": [batch.target_database_id], "patent_ids": None, "product_ids": None,
        "fields": [field for field in request.fields if field in _PUBLICATION_FIELDS], "recipient_names": request.recipient_names,
        "include_attachments": False, "password": request.password, "expires_days": request.expires_days,
        "package_type": "department_publication",
        "external_update_results": (batch.preview_json or {}).get("external_update_results", {}),
    })()
    result = export_package(db, user_id, export_request)
    batch.publication_package_uid = result["package_uid"]
    batch.status = "published"
    db.commit()
    return {**_batch_dict(batch), "publication": result}


def export_path(db: Session, user_id: int, package_uid: str) -> Path:
    package = _visible_package(db, user_id, package_uid)
    if package.direction != "outbox":
        raise HTTPException(404, "导出文件不存在")
    path = workspace_dir() / "outbox" / f"{package_uid}.pwshare"
    if not path.is_file() or path.resolve() != Path(package.path).resolve():
        raise HTTPException(404, "导出文件不存在")
    return path
