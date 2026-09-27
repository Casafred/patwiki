"""Offline, read-only patent snapshot export and import."""
from __future__ import annotations

import os
from datetime import datetime, timedelta
from pathlib import Path
from uuid import uuid4

from fastapi import HTTPException, UploadFile
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.core.time import utc_now_naive
from app.models import Patent, PatentDatabase, PatentDatabaseMembership, Product, User
from app.models.collaboration_sync import CollaborationCredential, PermissionGrant, SyncPackage, SyncPackageMember, SyncPackageRecord, SyncWorkspace
from app.services.collaboration_identity_service import audit, roles, uid, workspace_dir
from app.services.collaboration_package_codec import MAX_BYTES, MAX_RECORDS, decode, encode, file_hash

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


def _validate_request(db: Session, user_id: int, request):
    fields = list(dict.fromkeys(request.fields))
    if not fields or "title" not in fields or set(fields) - EXPORT_FIELDS:
        raise HTTPException(400, "字段范围无效，必须包含标题且只能选择首期支持的字段")
    if request.include_attachments:
        raise HTTPException(400, "首期同步包暂不支持附件")
    recipients = list(dict.fromkeys(name.lower() for name in request.recipient_names))
    if not recipients or any(not name or len(name) > 100 for name in recipients):
        raise HTTPException(400, "必须指定有效接收账号")
    known_recipients = {row[0].lower() for row in db.query(CollaborationCredential.login_name).join(
        User, User.id == CollaborationCredential.user_id
    ).filter(CollaborationCredential.active.is_(True), User.is_active.is_(True)).all()}
    if not set(recipients).issubset(known_recipients):
        raise HTTPException(400, "接收人必须先开通有效的协同账号")
    databases = db.query(PatentDatabase).filter(PatentDatabase.id.in_(request.database_ids), PatentDatabase.is_archived.is_(False)).all()
    if len(databases) != len(set(request.database_ids)):
        raise HTTPException(404, "所选数据库不存在或已归档")
    privileged = bool(roles(db, user_id) & PRIVILEGED)
    if not privileged:
        now = utc_now_naive()
        grants = db.query(PermissionGrant).filter(
            PermissionGrant.subject_user_id == user_id,
            PermissionGrant.scope_type == "database",
            PermissionGrant.revoked_at.is_(None),
            or_(PermissionGrant.expires_at.is_(None), PermissionGrant.expires_at > now),
        ).all()
        for database in databases:
            matching = [grant for grant in grants if grant.scope_uid == database.database_uid and
                        "export" in (grant.actions or []) and set(fields).issubset(set(grant.field_scope or [])) and
                        (not request.product_ids or not (grant.scope_json or {}).get("product_ids") or
                         set(request.product_ids).issubset(set(grant.scope_json["product_ids"]))) and
                        (request.product_ids is not None or not (grant.scope_json or {}).get("product_ids"))]
            if not matching:
                raise HTTPException(403, f"没有数据库 {database.name} 的协同导出授权")
    return fields, recipients, databases


def _query(db: Session, request):
    query = db.query(Patent).filter(Patent.deleted_at.is_(None)).filter(or_(
        Patent.database_id.in_(request.database_ids),
        Patent.id.in_(db.query(PatentDatabaseMembership.patent_id).filter(
            PatentDatabaseMembership.database_id.in_(request.database_ids)
        )),
    ))
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


