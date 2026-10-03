"""Authenticated department collaboration and offline sync package API."""
from __future__ import annotations

import hashlib
import base64
import json
from datetime import timedelta

from fastapi import APIRouter, Depends, File, Form, Header, HTTPException, UploadFile
from fastapi.responses import FileResponse, JSONResponse
from argon2.exceptions import VerificationError
from app.core.time import utc_now_naive
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import User
from app.models import PatentDatabase, Product
from app.models.collaboration_sync import (
    CollaborationCredential, CollaborationEdge, CollaborationSession, OrganizationUnit, PermissionGrant,
    SyncPackage, TrustedSyncDevice, SyncWorkspace, UserResponsibility, UserRoleAssignment,
)
from app.schemas.collaboration_sync import (
    AccountRequest, AccountRoleRequest, BootstrapRequest, ExportRequest, LibraryGrantRequest, PeerRequest,
    SharedLibraryApplyRequest,
    SharingPreferenceRequest, AggregationUpdateRequest, AggregationUpdateConfirmRequest,
    DepartmentPublicationApplyRequest,
    LibraryFieldEditRequest,
    ActiveRequest, AggregationBatchCreateRequest, AggregationPublishRequest, AggregationBatchSubmitRequest, ApplyPackageRequest, LoginRequest, PasswordRequest, ProvisioningRequest, ResponsibilityRequest, UnitRequest,
)
from app.services.collaboration_identity_service import (
    PASSWORDS, audit, bootstrap, create_account, identity, login, logout, require_admin, roles,
    session_user, setup_status, uid,
)
from app.services.collaboration_sync_service import (
    export_package, import_package, inspect_package, list_packages,
    export_path, package_records, preview_export, read_upload, EXPORT_FIELDS,
    device_signing_identity,
    create_aggregation_batch, preview_aggregation_batch, submit_aggregation_batch,
    publish_aggregation_batch,
    process_package_stream,
    shared_package_sources, apply_shared_library,
)

router = APIRouter(prefix="/collaboration-sync", tags=["collaboration-sync"])


@router.post("/employee-config/import")
async def import_employee_config(file: UploadFile = File(...), db: Session = Depends(get_db)):
    from app.services.collaboration_enrollment_service import import_enrollment
    return import_enrollment(db, await file.read(64 * 1024 + 1))



def current_user(
    authorization: str | None = Header(default=None),
    db: Session = Depends(get_db),
) -> User:
    return session_user(db, authorization)


@router.get("/setup-status")
def get_setup_status(db: Session = Depends(get_db)):
    return setup_status(db)


@router.post("/bootstrap")
def bootstrap_system(request: BootstrapRequest, db: Session = Depends(get_db)):
    return bootstrap(db, request)


@router.post("/login")
def login_system(request: LoginRequest, db: Session = Depends(get_db)):
    return login(db, request.username, request.password)


@router.post("/logout")
def logout_system(authorization: str | None = Header(default=None), user: User = Depends(current_user), db: Session = Depends(get_db)):
    logout(db, user.id, authorization)
    return {"success": True}


@router.get("/identity/me")
def get_identity(user: User = Depends(current_user), db: Session = Depends(get_db)):
    return identity(db, user)


