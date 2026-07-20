from datetime import datetime, date
from typing import Optional, Any
from pydantic import BaseModel, ConfigDict, Field, model_validator


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
    # P0-13：允许创建专利时直接指定库归属（之前 schema 漏掉此字段导致只能通过导入设置）
    database_id: Optional[int] = None
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


class BulkUpdateRequest(BaseModel):
    """P1-8：批量更新专利的请求体。

    主要路径：显式传 `updates` 字段。
    向后兼容：旧客户端若未用 `updates` 包装（直接把字段平铺到顶层），
    会通过 model_validator 把多余字段合并进 `updates`。
    """
    patent_ids: list[int]
    updates: Optional[dict[str, Any]] = None
    changed_by: Optional[str] = None
    source: Optional[str] = None  # HistorySource 字符串：manual/bulk/import/ai/...

    model_config = ConfigDict(extra="allow")

    @model_validator(mode="after")
    def _merge_extra_into_updates(self) -> "BulkUpdateRequest":
        """旧客户端可能直接把待更新字段平铺到 body（无 updates 包装），
        此处将额外字段合并到 updates，保持向后兼容。"""
        if self.updates is None:
            extras = self.__pydantic_extra__ or {}
            if extras:
                self.updates = dict(extras)
                self.__pydantic_extra__ = {}
        return self


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


class TagGroupUpdate(BaseSchema):
    name: Optional[str] = None
    description: Optional[str] = None
    color: Optional[str] = None


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


class PersonUpdate(BaseSchema):
    name: Optional[str] = None
    email: Optional[str] = None
    department_id: Optional[int] = None
    role: Optional[str] = None
    is_active: Optional[bool] = None
    notes: Optional[str] = None


class Person(PersonBase):
    id: int
    created_at: datetime


class DepartmentBase(BaseSchema):
    name: str
    description: Optional[str] = None


class DepartmentCreate(DepartmentBase):
    pass


class DepartmentUpdate(BaseSchema):
    name: Optional[str] = None
    description: Optional[str] = None


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


# ===== P0-13：部门级总表与小表（视图）相关 schema =====

# ----- P1-11：标准化 filter_config / column_config / sort_config 结构 -----
#
# filter_config 结构（dict[field_key, ViewFilterRule]）：
#   {
#     "title": {"contains": "电池"},
#     "legal_status": {"eq": "granted"},
#     "custom_fields.cf_xxx": {"contains": "锂"}
#   }
#
# column_config 结构（list[ViewColumnConfig]）：
#   - []  = 显示全部字段（白名单为空等价全选，部门总表强制为此值）
#   - 非空 = 白名单 + 排序 + 列宽（仅列出的字段会展示，order 升序）
#
# sort_config 结构（ViewSortConfig）：
#   {"sort_by": "filing_date", "sort_order": "desc"}


class ViewFilterRule(BaseSchema):
    """单字段筛选规则（P1-11 标准化）。

    - contains: 模糊匹配（字符串包含）
    - eq: 精确匹配
    - in_: 多值匹配（任一命中）
    - gte / lte: 范围匹配（用于日期/数字）
    """
    contains: Optional[Any] = None
    eq: Optional[Any] = None
    in_: Optional[list[Any]] = Field(default=None, alias="in")
    gte: Optional[Any] = None
    lte: Optional[Any] = None

    model_config = {"populate_by_name": True}


class ViewColumnConfig(BaseSchema):
    """视图列配置项（P1-11 标准化）。

    - key: 字段 key（系统字段名 / custom_fields.cf_xxx / view_local.vlf_xxx）
    - visible: 是否显示（False 时该列被隐藏，仅在"全部字段"模式下生效）
    - width: 列宽（像素）
    - order: 排序序号（升序，从 0 开始）
    - frozen: 是否冻结在左侧
    """
    key: str
    visible: Optional[bool] = True
    width: Optional[int] = None
    order: Optional[int] = 0
    frozen: Optional[bool] = False


class ViewSortConfig(BaseSchema):
    """视图排序配置（P1-11 标准化）。"""
    sort_by: Optional[str] = None
    sort_order: Optional[str] = "asc"  # asc / desc


class PatentViewBase(BaseSchema):
    name: str
    description: Optional[str] = None
    database_id: int
    view_type: Optional[str] = "personal"  # personal / shared / department_master
    # 标准化结构：filter_config={field_key: ViewFilterRule}, column_config=list[ViewColumnConfig]
    # 注：column_config=[] 表示"显示全部字段"（白名单为空 = 全选）
    filter_config: Optional[dict[str, Any]] = {}
    column_config: Optional[list[dict[str, Any]]] = []
    sort_config: Optional[dict[str, Any]] = {}


class PatentViewCreate(PatentViewBase):
    is_department_master: Optional[bool] = False


class PatentViewUpdate(BaseSchema):
    name: Optional[str] = None
    description: Optional[str] = None
    view_type: Optional[str] = None
    filter_config: Optional[dict[str, Any]] = None
    column_config: Optional[list[dict[str, Any]]] = None
    sort_config: Optional[dict[str, Any]] = None
    is_archived: Optional[bool] = None


class ViewLocalFieldBase(BaseSchema):
    key: str
    name: str
    field_type: str  # text/number/date/select/boolean/textarea
    options: Optional[list[str]] = None
    description: Optional[str] = None
    default_value: Optional[str] = None
    is_required: Optional[bool] = False
    sort_order: Optional[int] = 0


class ViewLocalFieldCreate(ViewLocalFieldBase):
    pass


class ViewLocalFieldUpdate(BaseSchema):
    name: Optional[str] = None
    field_type: Optional[str] = None
    options: Optional[list[str]] = None
    description: Optional[str] = None
    default_value: Optional[str] = None
    is_required: Optional[bool] = None
    sort_order: Optional[int] = None


class ViewLocalField(ViewLocalFieldBase):
    id: int
    view_id: int
    is_promoted: bool = False
    promoted_field_key: Optional[str] = None
    created_at: datetime
    updated_at: datetime


class PatentView(PatentViewBase):
    id: int
    owner_id: Optional[int] = None
    is_department_master: bool = False
    is_archived: bool = False
    created_at: datetime
    updated_at: datetime
    local_fields: list[ViewLocalField] = []


class ViewFieldValueUpdate(BaseSchema):
    """小表本地字段值更新请求。"""
    value: Optional[Any] = None
    changed_by: Optional[str] = None


class ViewPatentCellUpdate(BaseSchema):
    """在小表中编辑共享字段的请求（会写入大表并记录来源视图）。"""
    value: Optional[Any] = None
    changed_by: Optional[str] = None


class PromoteFieldRequest(BaseSchema):
    """将视图本地字段提升为全局 CustomField。"""
    global_name: Optional[str] = None  # 提升后的全局字段名（默认用原名）
    global_group: Optional[str] = "从小表提升"


class FieldSourceInfo(BaseSchema):
    """字段来源信息。"""
    field_key: str
    field_display_name: Optional[str] = None
    current_value: Optional[str] = None
    last_source: Optional[str] = None  # manual/import/ai/bulk/api
    last_changed_by: Optional[str] = None
    last_changed_at: Optional[datetime] = None
    last_source_view_id: Optional[int] = None
    last_source_view_name: Optional[str] = None


Patent.model_rebuild()
