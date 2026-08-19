"""Excel/Word 工作文件模板定义。

模板只保存字段投影、筛选和排序，不保存导出的数据快照；每次导出都从
Patent 主表重新装配，并在文件中写入模板版本和字段来源信息。
"""
from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, JSON, String, Text, UniqueConstraint
from sqlalchemy.sql import func

from app.database import Base


class PatentExportTemplate(Base):
    __tablename__ = "patent_export_templates"
    __table_args__ = (
        UniqueConstraint("database_id", "template_key", name="uq_export_template_key"),
    )

    id = Column(Integer, primary_key=True, index=True)
    database_id = Column(Integer, ForeignKey("patent_databases.id", ondelete="CASCADE"), nullable=False, index=True)
    view_id = Column(Integer, ForeignKey("patent_views.id", ondelete="SET NULL"), nullable=True, index=True)
    template_key = Column(String(100), nullable=False)
    name = Column(String(200), nullable=False)
    description = Column(Text)
    output_format = Column(String(20), nullable=False, default="excel")  # excel / word / csv
    field_keys = Column(JSON, nullable=False, default=list)
    filter_config = Column(JSON, nullable=False, default=dict)
    sort_config = Column(JSON, nullable=False, default=dict)
    group_by = Column(String(100), nullable=True)
    version = Column(Integer, nullable=False, default=1)
    is_system = Column(Boolean, nullable=False, default=False)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())
