"""表单视图公开提交链接。"""
from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.database import Base


class FormShareLink(Base):
    __tablename__ = "form_share_links"

    id = Column(Integer, primary_key=True, index=True)
    view_id = Column(Integer, ForeignKey("patent_views.id", ondelete="CASCADE"), nullable=False, index=True)
    token = Column(String(128), unique=True, nullable=False, index=True)
    is_active = Column(Boolean, default=True, nullable=False)
    expires_at = Column(DateTime)
    created_at = Column(DateTime, server_default=func.now())

    view = relationship("PatentView", back_populates="form_share_links")
