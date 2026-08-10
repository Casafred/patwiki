"""Automation rule and execution log models."""
from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, JSON, String, Text
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.database import Base


class AutomationRule(Base):
    __tablename__ = "automation_rules"

    id = Column(Integer, primary_key=True, index=True)
    database_id = Column(Integer, ForeignKey("patent_databases.id", ondelete="CASCADE"), nullable=False, index=True)
    name = Column(String(200), nullable=False)
    description = Column(Text)
    is_enabled = Column(Boolean, default=True, nullable=False)
    priority = Column(Integer, default=0, nullable=False)
    trigger_config = Column(JSON, nullable=False, default=dict)
    condition_config = Column(JSON, nullable=False, default=list)
    action_config = Column(JSON, nullable=False, default=list)
    last_executed_at = Column(DateTime)
    execution_count = Column(Integer, default=0, nullable=False)
    failure_count = Column(Integer, default=0, nullable=False)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    logs = relationship("AutomationLog", back_populates="rule", cascade="all, delete-orphan")


class AutomationLog(Base):
    __tablename__ = "automation_logs"

    id = Column(Integer, primary_key=True, index=True)
    rule_id = Column(Integer, ForeignKey("automation_rules.id", ondelete="CASCADE"), nullable=False, index=True)
    patent_id = Column(Integer, ForeignKey("patents.id", ondelete="SET NULL"), nullable=True, index=True)
    trigger_type = Column(String(50), nullable=False)
    status = Column(String(20), nullable=False)
    error_message = Column(Text)
    executed_at = Column(DateTime, server_default=func.now())
    details = Column(JSON, default=dict)

    rule = relationship("AutomationRule", back_populates="logs")
