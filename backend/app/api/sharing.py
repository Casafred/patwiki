"""用户与库的协作/权限管理 API（MVP）。

设计：
- 用户无密码，前端通过 localStorage 记录当前用户 ID
- 库的所有者可添加/移除协作者，并设置角色（editor / viewer）
- 不强制鉴权（MVP 阶段，所有 API 公开访问）
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import or_, and_
from typing import Optional
from pydantic import BaseModel

from app.database import get_db
from app.models import User, DatabaseMembership, PatentDatabase

router = APIRouter(tags=["sharing"])


# ============================================================
# Schemas
# ============================================================
class UserCreate(BaseModel):
    username: str
    display_name: Optional[str] = None
    email: Optional[str] = None
    role: Optional[str] = "member"


class UserOut(BaseModel):
    id: int
    username: str
    display_name: Optional[str]
    email: Optional[str]
    role: str
    is_active: bool
    created_at: Optional[str] = None

    class Config:
        from_attributes = True


class MemberAdd(BaseModel):
    username: Optional[str] = None
    user_id: Optional[int] = None
    role: str = "viewer"  # editor / viewer


class MemberOut(BaseModel):
    id: int
    user_id: int
    username: str
    display_name: Optional[str]
    role: str
    created_at: Optional[str] = None

    class Config:
        from_attributes = True


class MemberUpdate(BaseModel):
    role: str


# ============================================================
# 用户管理
# ============================================================
@router.get("/users", response_model=list[UserOut])
def list_users(db: Session = Depends(get_db)):
    return db.query(User).order_by(User.created_at).all()


@router.post("/users", response_model=UserOut)
def create_user(user_in: UserCreate, db: Session = Depends(get_db)):
    if db.query(User).filter(User.username == user_in.username).first():
        raise HTTPException(status_code=400, detail=f"用户名 '{user_in.username}' 已存在")
    user = User(
        username=user_in.username,
        display_name=user_in.display_name or user_in.username,
        email=user_in.email,
        role=user_in.role or "member",
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@router.get("/users/{user_id}", response_model=UserOut)
def get_user(user_id: int, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return user


# ============================================================
# 库的成员管理
# ============================================================
@router.get("/databases/{database_id}/members", response_model=list[MemberOut])
def list_members(database_id: int, db: Session = Depends(get_db)):
    """列出库的所有协作者（包括所有者）"""
    db_obj = db.query(PatentDatabase).filter(PatentDatabase.id == database_id).first()
    if not db_obj:
        raise HTTPException(status_code=404, detail="Database not found")

    members = db.query(DatabaseMembership).filter(DatabaseMembership.database_id == database_id).all()
    result = []
    for m in members:
        result.append(MemberOut(
            id=m.id,
            user_id=m.user_id,
            username=m.user.username,
            display_name=m.user.display_name,
            role=m.role,
            created_at=m.created_at.isoformat() if m.created_at else None,
        ))
    return result


@router.post("/databases/{database_id}/members", response_model=MemberOut)
def add_member(database_id: int, member_in: MemberAdd, db: Session = Depends(get_db)):
    """添加协作者（按 user_id 或 username 查找用户）"""
    db_obj = db.query(PatentDatabase).filter(PatentDatabase.id == database_id).first()
    if not db_obj:
        raise HTTPException(status_code=404, detail="Database not found")

    # 找用户
    user = None
    if member_in.user_id:
        user = db.query(User).filter(User.id == member_in.user_id).first()
    elif member_in.username:
        user = db.query(User).filter(User.username == member_in.username).first()
        if not user:
            # 用户不存在则自动创建（便于协作邀请）
            user = User(username=member_in.username, display_name=member_in.username)
            db.add(user)
            db.commit()
            db.refresh(user)
    if not user:
        raise HTTPException(status_code=400, detail="必须提供 user_id 或 username")

    # 已存在则更新角色
    existing = db.query(DatabaseMembership).filter(
        DatabaseMembership.user_id == user.id,
        DatabaseMembership.database_id == database_id,
    ).first()
    if existing:
        existing.role = member_in.role
        db.commit()
        db.refresh(existing)
        return MemberOut(
            id=existing.id, user_id=user.id, username=user.username,
            display_name=user.display_name, role=existing.role,
            created_at=existing.created_at.isoformat() if existing.created_at else None,
        )

    membership = DatabaseMembership(
        user_id=user.id,
        database_id=database_id,
        role=member_in.role,
    )
    db.add(membership)
    db.commit()
    db.refresh(membership)
    return MemberOut(
        id=membership.id, user_id=user.id, username=user.username,
        display_name=user.display_name, role=membership.role,
        created_at=membership.created_at.isoformat() if membership.created_at else None,
    )


@router.put("/databases/{database_id}/members/{user_id}", response_model=MemberOut)
def update_member(database_id: int, user_id: int, member_in: MemberUpdate, db: Session = Depends(get_db)):
    membership = db.query(DatabaseMembership).filter(
        DatabaseMembership.user_id == user_id,
        DatabaseMembership.database_id == database_id,
    ).first()
    if not membership:
        raise HTTPException(status_code=404, detail="Membership not found")
    if membership.role == "owner":
        raise HTTPException(status_code=400, detail="不能修改所有者角色")
    if member_in.role not in ("editor", "viewer"):
        raise HTTPException(status_code=400, detail="role 必须是 editor 或 viewer")
    membership.role = member_in.role
    db.commit()
    db.refresh(membership)
    return MemberOut(
        id=membership.id, user_id=user_id, username=membership.user.username,
        display_name=membership.user.display_name, role=membership.role,
        created_at=membership.created_at.isoformat() if membership.created_at else None,
    )


@router.delete("/databases/{database_id}/members/{user_id}")
def remove_member(database_id: int, user_id: int, db: Session = Depends(get_db)):
    membership = db.query(DatabaseMembership).filter(
        DatabaseMembership.user_id == user_id,
        DatabaseMembership.database_id == database_id,
    ).first()
    if not membership:
        raise HTTPException(status_code=404, detail="Membership not found")
    if membership.role == "owner":
        raise HTTPException(status_code=400, detail="不能移除所有者")
    db.delete(membership)
    db.commit()
    return {"success": True}


# ============================================================
# 当前用户视角：与我共享的库
# ============================================================
@router.get("/users/{user_id}/databases")
def list_user_databases(user_id: int, db: Session = Depends(get_db)):
    """列出与某用户共享的所有库（含其角色）"""
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    memberships = db.query(DatabaseMembership).filter(DatabaseMembership.user_id == user_id).all()
    result = []
    for m in memberships:
        d = m.database
        result.append({
            "id": d.id,
            "name": d.name,
            "code": d.code,
            "description": d.description,
            "color": d.color,
            "icon": d.icon,
            "patent_count": d.patent_count,
            "is_default": d.is_default,
            "is_archived": d.is_archived,
            "my_role": m.role,
            "owner_id": d.owner_id,
        })
    return result
