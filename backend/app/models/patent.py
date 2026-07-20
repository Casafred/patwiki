"""专利主表 + 同族 + 引用 模型。

P0-8：Patent 新增 database_id 外键，关联 PatentDatabase。
"""
from sqlalchemy import (
    Column, Integer, String, Text, Date, DateTime, Boolean,
    ForeignKey, JSON, Float,
    Enum as SQLEnum, UniqueConstraint,
)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.database import Base
from app.models.enums import LegalStatus, PatentType, RiskLevel


class PatentFamily(Base):
    __tablename__ = "patent_families"

    id = Column(Integer, primary_key=True, index=True)
    family_id = Column(String(100), unique=True, nullable=False)
    family_type = Column(String(50), default="simple")
    priority_number = Column(String(100))
    priority_date = Column(Date)
    priority_country = Column(String(10))
    description = Column(Text)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    patents = relationship("Patent", back_populates="family")


class Citation(Base):
    __tablename__ = "citations"

    id = Column(Integer, primary_key=True, index=True)
    citing_patent_id = Column(Integer, ForeignKey("patents.id"), nullable=False)
    cited_patent_id = Column(Integer, ForeignKey("patents.id"), nullable=False)
    citation_type = Column(String(50), default="citation")
    created_at = Column(DateTime, server_default=func.now())

    citing = relationship("Patent", foreign_keys=[citing_patent_id], back_populates="citing_patents")
    cited = relationship("Patent", foreign_keys=[cited_patent_id], back_populates="cited_patents")


class Patent(Base):
    __tablename__ = "patents"

    id = Column(Integer, primary_key=True, index=True)

    # 著录项目
    application_number = Column(String(100), index=True)
    publication_number = Column(String(100), index=True)
    grant_number = Column(String(100))
    title = Column(Text, nullable=False)
    abstract = Column(Text)
    claims = Column(Text)
    description_full = Column(Text)

    applicant = Column(String(500))
    inventor = Column(String(500))
    assignee = Column(String(500))
    agent = Column(String(200))

    filing_date = Column(Date)
    publication_date = Column(Date)
    grant_date = Column(Date)
    priority_date = Column(Date)
    priority_number = Column(String(100))
    priority_country = Column(String(10))

    country = Column(String(10), default="CN")
    patent_type = Column(SQLEnum(PatentType), default=PatentType.INVENTION)
    legal_status = Column(SQLEnum(LegalStatus), default=LegalStatus.UNKNOWN)
    legal_status_date = Column(Date)
    legal_status_details = Column(Text)

    ipc_main = Column(String(50))
    ipc_all = Column(Text)
    cpc_main = Column(String(50))
    cpc_all = Column(Text)

    # 库归属（P0-8 新增）：库是顶层品类容器
    database_id = Column(Integer, ForeignKey("patent_databases.id"), index=True, nullable=True)
    product_id = Column(Integer, ForeignKey("products.id"))
    family_id = Column(Integer, ForeignKey("patent_families.id"))

    # 业务标注
    category = Column(String(100))
    subcategory = Column(String(100))
    technical_problem = Column(Text)
    technical_effect = Column(Text)
    technical_solution = Column(Text)
    has_risk = Column(Boolean, default=False)
    risk_level = Column(SQLEnum(RiskLevel), default=RiskLevel.NONE)
    risk_description = Column(Text)
    module = Column(String(200))
    application_status = Column(String(50))
    scope_description = Column(Text)
    notes = Column(Text)

    # 扩展字段（Wiki 式持续增长）
    custom_fields = Column(JSON, default=dict)
    ai_fields = Column(JSON, default=dict)
    search_vector = Column(Text)

    # 来源信息
    source_batch_id = Column(Integer, ForeignKey("import_batches.id"))
    source_row = Column(Integer)
    external_id = Column(String(200))

    # 去重
    is_duplicate = Column(Boolean, default=False)
    duplicate_of = Column(Integer, ForeignKey("patents.id"))

    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    # 关系
    database = relationship("PatentDatabase", back_populates="patents")
    product = relationship("Product", back_populates="patents")
    family = relationship("PatentFamily", back_populates="patents")
    tags = relationship("Tag", secondary="patent_tags", back_populates="patents")
    projects = relationship("Project", secondary="patent_projects", back_populates="patents")
    citing_patents = relationship(
        "Citation", foreign_keys=[Citation.cited_patent_id], back_populates="cited"
    )
    cited_patents = relationship(
        "Citation", foreign_keys=[Citation.citing_patent_id], back_populates="citing"
    )
    source_batch = relationship("ImportBatch", back_populates="patents")
    duplicate_of_patent = relationship("Patent", remote_side=[id])
    # 修改历史
    histories = relationship("PatentHistory", back_populates="patent", cascade="all, delete-orphan", order_by="PatentHistory.id.desc()")

    __table_args__ = (
        UniqueConstraint("application_number", "country", name="_app_num_country_uc"),
        UniqueConstraint("publication_number", "country", name="_pub_num_country_uc"),
    )