def _records(db: Session, user_id: int, request, fields: list[str], databases: list[PatentDatabase], node_uid: str):
    query = _query(db, request)
    count = query.count()
    if count > MAX_RECORDS:
        raise HTTPException(413, "单个同步包最多 20000 条记录，请缩小范围")
    patents = query.all()
    database_uids = {item.id: item.database_uid for item in databases}
    privileged = bool(roles(db, user_id) & PRIVILEGED)
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
    product_ids = {patent.product_id for patent in patents if patent.product_id}
    products = {item.id: item for item in db.query(Product).filter(Product.id.in_(product_ids)).all()} if product_ids else {}
    records = []
    for patent in patents:
        _assert_record_scope(patent, request, fields, privileged, memberships_by_patent.get(patent.id, set()),
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
        records.append({"entity_type": "patent", "entity_uid": patent.entity_uid,
                        "record_version": patent.record_version or 1,
                        "origin_node_uid": patent.origin_node_uid,
                        "updated_at": _value(patent.updated_at),
                        "scope": {"database_uids": sorted(scopes),
                                  "product": {"code": product.code, "name": product.name} if product else None},
                        "payload": payload, "field_provenance": {}})
    return records


def preview_export(db: Session, user_id: int, request) -> dict:
    try:
        fields, recipients, databases = _validate_request(db, user_id, request)
        records = _records(db, user_id, request, fields, databases, "node_" + "0" * 32)
        return {"count": len(records), "fields": fields, "recipients": recipients}
    except HTTPException as exc:
        _audit_denial(db, user_id, "package_export_denied", {"database_ids": request.database_ids,
                       "status_code": exc.status_code, "reason": str(exc.detail)})
        raise


def export_package(db: Session, user_id: int, request) -> dict:
    try:
        fields, recipients, databases = _validate_request(db, user_id, request)
        workspace = _workspace(db, user_id)
        records = _records(db, user_id, request, fields, databases, workspace.node_uid)
    except HTTPException as exc:
        _audit_denial(db, user_id, "package_export_denied", {"database_ids": request.database_ids,
                       "status_code": exc.status_code, "reason": str(exc.detail)})
        raise
    now = utc_now_naive()
    package_uid = uid("pkg")
    user = db.get(User, user_id)
    manifest = {"package_id": package_uid, "profile": "patent-snapshot-v1", "package_type": "snapshot",
                "created_at": now.isoformat(), "expires_at": (now + timedelta(days=request.expires_days)).isoformat(),
                "created_by": {"user_uid": user.user_uid, "username": user.username},
                "origin_node_uid": workspace.node_uid, "fields": fields, "count": len(records),
                "databases": [{"database_uid": item.database_uid, "name": item.name} for item in databases],
                "signature_status": "not_signed"}
    permissions = {"access": "viewer", "recipients": recipients, "fields": fields,
                   "can_edit": False, "can_redistribute": False}
    raw = encode(manifest, permissions, records, request.password)
    path = workspace_dir() / "outbox" / f"{package_uid}.pwshare"
    with path.open("xb") as stream:
        stream.write(raw)
    package = SyncPackage(package_uid=package_uid, package_type="snapshot", direction="outbox",
                          path=str(path), file_hash=file_hash(raw), created_by=user_id,
                          status="created", access="viewer", manifest_json=manifest,
                          expires_at=now + timedelta(days=request.expires_days))
    db.add(package)
    db.flush()
    recipient_rows = db.query(CollaborationCredential.login_name, CollaborationCredential.user_id).filter(
        CollaborationCredential.active.is_(True), CollaborationCredential.login_name.in_(recipients)
    ).all()
    recipient_ids = {name.lower(): user_id for name, user_id in recipient_rows}
    for recipient in recipients:
        db.add(SyncPackageMember(package_id=package.id, user_id=recipient_ids[recipient],
                                 subject_label=recipient, access="viewer", field_scope=fields))
    audit(db, user_id, "package_exported", package_id=package.id, detail={"count": len(records)})
    try:
        db.commit()
    except Exception:
        db.rollback()
        path.unlink(missing_ok=True)
        raise
    return {"package_uid": package_uid, "path": str(path), "file_hash": package.file_hash,
            "count": len(records), "expires_at": manifest["expires_at"]}


async def read_upload(upload: UploadFile) -> bytes:
    raw = await upload.read(MAX_BYTES + 1)
    if len(raw) > MAX_BYTES:
        raise HTTPException(413, "同步包超过 100MB")
    return raw


def _validated_import(db: Session, user_id: int, raw: bytes, password: str):
    try:
        manifest, permissions, records = decode(raw, password)
        if datetime.fromisoformat(manifest["expires_at"]) <= utc_now_naive():
            raise HTTPException(410, "同步包已过期")
        user = db.get(User, user_id)
        if user.username.lower() not in permissions["recipients"] and not (roles(db, user_id) & PRIVILEGED):
            raise HTTPException(403, "当前账号不是此包的接收人")
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
    if db.query(SyncPackage).filter(SyncPackage.package_uid == package_uid).first():
        _audit_denial(db, user_id, "package_import_denied", {"package_uid": package_uid, "reason": "duplicate package UID"})
        raise HTTPException(409, "同步包已经导入或由本机导出")
    if db.query(SyncPackage).filter(SyncPackage.file_hash == file_hash(raw), SyncPackage.direction == "inbox").first():
        _audit_denial(db, user_id, "package_import_denied", {"file_hash": file_hash(raw), "reason": "duplicate package hash"})
        raise HTTPException(409, "该同步文件已经导入")
    path = workspace_dir() / "inbox" / f"{package_uid}.pwshare"
    with path.open("xb") as stream:
        stream.write(raw)
    package = SyncPackage(package_uid=package_uid, package_type="snapshot", direction="inbox",
                          path=str(path), file_hash=file_hash(raw), created_by=user_id,
                          status="imported", access="viewer", manifest_json=manifest,
                          signature_status="not_signed", applied_at=utc_now_naive(),
                          expires_at=datetime.fromisoformat(manifest["expires_at"]))
    db.add(package)
    db.flush()
    db.add(SyncPackageMember(package_id=package.id, user_id=user_id, subject_label=db.get(User, user_id).username,
                             access="viewer", field_scope=permissions["fields"]))
    for record in records:
        db.add(SyncPackageRecord(package_id=package.id, entity_type="patent", entity_uid=record["entity_uid"],
                                 record_version=record["record_version"], scope_json=record["scope"],
                                 payload_json=record["payload"], field_provenance=record["field_provenance"]))
    audit(db, user_id, "package_imported", package_id=package.id, detail={"count": len(records)})
    try:
        db.commit()
    except Exception:
        db.rollback()
        path.unlink(missing_ok=True)
        raise
    return {"package_uid": package_uid, "count": len(records), "status": "imported"}


def _visible_package(db: Session, user_id: int, package_uid: str) -> SyncPackage:
    package = db.query(SyncPackage).filter(SyncPackage.package_uid == package_uid).first()
    if not package or (package.created_by != user_id and not (roles(db, user_id) & PRIVILEGED)):
        raise HTTPException(404, "同步包不存在")
    return package


def list_packages(db: Session, user_id: int) -> list[dict]:
    query = db.query(SyncPackage)
    if not (roles(db, user_id) & PRIVILEGED):
        query = query.filter(SyncPackage.created_by == user_id)
    return [{"package_uid": row.package_uid, "direction": row.direction, "status": row.status,
             "file_hash": row.file_hash, "count": (row.manifest_json or {}).get("count", 0),
             "path": row.path, "created_at": row.created_at.isoformat() if row.created_at else None}
            for row in query.order_by(SyncPackage.created_at.desc()).limit(100).all()]


def package_records(db: Session, user_id: int, package_uid: str) -> list[dict]:
    package = _visible_package(db, user_id, package_uid)
    return [{"entity_type": row.entity_type, "entity_uid": row.entity_uid,
             "record_version": row.record_version, "scope": row.scope_json, "payload": row.payload_json,
             "field_provenance": row.field_provenance}
            for row in db.query(SyncPackageRecord).filter(SyncPackageRecord.package_id == package.id).limit(1000).all()]


def export_path(db: Session, user_id: int, package_uid: str) -> Path:
    package = _visible_package(db, user_id, package_uid)
    if package.direction != "outbox":
        raise HTTPException(404, "导出文件不存在")
    path = workspace_dir() / "outbox" / f"{package_uid}.pwshare"
    if not path.is_file() or path.resolve() != Path(package.path).resolve():
        raise HTTPException(404, "导出文件不存在")
    return path
