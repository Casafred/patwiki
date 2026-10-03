"""Single employee configuration files for offline enrollment and role updates."""
import base64
import json
from datetime import datetime

from cryptography.exceptions import InvalidSignature
from argon2.exceptions import InvalidHashError
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey
from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.core.time import utc_now_naive
from app.models import User, PatentDatabase, DatabaseMembership
from app.models.collaboration_sync import CollaborationCredential, CollaborationEnrollment, CollaborationSession, UserRoleAssignment, PermissionGrant
from app.services.collaboration_identity_service import audit, require_admin, roles, uid
from app.services.collaboration_package_codec import json_bytes


def export_enrollment(db: Session, admin_id: int, user_id: int, department_code: str, signing_key: bytes) -> dict:
    require_admin(db, admin_id)
    user = db.get(User, user_id)
    credential = db.get(CollaborationCredential, user_id)
    if not user or not credential or not user.employee_no:
        raise HTTPException(400, "请先设置有效协同账号和员工工号")
    assigned = roles(db, user_id)
    role = "system_admin" if assigned & {"system_admin", "department_leader"} else "viewer" if "viewer" in assigned else "member"
    private = Ed25519PrivateKey.from_private_bytes(signing_key)
    payload = {"format": "patwiki.employee-config", "version": 1, "department_code": department_code,
        "employee_no": user.employee_no, "user_uid": user.user_uid, "username": credential.login_name,
        "display_name": user.display_name or user.username, "role": role,
        "active": bool(credential.active and user.is_active), "password_hash": credential.password_hash,
        "issued_at": utc_now_naive().isoformat(),
        "issuer_public_key": base64.b64encode(private.public_key().public_bytes_raw()).decode("ascii")}
    payload["database_permissions"] = [{"database_uid": database.database_uid,
        "actions": ["export", "apply"] if membership.role in {"owner", "editor"} else [],
        "fields": []} for membership, database in db.query(DatabaseMembership, PatentDatabase).join(
            PatentDatabase, PatentDatabase.id == DatabaseMembership.database_id).filter(DatabaseMembership.user_id == user_id).all()]
    for grant in db.query(PermissionGrant).filter_by(subject_user_id=user_id, scope_type="database", revoked_at=None).all():
        if not grant.expires_at or grant.expires_at > utc_now_naive():
            payload["database_permissions"].append({"database_uid": grant.scope_uid, "actions": grant.actions,
                "fields": grant.field_scope})
    return {"payload": payload, "signature": base64.b64encode(private.sign(json_bytes(payload))).decode("ascii")}


def import_enrollment(db: Session, raw: bytes) -> dict:
    if len(raw) > 64 * 1024:
        raise HTTPException(413, "成员配置文件过大")
    try:
        document = json.loads(raw)
        payload = document["payload"]
        key = base64.b64decode(payload["issuer_public_key"], validate=True)
        Ed25519PublicKey.from_public_bytes(key).verify(base64.b64decode(document["signature"], validate=True), json_bytes(payload))
        from pydantic import BaseModel, ConfigDict, Field
        from typing import Literal
        class DatabasePermission(BaseModel):
            model_config = ConfigDict(extra="forbid", strict=True)
            database_uid: str = Field(pattern=r"^db_[a-f0-9]{32}$")
            actions: list[Literal["export", "apply"]] = Field(max_length=2)
            fields: list[str] = Field(max_length=100)
        class EmployeeConfig(BaseModel):
            model_config = ConfigDict(extra="forbid", strict=True)
            format: Literal["patwiki.employee-config"]
            version: Literal[1]
            department_code: str = Field(min_length=1, max_length=80)
            employee_no: str = Field(min_length=1, max_length=50)
            user_uid: str = Field(pattern=r"^user_[a-f0-9]{32}$")
            username: str = Field(pattern=r"^[a-z0-9_.@-]{1,100}$")
            display_name: str = Field(min_length=1, max_length=100)
            role: Literal["system_admin", "member", "viewer"]
            active: bool
            password_hash: str = Field(min_length=40, max_length=255)
            issued_at: str
            issuer_public_key: str
            database_permissions: list[DatabasePermission] = Field(default_factory=list, max_length=500)
        config = EmployeeConfig.model_validate(payload)
        issued_at = datetime.fromisoformat(config.issued_at)
        if issued_at.tzinfo is not None or issued_at > utc_now_naive():
            raise ValueError("invalid issuance time")
        from argon2 import extract_parameters
        parameters = extract_parameters(config.password_hash)
        if not (8 * parameters.parallelism <= parameters.memory_cost <= 262144 and
                1 <= parameters.time_cost <= 10 and 1 <= parameters.parallelism <= 8 and
                16 <= parameters.hash_len <= 64 and 8 <= parameters.salt_len <= 64):
            raise ValueError("invalid password hash parameters")
    except (ValueError, KeyError, TypeError, InvalidSignature, InvalidHashError) as exc:
        raise HTTPException(400, "成员配置无效或签名损坏") from exc
    try:
        user = db.query(User).filter_by(user_uid=config.user_uid).first()
        enrollment = db.get(CollaborationEnrollment, user.id) if user else None
        if enrollment:
            if enrollment.issuer_public_key != config.issuer_public_key or enrollment.department_code != config.department_code or enrollment.employee_no != config.employee_no:
                raise HTTPException(403, "配置签发者或成员身份不匹配")
            if issued_at <= enrollment.accepted_at:
                return {"username": config.username, "status": "already_processed"}
        elif db.query(CollaborationCredential).first():
            raise HTTPException(403, "已初始化的客户端只能更新原成员配置")
        if user is None:
            if db.query(User).filter((User.username == config.username) | (User.employee_no == config.employee_no)).first():
                raise HTTPException(409, "本机已有同名账号或工号，需先核对身份")
            user = User(user_uid=config.user_uid, username=config.username, employee_no=config.employee_no)
            db.add(user)
            db.flush()
        credential = db.get(CollaborationCredential, user.id)
        if credential is None:
            credential = CollaborationCredential(user_id=user.id, login_name=config.username, password_hash=config.password_hash)
            db.add(credential)
        credential.active = config.active
        user.is_active = config.active
        user.display_name = config.display_name
        from app.services.collaboration_sync_service import EXPORT_FIELDS
        db.query(PermissionGrant).filter_by(subject_user_id=user.id, scope_type="database", subject_label="employee_config").update({"revoked_at": utc_now_naive()})
        for permission in config.database_permissions:
            if set(permission.fields) - EXPORT_FIELDS:
                raise HTTPException(400, "配置包含未知字段权限")
            db.add(PermissionGrant(grant_uid=uid("grant"), subject_user_id=user.id, subject_label="employee_config",
                scope_type="database", scope_uid=permission.database_uid, actions=permission.actions,
                field_scope=permission.fields or sorted(EXPORT_FIELDS)))
        db.query(UserRoleAssignment).filter_by(user_id=user.id, valid_to=None).update({"valid_to": utc_now_naive()})
        db.add(UserRoleAssignment(user_id=user.id, role_code=config.role))
        db.query(CollaborationSession).filter_by(user_id=user.id).delete()
        if enrollment is None:
            enrollment = CollaborationEnrollment(user_id=user.id, department_code=config.department_code,
                employee_no=config.employee_no, issuer_public_key=config.issuer_public_key)
            db.add(enrollment)
        enrollment.accepted_at = issued_at
        audit(db, user.id, "employee_config_imported", detail={"department_code": config.department_code, "role": config.role})
        db.commit()
        return {"username": config.username, "status": "configured"}
    except Exception:
        db.rollback()
        raise
