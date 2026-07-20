from datetime import datetime, date
from typing import Optional, Any
from pydantic import BaseModel, ConfigDict


class BaseSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class PatentBase(BaseSchema):
    application_number: Optional[str] = None
    publication_number: Optional[str] = None
    grant_number: Optional[str] = None
    title: str
    abstract: Optional[str] = None
    claims: Optional[str] = None
    description_full: Optional[str] = None
    applicant: Optional[str] = None
    inventor: Optional[str] = None
    assignee: Optional[str] = None
    agent: Optional[str] = None
    filing_date: Optional[date] = None
    publication_date: Optional[date] = None
    grant_date: Optional[date] = None
    priority_date: Optional[date] = None
    priority_number: Optional[str] = None
    priority_country: Optional[str] = None
    country: Optional[str] = "CN"
    patent_type: Optional[str] = "invention"
    legal_status: Optional[str] = "unknown"
    legal_status_date: Optional[date] = None
    legal_status_details: Optional[str] = None
    ipc_main: Optional[str] = None
    ipc_all: Optional[str] = None
    cpc_main: Optional[str] = None
    cpc_all: Optional[str] = None
    product_id: Optional[int] = None
    category: Optional[str] = None
    subcategory: Optional[str] = None
    technical_problem: Optional[str] = None
    technical_effect: Optional[str] = None
    technical_solution: Optional[str] = None
    has_risk: Optional[bool] = False
    risk_level: Optional[str] = "none"
    risk_description: Optional[str] = None
    module: Optional[str] = None
    application_status: Optional[str] = None
    scope_description: Optional[str] = None
    notes: Optional[str] = None
    custom_fields: Optional[dict[str, Any]] = {}


class PatentCreate(PatentBase):
    pass


class PatentUpdate(BaseSchema):
    title: Optional[str] = None
    abstract: Optional[str] = None
    claims: Optional[str] = None
    description_full: Optional[str] = None
    applicant: Optional[str] = None
    inventor: Optional[str] = None
    assignee: Optional[str] = None
    agent: Optional[str] = None
    filing_date: Optional[date] = None
    publication_date: Optional[date] = None
    grant_date: Optional[date] = None
    legal_status: Optional[str] = None
    legal_status_date: Optional[date] = None
    ipc_main: Optional[str] = None
    product_id: Optional[int] = None
    category: Optional[str] = None
    subcategory: Optional[str] = None
    technical_problem: Optional[str] = None
    technical_effect: Optional[str] = None
    technical_solution: Optional[str] = None
    has_risk: Optional[bool] = None
    risk_level: Optional[str] = None
    risk_description: Optional[str] = None
    module: Optional[str] = None
    application_status: Optional[str] = None
    scope_description: Optional[str] = None
    notes: Optional[str] = None
    custom_fields: Optional[dict[str, Any]] = None
    tag_ids: Optional[list[int]] = None
    project_ids: Optional[list[int]] = None


class Patent(PatentBase):
    id: int
    created_at: datetime
    updated_at: datetime
    ai_fields: Optional[dict[str, Any]] = {}
    tags: list["Tag"] = []
    projects: list["Project"] = []


class PatentListResponse(BaseSchema):
    total: int
    items: list[Patent]
    page: int
    page_size: int


class ProductBase(BaseSchema):
    name: str
    code: Optional[str] = None
    product_line_id: Optional[int] = None
    owner_id: Optional[int] = None
    description: Optional[str] = None
    category: Optional[str] = None
    is_active: Optional[bool] = True


class ProductCreate(ProductBase):
    pass


class ProductUpdate(BaseSchema):
    name: Optional[str] = None
    code: Optional[str] = None
    product_line_id: Optional[int] = None
    owner_id: Optional[int] = None
    description: Optional[str] = None
    category: Optional[str] = None
    is_active: Optional[bool] = None


class Product(ProductBase):
    id: int
    created_at: datetime
    updated_at: datetime
    patent_count: Optional[int] = 0


class ProjectBase(BaseSchema):
    name: str
    code: Optional[str] = None
    product_id: Optional[int] = None
    description: Optional[str] = None
    module: Optional[str] = None
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    status: Optional[str] = "active"


class ProjectCreate(ProjectBase):
    pass


class ProjectUpdate(BaseSchema):
    name: Optional[str] = None
    code: Optional[str] = None
    product_id: Optional[int] = None
    description: Optional[str] = None
    module: Optional[str] = None
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    status: Optional[str] = None


class Project(ProjectBase):
    id: int
    created_at: datetime
    updated_at: datetime
    patent_count: Optional[int] = 0


class TagBase(BaseSchema):
    name: str
    group_id: Optional[int] = None
    color: Optional[str] = None
    description: Optional[str] = None


class TagCreate(TagBase):
    pass


