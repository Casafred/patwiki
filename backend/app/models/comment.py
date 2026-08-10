"""Collaborative comments attached to a patent or one of its fields."""
from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, JSON, String, Text
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.database import Base


class Comment(Base):
    __tablename__ = "comments"

    id = Column(Integer, primary_key=True, index=True)
    patent_id = Column(Integer, ForeignKey("patents.id", ondelete="CASCADE"), nullable=False, index=True)
    parent_id = Column(Integer, ForeignKey("comments.id", ondelete="SET NULL"), nullable=True, index=True)
    author_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    author_name = Column(String(100), nullable=False, default="当前用户")
    field_key = Column(String(200), nullable=True, index=True)
    content = Column(Text, nullable=False)
    mentions = Column(JSON, nullable=False, default=list)
    is_resolved = Column(Boolean, nullable=False, default=False)
    resolved_by = Column(String(100), nullable=True)
    resolved_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, server_default=func.now(), index=True)
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    patent = relationship("Patent", back_populates="comments")
    parent = relationship("Comment", remote_side=[id], back_populates="replies")
    replies = relationship("Comment", back_populates="parent", cascade="all, delete-orphan")