@router.patch("/identity/password")
def change_own_password(
    request: PasswordRequest,
    authorization: str | None = Header(default=None),
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    credential = db.get(CollaborationCredential, user.id)
    try:
        valid = bool(credential and PASSWORDS.verify(credential.password_hash, request.current_password))
    except VerificationError:
        valid = False
    if not valid or not authorization or not authorization.startswith("Bearer "):
        audit(db, user.id, "password_changed", result="denied")
        db.commit()
        raise HTTPException(403, "当前密码错误")
    current_session_hash = hashlib.sha256(authorization[7:].encode()).hexdigest()
    credential.password_hash = PASSWORDS.hash(request.new_password)
    db.query(CollaborationSession).filter(
        CollaborationSession.user_id == user.id,
        CollaborationSession.token_hash != current_session_hash,
    ).delete(synchronize_session=False)
    audit(db, user.id, "password_changed")
    db.commit()
    return {"success": True, "other_sessions_revoked": True}


@router.get("/devices/identity")
def get_device_identity(user: User = Depends(current_user), db: Session = Depends(get_db)):
    require_admin(db, user.id)
    result = device_signing_identity(db, user.id)
    db.commit()
    result.pop("private_key", None)
    return result


@router.get("/devices/trusted")
def list_trusted_devices(user: User = Depends(current_user), db: Session = Depends(get_db)):
    require_admin(db, user.id)
    return {"items": [{"fingerprint": row.fingerprint, "name": row.name,
                        "public_key": row.public_key, "revoked": row.revoked_at is not None,
                        "created_at": row.created_at.isoformat() if row.created_at else None}
                       for row in db.query(TrustedSyncDevice).order_by(TrustedSyncDevice.created_at).all()]}


@router.post("/devices/trusted")
def trust_device(request: PeerRequest, user: User = Depends(current_user), db: Session = Depends(get_db)):
    require_admin(db, user.id)
    if not request.name.strip():
        raise HTTPException(400, "设备名称不能为空")
    try:
        public_key = base64.b64decode(request.public_key, validate=True)
    except (ValueError, TypeError) as exc:
        raise HTTPException(400, "设备公钥必须是 Base64 编码的 Ed25519 公钥") from exc
    if len(public_key) != 32:
        raise HTTPException(400, "Ed25519 设备公钥长度无效")
    fingerprint = hashlib.sha256(public_key).hexdigest()
    own = db.query(SyncWorkspace).first()
    if own and own.public_key:
        try:
            own_key = base64.b64decode(own.public_key, validate=True)
        except (ValueError, TypeError):
            own_key = b""
        if own_key == public_key:
            raise HTTPException(400, "无需登记本机自己的设备密钥")
    record = db.get(TrustedSyncDevice, fingerprint)
    if record and record.public_key != request.public_key:
        raise HTTPException(409, "设备指纹已存在但公钥不一致")
    if record is None:
        record = TrustedSyncDevice(fingerprint=fingerprint, name=request.name.strip(), public_key=request.public_key)
        db.add(record)
    else:
        record.name = request.name.strip()
        record.revoked_at = None
    audit(db, user.id, "sync_device_trusted", detail={"fingerprint": fingerprint, "name": record.name})
    db.commit()
    return {"fingerprint": fingerprint, "name": record.name, "public_key": record.public_key, "revoked": False}


@router.delete("/devices/trusted/{fingerprint}")
def revoke_trusted_device(fingerprint: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    require_admin(db, user.id)
    record = db.get(TrustedSyncDevice, fingerprint)
    if not record:
        raise HTTPException(404, "可信设备不存在")
    if record.revoked_at is None:
        record.revoked_at = utc_now_naive()
        audit(db, user.id, "sync_device_revoked", detail={"fingerprint": fingerprint})
        db.commit()
    return {"fingerprint": fingerprint, "revoked": True}


@router.post("/accounts")
def add_account(request: AccountRequest, user: User = Depends(current_user), db: Session = Depends(get_db)):
    require_admin(db, user.id)
    created = create_account(db, request, user.id, request.role)
    created.employee_no = request.employee_no
    db.commit()
    return identity(db, created)


@router.get("/accounts/{target_user_id}/employee-config")
def export_employee_config(target_user_id: int, department_code: str,
                           user: User = Depends(current_user), db: Session = Depends(get_db)):
    require_admin(db, user.id)
    if not department_code.strip() or len(department_code) > 80:
        raise HTTPException(400, "部门标识无效")
    from app.services.collaboration_enrollment_service import export_enrollment
    key = device_signing_identity(db, user.id)["private_key"]
    document = export_enrollment(db, user.id, target_user_id, department_code.strip(), key)
    db.commit()
    return JSONResponse(document, headers={"Content-Disposition": "attachment; filename=patwiki-employee-config.json"})


@router.post("/accounts/provision")
def provision_accounts(request: ProvisioningRequest, user: User = Depends(current_user), db: Session = Depends(get_db)):
    require_admin(db, user.id)
    usernames = [item.username.lower() for item in request.accounts]
    if len(set(usernames)) != len(usernames):
        raise HTTPException(400, "配置文件中的账号重复")
    created = []
    try:
        for item in request.accounts:
            account = create_account(db, item, user.id, item.role)
            account.employee_no = item.employee_no
            created.append({"username": account.username, "display_name": account.display_name,
                            "employee_no": account.employee_no, "role": item.role})
        audit(db, user.id, "accounts_provisioned", detail={"department_code": request.department_code,
              "count": len(created)})
        db.commit()
    except Exception:
        db.rollback()
        raise
    return {"department_code": request.department_code, "accounts": created}


@router.get("/accounts/provision/template")
def provision_template(user: User = Depends(current_user), db: Session = Depends(get_db)):
    require_admin(db, user.id)
    payload = {"department_code": "DEPARTMENT_CODE", "accounts": [{
        "username": "employee.login", "display_name": "员工姓名", "employee_no": "EMP001",
        "role": "member", "password": "",
    }]}
    return JSONResponse(content=payload, headers={"Content-Disposition": "attachment; filename=patwiki-account-provision-template.json"})


@router.post("/accounts/provision/file")
async def provision_file(file: UploadFile = File(...), user: User = Depends(current_user), db: Session = Depends(get_db)):
    require_admin(db, user.id)
    if not (file.filename or "").lower().endswith(".json"):
        raise HTTPException(400, "账号配置文件必须是 JSON")
    raw = await file.read(1024 * 1024 + 1)
    if len(raw) > 1024 * 1024:
        raise HTTPException(413, "账号配置文件过大")
    try:
        request = ProvisioningRequest.model_validate(json.loads(raw.decode("utf-8")))
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
        raise HTTPException(400, "账号配置文件格式无效，且必须为 UTF-8 JSON") from exc
    # Passwords are accepted only for this transaction and are never returned
    # in the response or persisted outside the credential hash.
    return provision_accounts(request, user, db)


@router.get("/accounts")
def list_accounts(user: User = Depends(current_user), db: Session = Depends(get_db)):
    require_admin(db, user.id)
    rows = db.query(CollaborationCredential, User).join(User, User.id == CollaborationCredential.user_id).order_by(User.username).all()
    items = [{**identity(db, account), "role_assignments": [
        {"role": assignment.role_code, "unit_id": assignment.unit_id}
        for assignment in db.query(UserRoleAssignment).filter(
            UserRoleAssignment.user_id == account.id, UserRoleAssignment.valid_to.is_(None),
        ).all()
    ]} for _, account in rows]
    return {"items": items}


@router.patch("/accounts/{target_user_id}/active")
def set_account_active(target_user_id: int, request: ActiveRequest, user: User = Depends(current_user), db: Session = Depends(get_db)):
    require_admin(db, user.id)
    credential = db.get(CollaborationCredential, target_user_id)
    if not credential:
        raise HTTPException(404, "协同账号不存在")
    if not request.active:
        active_admin_ids = {row[0] for row in db.query(UserRoleAssignment.user_id).join(
            User, User.id == UserRoleAssignment.user_id
        ).join(CollaborationCredential, CollaborationCredential.user_id == User.id).filter(
            UserRoleAssignment.role_code.in_(["system_admin", "department_leader"]),
            UserRoleAssignment.valid_to.is_(None),
            User.is_active.is_(True), CollaborationCredential.active.is_(True),
        ).distinct().all()}
        if target_user_id in active_admin_ids and len(active_admin_ids) <= 1:
            raise HTTPException(409, "不能停用唯一的协同管理员")
        db.query(CollaborationSession).filter_by(user_id=target_user_id).delete()
    credential.active = request.active
    from app.services.collaboration_identity_service import audit
    audit(db, user.id, "account_status_changed", detail={"target_user_id": target_user_id, "active": request.active})
    db.commit()
    return {"user_id": target_user_id, "active": credential.active}


@router.patch("/accounts/{target_user_id}/role")
def set_account_role(target_user_id: int, request: AccountRoleRequest, user: User = Depends(current_user), db: Session = Depends(get_db)):
    require_admin(db, user.id)
    target = db.get(User, target_user_id)
    credential = db.get(CollaborationCredential, target_user_id)
    if not target or not credential or not credential.active or not target.is_active:
        raise HTTPException(404, "协同账号不存在或已停用")
    unit = db.get(OrganizationUnit, request.unit_id) if request.unit_id else None
    if request.unit_id and (not unit or not unit.active):
        raise HTTPException(404, "组织小组不存在或已停用")
    if request.role == "group_leader" and (not unit or unit.unit_type != "team"):
        raise HTTPException(400, "组长角色必须指定一个有效小组")
    active = db.query(UserRoleAssignment).filter_by(user_id=target_user_id, valid_to=None).all()
    if any(item.role_code in {"system_admin", "department_leader"} for item in active) and request.role not in {"system_admin", "department_leader"}:
        active_admin_ids = {row[0] for row in db.query(UserRoleAssignment.user_id).join(
            User, User.id == UserRoleAssignment.user_id
        ).join(CollaborationCredential, CollaborationCredential.user_id == User.id).filter(
            UserRoleAssignment.role_code.in_(["system_admin", "department_leader"]),
            UserRoleAssignment.valid_to.is_(None), User.is_active.is_(True),
            CollaborationCredential.active.is_(True),
        ).distinct().all()}
        if target_user_id in active_admin_ids and len(active_admin_ids) <= 1:
            raise HTTPException(409, "不能移除唯一的协同管理员角色")
    for assignment in active:
        assignment.valid_to = utc_now_naive()
    replacement = UserRoleAssignment(user_id=target_user_id, role_code=request.role, unit_id=unit.id if unit else None,
                                    valid_from=utc_now_naive(), assigned_by=user.id)
    db.add(replacement)
    from app.services.collaboration_identity_service import audit
    audit(db, user.id, "account_role_changed", detail={"target_user_id": target_user_id,
          "role": request.role, "unit_id": request.unit_id})
    db.commit()
    return identity(db, target)


@router.get("/organization/units")
def list_units(user: User = Depends(current_user), db: Session = Depends(get_db)):
    return [{"id": unit.id, "unit_uid": unit.unit_uid, "name": unit.name, "unit_type": unit.unit_type,
             "team_type": unit.team_type, "parent_id": unit.parent_id, "active": unit.active}
            for unit in db.query(OrganizationUnit).order_by(OrganizationUnit.id).all()]


@router.post("/organization/units")
def add_unit(request: UnitRequest, user: User = Depends(current_user), db: Session = Depends(get_db)):
    require_admin(db, user.id)
    parent = db.get(OrganizationUnit, request.parent_id) if request.parent_id else db.query(OrganizationUnit).filter_by(unit_type="department", active=True).first()
    if not parent or parent.unit_type != "department" or not parent.active:
        raise HTTPException(400, "小组必须隶属一个有效部门")
    unit = OrganizationUnit(unit_uid=uid("unit"), name=request.name, unit_type="team",
                            team_type=request.team_type, parent_id=parent.id)
    db.add(unit)
    from app.services.collaboration_identity_service import audit
    audit(db, user.id, "organization_unit_created", detail={"unit_uid": unit.unit_uid, "team_type": unit.team_type})
    db.commit()
    db.refresh(unit)
    return {"id": unit.id, "unit_uid": unit.unit_uid, "name": unit.name, "team_type": unit.team_type, "parent_id": unit.parent_id}


@router.post("/organization/responsibilities")
def add_responsibility(request: ResponsibilityRequest, user: User = Depends(current_user), db: Session = Depends(get_db)):
    require_admin(db, user.id)
    target_user = db.get(User, request.user_id)
    unit = db.get(OrganizationUnit, request.unit_id)
    product = db.get(Product, request.product_id)
    if not target_user or not unit or not product:
        raise HTTPException(404, "用户或组织不存在")
    if unit.unit_type != "team" or unit.team_type != request.team_type or not unit.active:
        raise HTTPException(400, "责任组别与组织小组不匹配")
    if not target_user.is_active:
        raise HTTPException(400, "不能为停用用户分配品类责任")
    existing = db.query(UserResponsibility).filter_by(
        user_id=request.user_id, scope_type="product", scope_uid=f"product_{request.product_id}",
        team_type=request.team_type, valid_to=None,
    ).first()
    if existing and existing.unit_id == unit.id and existing.responsibility_level == request.level:
        return {"id": existing.id, "user_id": existing.user_id, "product_id": request.product_id,
                "team_type": existing.team_type, "unit_id": existing.unit_id, "level": existing.responsibility_level}
    if existing:
        existing.valid_to = utc_now_naive()
        db.flush()
    record = UserResponsibility(user_id=request.user_id, scope_type="product", scope_uid=f"product_{request.product_id}",
                                team_type=request.team_type, responsibility_level=request.level,
                                unit_id=unit.id, can_edit=request.level != "reviewer",
                                valid_from=utc_now_naive(), assigned_by=user.id)
    db.add(record)
    db.flush()
    _link_same_category_colleagues(db, record)
    from app.services.collaboration_identity_service import audit
    audit(db, user.id, "responsibility_changed", detail={"user_id": record.user_id,
          "product_id": request.product_id, "team_type": record.team_type, "unit_id": record.unit_id})
    db.commit()
    return {"id": record.id, "user_id": record.user_id, "product_id": request.product_id,
            "team_type": record.team_type, "unit_id": record.unit_id, "level": record.responsibility_level}


def _link_same_category_colleagues(db: Session, record: UserResponsibility) -> None:
    active_responsibilities = db.query(UserResponsibility).filter(
        UserResponsibility.scope_type == record.scope_type,
        UserResponsibility.scope_uid == record.scope_uid,
        UserResponsibility.valid_to.is_(None),
    ).all()
    desired = set()
    for source in active_responsibilities:
        for target in active_responsibilities:
            if source.user_id != target.user_id and source.team_type != target.team_type:
                desired.add((source.user_id, target.user_id))
    all_edges = db.query(CollaborationEdge).filter_by(
        scope_type=record.scope_type, scope_uid=record.scope_uid,
        relation_type="same_category",
    ).all()
    existing = set()
    for edge in all_edges:
        pair = (edge.source_user_id, edge.target_user_id)
        if pair in desired:
            existing.add(pair)
            edge.valid_to = None
        else:
            if edge.valid_to is None:
                edge.valid_to = utc_now_naive()
    for source_id, target_id in desired - existing:
        db.add(CollaborationEdge(source_user_id=source_id, target_user_id=target_id,
                                 scope_type=record.scope_type, scope_uid=record.scope_uid,
                                 relation_type="same_category", default_access="viewer",
                                 can_request_edit=True))


@router.get("/organization/responsibilities")
def list_responsibilities(user: User = Depends(current_user), db: Session = Depends(get_db)):
    require_admin(db, user.id)
    result = []
    for record in db.query(UserResponsibility).filter(UserResponsibility.valid_to.is_(None)).order_by(UserResponsibility.id.desc()).all():
        try:
            product_id = int(record.scope_uid.removeprefix("product_"))
        except ValueError:
            continue
        target_user, product, unit = db.get(User, record.user_id), db.get(Product, product_id), db.get(OrganizationUnit, record.unit_id)
        if not target_user or not product:
            continue
        result.append({"id": record.id, "user_id": record.user_id, "username": target_user.username,
                       "display_name": target_user.display_name, "product_id": product.id,
                       "product_name": product.name, "team_type": record.team_type,
                       "unit_id": record.unit_id, "unit_name": unit.name if unit else None,
                       "level": record.responsibility_level, "can_edit": record.can_edit})
    return {"items": result}


@router.post("/permissions/library-grants")
def create_library_grant(request: LibraryGrantRequest, user: User = Depends(current_user), db: Session = Depends(get_db)):
    require_admin(db, user.id)
    target = db.get(User, request.user_id)
    credential = db.get(CollaborationCredential, request.user_id)
    database = db.get(PatentDatabase, request.database_id)
    if not target or not target.is_active or not credential or not credential.active:
        raise HTTPException(404, "协同用户不存在或已停用")
    if not database or database.is_archived or not database.database_uid:
        raise HTTPException(404, "数据库不存在或已归档")
    fields = list(dict.fromkeys(request.fields))
    if not fields or "title" not in fields or set(fields) - EXPORT_FIELDS:
        raise HTTPException(400, "字段范围无效")
    actions = list(dict.fromkeys(request.actions))
    if "apply" in actions and not request.edit_password:
        raise HTTPException(400, "主表应用授权必须设置独立编辑密码")
    if "apply" in actions and "viewer" in roles(db, target.id):
        raise HTTPException(400, "只读协作者不能获得主表应用授权")
    if request.product_ids:
        existing_ids = {row[0] for row in db.query(Product.id).filter(Product.id.in_(request.product_ids)).all()}
        if existing_ids != set(request.product_ids):
            raise HTTPException(404, "部分品类不存在")
    grant = PermissionGrant(grant_uid=uid("grant"), subject_user_id=target.id, granted_by=user.id,
                            scope_type="database", scope_uid=database.database_uid, field_scope=fields,
                            scope_json={"product_ids": list(dict.fromkeys(request.product_ids))},
                            actions=actions,
                            password_digest=PASSWORDS.hash(request.edit_password) if request.edit_password else None,
                            expires_at=utc_now_naive() + timedelta(days=request.expires_days))
    db.add(grant)
    from app.services.collaboration_identity_service import audit
    audit(db, user.id, "permission_granted", detail={"grant_uid": grant.grant_uid,
          "subject_user_id": target.id, "database_uid": database.database_uid,
          "actions": actions})
    db.commit()
    return {"grant_uid": grant.grant_uid, "user_id": target.id, "username": target.username,
            "database_id": database.id, "database_name": database.name,
            "fields": fields, "product_ids": grant.scope_json["product_ids"],
            "actions": actions,
            "expires_at": grant.expires_at.isoformat()}


@router.get("/permissions/library-grants")
def list_library_grants(user: User = Depends(current_user), db: Session = Depends(get_db)):
    require_admin(db, user.id)
    result = []
    for grant in db.query(PermissionGrant).filter(PermissionGrant.scope_type == "database").order_by(PermissionGrant.id.desc()).all():
        target = db.get(User, grant.subject_user_id) if grant.subject_user_id else None
        database = db.query(PatentDatabase).filter_by(database_uid=grant.scope_uid).first()
        if target and database:
            result.append({"grant_uid": grant.grant_uid, "username": target.username,
                           "database_id": database.id, "database_name": database.name,
                           "fields": grant.field_scope, "product_ids": (grant.scope_json or {}).get("product_ids", []),
                           "actions": grant.actions,
                           "expires_at": grant.expires_at.isoformat() if grant.expires_at else None,
                           "revoked": grant.revoked_at is not None})
    return {"items": result}


@router.delete("/permissions/library-grants/{grant_uid}")
def revoke_library_grant(grant_uid: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    require_admin(db, user.id)
    grant = db.query(PermissionGrant).filter_by(grant_uid=grant_uid, scope_type="database").first()
    if not grant:
        raise HTTPException(404, "授权不存在")
    if grant.revoked_at is None:
        from app.core.time import utc_now_naive
        from app.services.collaboration_identity_service import audit
        grant.revoked_at = utc_now_naive()
        audit(db, user.id, "permission_revoked", detail={"grant_uid": grant.grant_uid})
        db.commit()
    return {"success": True}


@router.post("/packages/preview-export")
def preview_package(request: ExportRequest, user: User = Depends(current_user), db: Session = Depends(get_db)):
    return preview_export(db, user.id, request)


@router.post("/packages/export")
def create_package(request: ExportRequest, user: User = Depends(current_user), db: Session = Depends(get_db)):
    return export_package(db, user.id, request)


@router.post("/packages/inspect")
async def inspect_package_file(
    file: UploadFile = File(...), password: str = Form(...), user: User = Depends(current_user), db: Session = Depends(get_db)
):
    return process_package_stream(db, user.id, file.file, password, inspect=True)


@router.post("/packages/import")
async def import_package_file(
    file: UploadFile = File(...), password: str = Form(...), user: User = Depends(current_user), db: Session = Depends(get_db)
):
    return process_package_stream(db, user.id, file.file, password)


@router.post("/packages/{package_uid}/preview-apply")
def preview_apply_package(package_uid: str, request: ApplyPackageRequest, user: User = Depends(current_user), db: Session = Depends(get_db)):
    from app.services.collaboration_sync_service import preview_apply
    return preview_apply(db, user.id, package_uid, request)


@router.get("/packages/{package_uid}/sources")
def shared_sources(package_uid: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    return {"items": shared_package_sources(db, user.id, package_uid)}


@router.post("/packages/{package_uid}/shared-library")
def import_shared_library(package_uid: str, request: SharedLibraryApplyRequest,
                          user: User = Depends(current_user), db: Session = Depends(get_db)):
    return apply_shared_library(db, user.id, package_uid, request)


@router.post("/packages/{package_uid}/apply")
def apply_package_file(package_uid: str, request: ApplyPackageRequest, user: User = Depends(current_user), db: Session = Depends(get_db)):
    from app.services.collaboration_sync_service import apply_package
    return apply_package(db, user.id, package_uid, request)


@router.post("/packages/{package_uid}/department-publication")
def import_department_publication(package_uid: str, request: DepartmentPublicationApplyRequest,
    user: User = Depends(current_user), db: Session = Depends(get_db)):
    from app.services.collaboration_sync_service import apply_department_publication
    return apply_department_publication(db, user.id, package_uid, request.decisions)


@router.get("/packages")
def get_packages(user: User = Depends(current_user), db: Session = Depends(get_db)):
    return {"items": list_packages(db, user.id)}


@router.get("/packages/{package_uid}/records")
def get_package_records(package_uid: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    return {"items": package_records(db, user.id, package_uid)}


@router.get("/packages/{package_uid}/download")
def download_package(package_uid: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    return FileResponse(export_path(db, user.id, package_uid), media_type="application/vnd.patwiki.pwshare",
                        filename=f"{package_uid}.pwshare")


@router.post("/aggregation-batches")
def create_sync_aggregation_batch(request: AggregationBatchCreateRequest, user: User = Depends(current_user), db: Session = Depends(get_db)):
    return create_aggregation_batch(db, user.id, request.name, request.target_database_id, request.package_uids)


@router.post("/aggregation-batches/{batch_uid}/preview")
def preview_sync_aggregation_batch(batch_uid: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    return preview_aggregation_batch(db, user.id, batch_uid)


@router.post("/aggregation-batches/{batch_uid}/submit")
def submit_sync_aggregation_batch(batch_uid: str, request: AggregationBatchSubmitRequest,
                                  user: User = Depends(current_user), db: Session = Depends(get_db)):
    return submit_aggregation_batch(db, user.id, batch_uid, request)


@router.post("/aggregation-batches/{batch_uid}/publish")
def publish_sync_aggregation_batch(batch_uid: str, request: AggregationPublishRequest,
                                   user: User = Depends(current_user), db: Session = Depends(get_db)):
    return publish_aggregation_batch(db, user.id, batch_uid, request)


@router.get("/sharing-preference")
def get_sharing_preference(user: User = Depends(current_user), db: Session = Depends(get_db)):
    from app.services.collaboration_update_service import sharing_preference
    return sharing_preference(db, user.id)


@router.put("/library-fields/{field_id}")
def edit_library_field(field_id: int, request: LibraryFieldEditRequest, user: User = Depends(current_user), db: Session = Depends(get_db)):
    from app.models import DatabaseMembership
    from app.models.collaboration_sync import SyncLibraryField
    row = db.get(SyncLibraryField, field_id)
    if not row:
        raise HTTPException(404, "来源库字段不存在")
    membership = db.query(DatabaseMembership).filter_by(user_id=user.id, database_id=row.database_id).first()
    if not roles(db, user.id) & {"system_admin", "department_leader"} and not (membership and membership.role in {"owner", "editor"}):
        raise HTTPException(403, "没有此来源库的编辑权限")
    database = db.get(PatentDatabase, row.database_id)
    if database.kind == "department_master" and not roles(db, user.id) & {"system_admin", "department_leader"}:
        raise HTTPException(403, "普通成员不能编辑部门已确认字段")
    before = row.local_value if row.has_overlay else row.baseline_value
    if before is not None and type(before) is not type(request.value) and request.value is not None:
        raise HTTPException(400, "字段类型不一致")
    row.local_value = request.value
    row.has_overlay = request.value != row.baseline_value
    row.editor_user_id = user.id
    row.reason = request.reason
    audit(db, user.id, "library_field_edited", detail={"field_id": field_id, "source_database_uid": row.source_database_uid,
        "field_key": row.field_key, "before": before, "after": request.value, "reason": request.reason})
    db.commit()
    return {"status": "saved"}


@router.put("/sharing-preference")
def put_sharing_preference(request: SharingPreferenceRequest, user: User = Depends(current_user), db: Session = Depends(get_db)):
    from app.services.collaboration_update_service import save_sharing_preference
    return save_sharing_preference(db, user.id, request)


@router.post("/aggregation-batches/{batch_uid}/external-updates/preview")
def preview_aggregation_updates(batch_uid: str, request: AggregationUpdateRequest,
    user: User = Depends(current_user), db: Session = Depends(get_db)):
    from app.services.collaboration_update_service import preview_updates
    return preview_updates(db, user.id, batch_uid, request.connector_id)


@router.post("/aggregation-batches/{batch_uid}/external-updates/confirm")
def confirm_aggregation_updates(batch_uid: str, request: AggregationUpdateConfirmRequest,
    user: User = Depends(current_user), db: Session = Depends(get_db)):
    from app.services.collaboration_update_service import confirm_updates
    return confirm_updates(db, user.id, batch_uid, [item.model_dump() for item in request.selected_items])
