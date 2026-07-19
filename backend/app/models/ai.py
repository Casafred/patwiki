"""AI 任务与 AI 字段值模型。"""
from sqlalchemy import Column, Integer, String, Text, Float, Boolean, DateTime, ForeignKey, JSON
from sqlalchemy.sql import func

from app.database import Base


class AITask(Base):
    __tablename__ = "ai_tasks"

    id = Column(Integer, primary_key=True, index=True)
    task_type = Column(String(50), nullable=False)
    field_key = Column(String(100))
    model_name = Column(String(100))
    prompt_version = Column(String(20))
    status = Column(String(50), default="pending")
    total_items = Column(Integer, default=0)
    processed_items = Column(Integer, default=0)
    success_count = Column(Integer, default=0)
    failed_count = Column(Integer, default=0)
    config = Column(JSON)
    errors = Column(JSON)
    started_at = Column(DateTime)
    completed_at = Column(DateTime)
    created_at = Column(DateTime, server_default=func.now())


class AIFieldValue(Base):
    __tablename__ = "ai_field_values"

    id = Column(Integer, primary_key=True, index=True)
    patent_id = Column(Integer, ForeignKey("patents.id"), nullable=False)
    field_key = Column(String(100), nullable=False)
    value = Column(Text)
    model_name = Column(String(100))
    prompt_version = Column(String(20))
    temperature = Column(Float, default=0.0)
    input_hash = Column(String(64))
    tokens_used = Column(Integer, default=0)
    cost = Column(Float, default=0.0)
    duration_ms = Column(Integer, default=0)
    is_overridden = Column(Boolean, default=False)
    overridden_value = Column(Text)
    overridden_at = Column(DateTime)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())
