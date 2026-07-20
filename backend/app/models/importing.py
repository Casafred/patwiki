"""导入相关模型：字段映射模板 + 导入批次。"""
from sqlalchemy import (
    Column, Integer, String, Text, Boolean, DateTime, ForeignKey, JSON,
    Enum as SQLEnum,
)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.database import Base
from app.models.enums import ImportBatchStatus


class FieldMapping(Base):
    """保存的字段映射模板，便于下次导入复用。"""
    __tablename__ = "field_mappings"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(200), nullable=False)
    description = Column(Text)
    mapping_config = Column(JSON, nullable=False)
    is_default = Column(Boolean, default=False)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())


class ImportBatch(Base):
    __tablename__ = "import_batches"

    id = Column(Integer, primary_key=True, index=True)
    filename = Column(String(500), nullable=False)
    status = Column(SQLEnum(ImportBatchStatus), default=ImportBatchStatus.PENDING)
    total_rows = Column(Integer, default=0)
    processed_rows = Column(Integer, default=0)
    inserted_count = Column(Integer, default=0)
    updated_count = Column(Integer, default=0)
    skipped_count = Column(Integer, default=0)
    duplicate_count = Column(Integer, default=0)
    error_count = Column(Integer, default=0)
    mapping_id = Column(Integer, ForeignKey("field_mappings.id"))
    mapping_config = Column(JSON)
    errors = Column(JSON)
    started_at = Column(DateTime)
    completed_at = Column(DateTime)
    created_at = Column(DateTime, server_default=func.now())
    # P2-2：导入历史按库/视图过滤
    database_id = Column(Integer, ForeignKey("patent_databases.id"), nullable=True, index=True)
    view_id = Column(Integer, ForeignKey("patent_views.id"), nullable=True, index=True)
    view_local_written = Column(Integer, default=0)  # P1-15：写入视图本地字段值条数
    dedupe_by = Column(String(20), default="both")
    triggered_by = Column(String(100), nullable=True)  # 触发者用户名/邮箱

    mapping = relationship("FieldMapping")
    patents = relationship("Patent", back_populates="source_batch")
