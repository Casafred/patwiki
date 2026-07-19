from datetime import datetime
from sqlalchemy import (
    Column, Integer, String, Text, Date, DateTime, Boolean,
    ForeignKey, JSON, Float, Enum as SQLEnum, Table, UniqueConstraint
)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
import enum

from app.database import Base


class LegalStatus(str, enum.Enum):
    PENDING = "pending"
    PUBLISHED = "published"
    EXAMINING = "examining"
    GRANTED = "granted"
    REJECTED = "rejected"
    WITHDRAWN = "withdrawn"
    DEEMED_WITHDRAWN = "deemed_withdrawn"
    EXPIRED = "expired"
    ABANDONED = "abandoned"
    UNKNOWN = "unknown"


class PatentType(str, enum.Enum):
    INVENTION = "invention"
    UTILITY_MODEL = "utility_model"
    DESIGN = "design"
    PCT = "pct"


class ProjectRole(str, enum.Enum):
    CORE = "core"
    APPLIED = "applied"
    RISK = "risk"
    REFERENCE = "reference"
    PERIPHERAL = "peripheral"
    DEFENSIVE = "defensive"


class RiskLevel(str, enum.Enum):
    NONE = "none"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class ImportBatchStatus(str, enum.Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    ROLLED_BACK = "rolled_back"


patent_tag = Table(
    "patent_tags",
    Base.metadata,
    Column("patent_id", Integer, ForeignKey("patents.id"), primary_key=True),
    Column("tag_id", Integer, ForeignKey("tags.id"), primary_key=True),
    Column("created_at", DateTime, server_default=func.now()),
)


patent_project = Table(
    "patent_projects",
    Base.metadata,
    Column("patent_id", Integer, ForeignKey("patents.id"), primary_key=True),
    Column("project_id", Integer, ForeignKey("projects.id"), primary_key=True),
    Column("role", SQLEnum(ProjectRole), default=ProjectRole.REFERENCE),
    Column("notes", Text),
    Column("created_at", DateTime, server_default=func.now()),
    Column("updated_at", DateTime, server_default=func.now(), onupdate=func.now()),
)


class Department(Base):
    __tablename__ = "departments"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), unique=True, nullable=False)
    description = Column(Text)
    created_at = Column(DateTime, server_default=func.now())

    members = relationship("Person", back_populates="department")


class Person(Base):
    __tablename__ = "people"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), nullable=False)
    email = Column(String(255))
    department_id = Column(Integer, ForeignKey("departments.id"))
    role = Column(String(100))
    is_active = Column(Boolean, default=True)
    notes = Column(Text)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    department = relationship("Department", back_populates="members")
    owned_products = relationship("Product", back_populates="owner")


class ProductLine(Base):
    __tablename__ = "product_lines"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(200), unique=True, nullable=False)
    description = Column(Text)
    code = Column(String(50), unique=True)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    products = relationship("Product", back_populates="product_line")


class Product(Base):
    __tablename__ = "products"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(200), nullable=False)
    code = Column(String(50))
    product_line_id = Column(Integer, ForeignKey("product_lines.id"))
    owner_id = Column(Integer, ForeignKey("people.id"))
    description = Column(Text)
    category = Column(String(100))
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    product_line = relationship("ProductLine", back_populates="products")
    owner = relationship("Person", back_populates="owned_products")
    projects = relationship("Project", back_populates="product")
    patents = relationship("Patent", back_populates="product")


class Project(Base):
    __tablename__ = "projects"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(200), nullable=False)
    code = Column(String(50))
    product_id = Column(Integer, ForeignKey("products.id"))
    description = Column(Text)
    module = Column(String(200))
    start_date = Column(Date)
    end_date = Column(Date)
    status = Column(String(50), default="active")
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    product = relationship("Product", back_populates="projects")
    patents = relationship("Patent", secondary=patent_project, back_populates="projects")


class TagGroup(Base):
    __tablename__ = "tag_groups"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), unique=True, nullable=False)
    description = Column(Text)
    color = Column(String(20))
    created_at = Column(DateTime, server_default=func.now())

    tags = relationship("Tag", back_populates="group")


class Tag(Base):
    __tablename__ = "tags"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), nullable=False)
    group_id = Column(Integer, ForeignKey("tag_groups.id"))
    color = Column(String(20))
    description = Column(Text)
    created_at = Column(DateTime, server_default=func.now())

    group = relationship("TagGroup", back_populates="tags")
    patents = relationship("Patent", secondary=patent_tag, back_populates="tags")

    __table_args__ = (UniqueConstraint("name", "group_id", name="_tag_name_group_uc"),)


class CustomFieldType(str, enum.Enum):
    TEXT = "text"
    TEXTAREA = "textarea"
    NUMBER = "number"
    DATE = "date"
    BOOLEAN = "boolean"
    SELECT = "select"
    MULTI_SELECT = "multi_select"
    URL = "url"
    RATING = "rating"
    AI_FIELD = "ai_field"


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


class Citation(Base):
    __tablename__ = "citations"

    id = Column(Integer, primary_key=True, index=True)
    citing_patent_id = Column(Integer, ForeignKey("patents.id"), nullable=False)
    cited_patent_id = Column(Integer, ForeignKey("patents.id"), nullable=False)
    citation_type = Column(String(50), default="citation")
    created_at = Column(DateTime, server_default=func.now())

    citing = relationship("Patent", foreign_keys=[citing_patent_id], back_populates="citing_patents")
    cited = relationship("Patent", foreign_keys=[cited_patent_id], back_populates="cited_patents")


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


class Patent(Base):
    __tablename__ = "patents"

    id = Column(Integer, primary_key=True, index=True)

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

    product_id = Column(Integer, ForeignKey("products.id"))
    family_id = Column(Integer, ForeignKey("patent_families.id"))

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

    custom_fields = Column(JSON, default=dict)
    ai_fields = Column(JSON, default=dict)
    search_vector = Column(Text)

    source_batch_id = Column(Integer, ForeignKey("import_batches.id"))
    source_row = Column(Integer)
    external_id = Column(String(200))

    is_duplicate = Column(Boolean, default=False)
    duplicate_of = Column(Integer, ForeignKey("patents.id"))

    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    product = relationship("Product", back_populates="patents")
    family = relationship("PatentFamily", back_populates="patents")
    tags = relationship("Tag", secondary=patent_tag, back_populates="patents")
    projects = relationship("Project", secondary=patent_project, back_populates="patents")
    citing_patents = relationship(
        "Citation", foreign_keys=[Citation.cited_patent_id], back_populates="cited"
    )
    cited_patents = relationship(
        "Citation", foreign_keys=[Citation.citing_patent_id], back_populates="citing"
    )
    source_batch = relationship("ImportBatch", back_populates="patents")
    duplicate_of_patent = relationship("Patent", remote_side=[id])

    __table_args__ = (
        UniqueConstraint("application_number", "country", name="_app_num_country_uc"),
        UniqueConstraint("publication_number", "country", name="_pub_num_country_uc"),
    )


class FieldMapping(Base):
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

    mapping = relationship("FieldMapping")
    patents = relationship("Patent", back_populates="source_batch")


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
