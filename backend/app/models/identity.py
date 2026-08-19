"""专利身份索引。

Patent 的号码字段是兼容投影；PatentIdentifier 保存可追溯的身份事实，
用于跨来源、跨号码类型的匹配和冲突检测。任何自动匹配都不能据此合并
不同 Patent，合并必须由人工确认完成。
"""
from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Index, Integer, JSON, String, UniqueConstraint
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.database import Base


class PatentIdentifier(Base):
    __tablename__ = "patent_identifiers"
    __table_args__ = (
        UniqueConstraint(
            "identifier_namespace",
            "identifier_type",
            "jurisdiction_code",
            "normalized_value",
            name="uq_patent_identifier_identity",
        ),
        Index("ix_patent_identifiers_normalized", "normalized_value"),
    )

    id = Column(Integer, primary_key=True, index=True)
    patent_id = Column(Integer, ForeignKey("patents.id", ondelete="CASCADE"), nullable=False, index=True)
    identifier_namespace = Column(String(30), nullable=False, default="official")
    identifier_type = Column(String(30), nullable=False)  # application/publication/grant/external
    raw_value = Column(String(300), nullable=False)
    raw_values = Column(JSON, nullable=False, default=list)
    normalized_value = Column(String(300), nullable=False)
    jurisdiction_code = Column(String(10), nullable=True)
    kind_code = Column(String(10), nullable=True)
    source_system = Column(String(200), nullable=True)
    source_timestamp = Column(DateTime, nullable=True)
    is_primary = Column(Boolean, nullable=False, default=False)
    valid_from = Column(DateTime, nullable=True)
    valid_to = Column(DateTime, nullable=True)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    patent = relationship("Patent", back_populates="identifiers")
