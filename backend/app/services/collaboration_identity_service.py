"""Password sessions and local enrollment independent of the legacy user picker."""
from __future__ import annotations

import hashlib
import hmac
import secrets
from datetime import timedelta
from pathlib import Path
from uuid import uuid4

from argon2 import PasswordHasher
from argon2.exceptions import VerificationError
from fastapi import HTTPException
from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from app.config import settings
from app.core.time import utc_now_naive
from app.models import User
from app.models.collaboration_sync import (
    CollaborationCredential, CollaborationSession, OrganizationUnit,
    SyncAuditEvent, SyncWorkspace, UserRoleAssignment,
)

PASSWORDS = PasswordHasher(time_cost=3, memory_cost=65536, parallelism=1)
DUMMY_PASSWORD = PASSWORDS.hash(secrets.token_urlsafe(32))
ADMIN_ROLES = {"system_admin", "department_leader"}


def uid(prefix: str) -> str:
    return f"{prefix}_{uuid4().hex}"


def workspace_dir() -> Path:
    root = settings.DATA_DIR / "collaboration_sync"
    for name in ("inbox", "outbox", "archive", "quarantine", "snapshots"):
        (root / name).mkdir(parents=True, exist_ok=True)
    return root


def audit(db: Session, user_id: int | None, action: str, *, package_id=None, detail=None, result="success"):
    db.add(SyncAuditEvent(actor_user_id=user_id, action=action, package_id=package_id,
                          detail_json=detail or {}, result=result))


def roles(db: Session, user_id: int) -> set[str]:
    now = utc_now_naive()
    return {r.role_code for r in db.query(UserRoleAssignment).filter(
        UserRoleAssignment.user_id == user_id,
        or_(UserRoleAssignment.valid_from.is_(None), UserRoleAssignment.valid_from <= now),
        or_(UserRoleAssignment.valid_to.is_(None), UserRoleAssignment.valid_to > now),
    )}


def require_admin(db: Session, user_id: int):
    if not roles(db, user_id) & ADMIN_ROLES:
        raise HTTPException(403, "需要部门领导或维护管理员权限")


def session_user(db: Session, authorization: str | None) -> User:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(401, "请登录协同账号")
    digest = hashlib.sha256(authorization[7:].encode()).hexdigest()
    session = db.get(CollaborationSession, digest)
    if not session or session.expires_at <= utc_now_naive():
        raise HTTPException(401, "协同登录已过期")
    credential = db.get(CollaborationCredential, session.user_id)
    user = db.get(User, session.user_id)
    if not credential or not credential.active or not user or not user.is_active:
        raise HTTPException(401, "协同账号已停用")
    return user


def setup_status(db: Session) -> dict:
    configured = db.query(CollaborationCredential).first() is not None
    path = workspace_dir() / "setup-token.txt"
    if not configured and not path.exists():
        try:
            with path.open("x", encoding="ascii") as stream:
                stream.write(secrets.token_urlsafe(32))
            path.chmod(0o600)
        except FileExistsError:
            pass
    return {"configured": configured, "setup_token_path": str(path) if not configured else None}


def create_account(db: Session, request, assigned_by: int | None, role: str):
    username = request.username.lower()
    if db.query(CollaborationCredential).filter_by(login_name=username).first():
        raise HTTPException(409, "协同账号已存在")
    unit_id = getattr(request, "unit_id", None)
    if unit_id and not db.get(OrganizationUnit, unit_id):
        raise HTTPException(400, "组织不存在")
    if role == "group_leader" and (not unit_id or db.get(OrganizationUnit, unit_id).unit_type != "team"):
        raise HTTPException(400, "组长必须指定有效的小组")
    user = db.query(User).filter(func.lower(User.username) == username).first()
    if user is None:
        user = User(username=username, display_name=request.display_name, role="member", user_uid=uid("user"))
        db.add(user)
        db.flush()
    elif not user.is_active:
        raise HTTPException(409, "对应的本地用户已停用")
    else:
        user.display_name = request.display_name
    if not user.user_uid:
        user.user_uid = uid("user")
    credential = CollaborationCredential(user_id=user.id, login_name=username,
                                          password_hash=PASSWORDS.hash(request.password))
    db.add(credential)
    db.add(UserRoleAssignment(user_id=user.id, role_code=role, unit_id=unit_id, assigned_by=assigned_by))
    audit(db, assigned_by, "account_created", detail={"subject": user.user_uid, "role": role})
    db.flush()
    return user


def bootstrap(db: Session, request):
    if db.query(CollaborationCredential).first():
        raise HTTPException(409, "协同空间已初始化")
    path = workspace_dir() / "setup-token.txt"
    if not path.exists() or not hmac.compare_digest(path.read_text().strip(), request.setup_token):
        raise HTTPException(403, "本机初始化口令错误")
    admin = create_account(db, request, None, "system_admin")
    root = OrganizationUnit(unit_uid=uid("unit"), name="专利部门", unit_type="department")
    db.add(root)
    db.flush()
    workspace = db.query(SyncWorkspace).first()
    if workspace and workspace.owner_user_id is None:
        workspace.owner_user_id = admin.id
    for name, team in (("撰写组", "writing"), ("检索组", "retrieval"), ("分析组", "analysis")):
        db.add(OrganizationUnit(unit_uid=uid("unit"), name=name, unit_type="team", team_type=team, parent_id=root.id))
    db.commit()
    path.unlink(missing_ok=True)
    return login(db, request.username, request.password)


def login(db: Session, username: str, password: str) -> dict:
    credential = db.query(CollaborationCredential).filter_by(login_name=username.lower()).first()
    now = utc_now_naive()
    if credential and credential.locked_until and credential.locked_until > now:
        raise HTTPException(429, "登录失败次数过多，请稍后重试")
    try:
        valid = PASSWORDS.verify(credential.password_hash if credential else DUMMY_PASSWORD, password)
    except VerificationError:
        valid = False
    user = db.get(User, credential.user_id) if credential else None
    if not valid or not credential or not credential.active or not user or not user.is_active:
        if credential:
            credential.failed_attempts += 1
            if credential.failed_attempts >= 5:
                credential.locked_until = now + timedelta(minutes=15)
        audit(db, credential.user_id if credential else None, "login", result="denied")
        db.commit()
        raise HTTPException(401, "账号或密码错误，或账号已停用")
    credential.failed_attempts = 0
    credential.locked_until = None
    token = secrets.token_urlsafe(48)
    expires = now + timedelta(hours=8)
    db.query(CollaborationSession).filter(CollaborationSession.expires_at <= now).delete()
    db.add(CollaborationSession(token_hash=hashlib.sha256(token.encode()).hexdigest(), user_id=user.id, expires_at=expires))
    audit(db, user.id, "login")
    db.commit()
    return {"token": token, "expires_at": expires.isoformat(), "user": identity(db, user)}


def identity(db: Session, user: User) -> dict:
    credential = db.get(CollaborationCredential, user.id)
    if credential is None:
        raise HTTPException(401, "该用户没有协同账号")
    return {"id": user.id, "user_uid": user.user_uid, "username": credential.login_name,
            "display_name": user.display_name, "roles": sorted(roles(db, user.id)), "active": credential.active}


def logout(db: Session, user_id: int, authorization: str | None) -> None:
    if authorization and authorization.startswith("Bearer "):
        digest = hashlib.sha256(authorization[7:].encode()).hexdigest()
        session = db.get(CollaborationSession, digest)
        if session and session.user_id == user_id:
            db.delete(session)
            audit(db, user_id, "logout")
            db.commit()
