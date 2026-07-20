"""用户与库的权限/协作关系模型。

MVP 版本：用户无密码（仅标识），通过 localStorage 在前端记录当前用户。
后续可扩展为完整的认证系统。
"""
from sqlalchemy import Column, Integer, String, Text, Boolean, DateTime, ForeignKey, UniqueConstraint
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.database import Base


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(100), unique=True, nullable=False, index=True)
    display_name = Column(String(200))
    email = Column(String(255))
    role = Column(String(50), default="member")  # admin / member
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    database_memberships = relationship("DatabaseMembership", back_populates="user", cascade="all, delete-orphan")


class DatabaseMembership(Base):
    """用户与库的协作关系。

    role:
      - owner:   所有者（创建者），拥有全部权限
      - editor:  可编辑（修改/删除专利、导入、AI 处理等）
      - viewer:  只读
    """
    __tablename__ = "database_memberships"
    __table_args__ = (
        UniqueConstraint("user_id", "database_id", name="uq_user_database"),
    )

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    database_id = Column(Integer, ForeignKey("patent_databases.id", ondelete="CASCADE"), nullable=False, index=True)
    role = Column(String(20), default="viewer")  # owner / editor / viewer
    created_at = Column(DateTime, server_default=func.now())

    user = relationship("User", back_populates="database_memberships")
    database = relationship("PatentDatabase", back_populates="memberships")