class TagUpdate(BaseSchema):
    name: Optional[str] = None
    group_id: Optional[int] = None
    color: Optional[str] = None
    description: Optional[str] = None


class Tag(TagBase):
    id: int
    created_at: datetime


class TagGroupBase(BaseSchema):
    name: str
    description: Optional[str] = None
    color: Optional[str] = None


class TagGroupCreate(TagGroupBase):
    pass


class TagGroup(TagGroupBase):
    id: int
    tags: list[Tag] = []


class CustomFieldBase(BaseSchema):
    key: str
    name: str
    field_type: str
    group_name: Optional[str] = "默认"
    description: Optional[str] = None
    options: Optional[list[str]] = None
    default_value: Optional[str] = None
    is_required: Optional[bool] = False
    is_active: Optional[bool] = True
    sort_order: Optional[int] = 0
    ai_config: Optional[dict[str, Any]] = None


class CustomFieldCreate(CustomFieldBase):
    pass


class CustomFieldUpdate(BaseSchema):
    name: Optional[str] = None
    field_type: Optional[str] = None
    group_name: Optional[str] = None
    description: Optional[str] = None
    options: Optional[list[str]] = None
    default_value: Optional[str] = None
    is_required: Optional[bool] = None
    is_active: Optional[bool] = None
    sort_order: Optional[int] = None
    ai_config: Optional[dict[str, Any]] = None


class CustomField(CustomFieldBase):
    id: int
    created_at: datetime
    updated_at: datetime


# P0-8：库（PatentDatabase）相关 schema
class PatentDatabaseBase(BaseSchema):
    name: str
    code: Optional[str] = None
    description: Optional[str] = None
    color: Optional[str] = None
    icon: Optional[str] = None
    sort_order: Optional[int] = 0


class PatentDatabaseCreate(PatentDatabaseBase):
    pass


class PatentDatabaseUpdate(BaseSchema):
    name: Optional[str] = None
    description: Optional[str] = None
    color: Optional[str] = None
    icon: Optional[str] = None
    sort_order: Optional[int] = None


class PatentDatabase(PatentDatabaseBase):
    id: int
    is_default: Optional[bool] = False
    is_archived: Optional[bool] = False
    patent_count: Optional[int] = 0
    created_at: datetime
    updated_at: datetime


class PersonBase(BaseSchema):
    name: str
    email: Optional[str] = None
    department_id: Optional[int] = None
    role: Optional[str] = None
    is_active: Optional[bool] = True
    notes: Optional[str] = None


class PersonCreate(PersonBase):
    pass


class Person(PersonBase):
    id: int
    created_at: datetime


class DepartmentBase(BaseSchema):
    name: str
    description: Optional[str] = None


class DepartmentCreate(DepartmentBase):
    pass


class Department(DepartmentBase):
    id: int
    members: list[Person] = []


class ProductLineBase(BaseSchema):
    name: str
    code: Optional[str] = None
    description: Optional[str] = None


class ProductLineCreate(ProductLineBase):
    pass


class ProductLine(ProductLineBase):
    id: int


class ImportPreviewResponse(BaseSchema):
    columns: list[str]
    sample_rows: list[dict[str, Any]]
    total_rows: int
    suggested_mapping: dict[str, str]


class FieldMappingConfig(BaseSchema):
    name: Optional[str] = None
    mapping: dict[str, str]
    options: Optional[dict[str, Any]] = {}


class ImportRequest(BaseSchema):
    mapping_id: Optional[int] = None
    mapping: dict[str, str]
    options: Optional[dict[str, Any]] = {}
    product_id: Optional[int] = None


class ImportBatchResponse(BaseSchema):
    id: int
    filename: str
    status: str
    total_rows: int
    processed_rows: int
    inserted_count: int
    updated_count: int
    duplicate_count: int
    error_count: int
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    created_at: datetime


class AIProcessRequest(BaseSchema):
    patent_ids: list[int]
    field_key: str
    model: Optional[str] = None
    force_recalculate: Optional[bool] = False


class AITaskResponse(BaseSchema):
    id: int
    task_type: str
    field_key: Optional[str]
    status: str
    total_items: int
    processed_items: int
    success_count: int
    failed_count: int
    started_at: Optional[datetime]
    completed_at: Optional[datetime]


class StatsResponse(BaseSchema):
    total_patents: int
    by_legal_status: dict[str, int]
    by_patent_type: dict[str, int]
    by_product: list[dict[str, Any]]
    by_category: dict[str, int]
    by_risk_level: dict[str, int]
    top_inventors: list[dict[str, Any]]
    top_applicants: list[dict[str, Any]]
    filing_trend: list[dict[str, Any]]
    top_ipcs: list[dict[str, Any]] = []
    by_country: dict[str, int] = {}


Patent.model_rebuild()
