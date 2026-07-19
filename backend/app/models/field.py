"""自定义字段定义模型。"""
from sqlalchemy import (
    Column, Integer, String, Text, Boolean, JSON, DateTime,
    Enum as SQLEnum,
)
from sqlalchemy.sql import func

from app.database import Base
from app.models.enums import CustomFieldType


class CustomField(Base):
    __tablename__ = "custom_fields"

    id = Column(Integer, primary_key=True, index=True)
    key = Column(String(100), unique=True, nullable=False)
    name = Column(String(200), nullable=False)
    field_type = Column(SQLEnum(CustomFieldType), nullable=False)
    group_name = Column(String(100), default="默认")
    description = Column(Text)
    options = Column(JSON)
    default_value = Column(Text)
    is_required = Column(Boolean, default=False)
    is_active = Column(Boolean, default=True)
    sort_order = Column(Integer, default=0)
    ai_config = Column(JSON)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())
