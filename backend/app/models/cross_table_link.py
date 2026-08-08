"""通用跨表关联记录。"""
from sqlalchemy import Column, Integer, String, DateTime, UniqueConstraint
from sqlalchemy.sql import func

from app.database import Base


class CrossTableLink(Base):
    __tablename__ = "cross_table_links"
    __table_args__ = (
        UniqueConstraint(
            "link_field_key",
            "source_table",
            "source_record_id",
            "target_table",
            "target_record_id",
            name="uq_cross_table_link",
        ),
    )

    id = Column(Integer, primary_key=True, index=True)
    link_field_key = Column(String(100), nullable=False, index=True)
    source_table = Column(String(50), nullable=False)
    source_record_id = Column(Integer, nullable=False, index=True)
    target_table = Column(String(50), nullable=False)
    target_record_id = Column(Integer, nullable=False, index=True)
    created_by = Column(String(100))
    created_at = Column(DateTime, server_default=func.now())
