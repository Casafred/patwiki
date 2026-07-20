export interface Patent {
  id: number
  application_number?: string
  publication_number?: string
  grant_number?: string
  title: string
  abstract?: string
  claims?: string
  applicant?: string
  inventor?: string
  assignee?: string
  agent?: string
  filing_date?: string
  publication_date?: string
  grant_date?: string
  priority_date?: string
  priority_number?: string
  priority_country?: string
  country?: string
  patent_type?: string
  legal_status?: string
  legal_status_date?: string
  ipc_main?: string
  ipc_all?: string
  cpc_main?: string
  cpc_all?: string
  database_id?: number
  product_id?: number
  category?: string
  subcategory?: string
  technical_problem?: string
  technical_effect?: string
  technical_solution?: string
  has_risk?: boolean
  risk_level?: string
  risk_description?: string
  module?: string
  application_status?: string
  scope_description?: string
  notes?: string
  custom_fields?: Record<string, any>
  ai_fields?: Record<string, any>
  tags?: Tag[]
  projects?: Project[]
  created_at: string
  updated_at: string
}

// P0-8：库（PatentDatabase）类型
export interface PatentDatabase {
  id: number
  name: string
  code?: string
  description?: string
  color?: string
  icon?: string
  is_default?: boolean
  is_archived?: boolean
  patent_count?: number
  sort_order?: number
  created_at?: string
  updated_at?: string
}

export interface PatentListResponse {
  total: number
  items: Patent[]
  page: number
  page_size: number
}

export interface Product {
  id: number
  name: string
  code?: string
  product_line_id?: number
  owner_id?: number
  description?: string
  category?: string
  is_active?: boolean
  patent_count?: number
  created_at: string
  updated_at: string
}

export interface Project {
  id: number
  name: string
  code?: string
  product_id?: number
  description?: string
  module?: string
  start_date?: string
  end_date?: string
  status?: string
  patent_count?: number
  created_at: string
  updated_at: string
}

export interface Tag {
  id: number
  name: string
  group_id?: number
  color?: string
  description?: string
  created_at: string
}

export interface TagGroup {
  id: number
  name: string
  description?: string
  color?: string
  tags?: Tag[]
}

export interface CustomField {
  id: number
  key: string
  name: string
  field_type: string
  group_name?: string
  description?: string
  options?: string[]
  default_value?: string
  is_required?: boolean
  is_active?: boolean
  sort_order?: number
  ai_config?: Record<string, any>
  created_at: string
  updated_at: string
}

export interface ImportBatch {
  id: number
  filename: string
  status: string
  total_rows: number
  processed_rows: number
  inserted_count: number
  updated_count: number
  duplicate_count: number
  skipped_count: number
  error_count: number
  view_local_written?: number
  dedupe_by?: string
  database_id?: number | null
  view_id?: number | null
  started_at?: string
  completed_at?: string
  created_at: string
  errors?: any[]
}

export interface ImportPreview {
  import_id: string
  detected_columns: string[]
  preview_rows: Record<string, string>[]
  total_rows: number
  suggested_mapping: Record<string, string>
  // P0-11：返回库列表供选择
  databases?: PatentDatabase[]
  default_database_id?: number | null
}

export interface FieldMapping {
  source_column: string
  target_field: string
}

export interface ImportResult {
  total: number
  created: number
  updated: number
  skipped: number
  errors: number
  error_details?: { row: number; error: string }[]
  // P0-10：关系入库统计
  database_id?: number
  family_links?: number
  citation_links?: number
}

export interface Stats {
  total_patents: number
  by_legal_status: Record<string, number>
  by_patent_type: Record<string, number>
  by_product: { id: number; name: string; count: number }[]
  by_category: Record<string, number>
  by_risk_level: Record<string, number>
  top_inventors: { name: string; count: number }[]
  top_applicants: { name: string; count: number }[]
  filing_trend: { year: string; count: number }[]
  top_ipcs?: { code: string; count: number }[]
  by_country?: Record<string, number>
}

export interface Person {
  id: number
  name: string
  email?: string
  department_id?: number
  role?: string
  is_active?: boolean
  notes?: string
}

export interface Department {
  id: number
  name: string
  description?: string
  members?: Person[]
}

export interface AITask {
  id: number
  task_type: string
  field_key?: string
  model_name?: string
  status: string
  total_items: number
  processed_items: number
  success_count: number
  failed_count: number
  errors?: any[] | null
  started_at?: string
  completed_at?: string
  created_at?: string
}

export interface FieldMeta {
  key: string
  name: string
  field_type: 'text' | 'longtext' | 'number' | 'date' | 'select' | 'multiselect' | 'boolean' | 'link' | 'textarea' | 'ai_field' | 'multi_select' | 'url' | 'rating'
  group_name: string
  options?: string[] | null
  width?: number
  sortable?: boolean
  filterable?: boolean
  editable?: boolean
  frozen?: boolean
  visible?: boolean
  is_system?: boolean
  ai_config?: Record<string, any> | null
}

export interface CellUpdateRequest {
  value: any
  changed_by?: string
  source_view_id?: number
}

// 专利修改历史
export interface PatentHistory {
  id: number
  patent_id: number
  field_key: string
  field_display_name?: string
  old_value?: string | null
  new_value?: string | null
  source: string  // manual / view_edit / import / ai / promote / bulk / api
  changed_by?: string | null
  source_view_id?: number | null
  source_view_name?: string | null
  created_at?: string
}

// 字段来源追溯（P0-13）
export interface FieldSource {
  field_key: string
  field_display_name?: string
  current_value?: any
  last_source?: string  // manual / view_edit / import / ai / promote / bulk / api
  last_changed_by?: string | null
  last_changed_at?: string | null
  source_view_id?: number | null
  source_view_name?: string | null
  // 该字段是否为视图本地字段（仅 view_local_sources 中存在）
  view_local?: boolean
  view_id?: number | null
  is_promoted?: boolean
  promoted_field_key?: string | null
}

// P2-3：AI 字段值（含人工覆盖状态）
export interface AIFieldValueInfo {
  id: number
  field_key: string
  field_name: string
  ai_value: string | null
  model_name?: string | null
  is_overridden: boolean
  display_value: string | null
  overridden_value: string | null
  overridden_at: string | null
  created_at?: string
  updated_at?: string
}

// ============================================================
// P0-13/P0-14：视图（小表 / 部门总表）
// ============================================================

export type ViewType = 'personal' | 'shared' | 'department_master'

// 视图筛选规则（P1-11 标准化）
export interface ViewFilterRule {
  contains?: any
  eq?: any
  in?: any[]
  gte?: any
  lte?: any
}

// 视图列配置（P1-11 标准化）
// column_config=[] 表示"显示全部字段"（白名单空 = 全选）
// 非空数组 = 白名单 + 顺序 + 列宽
export interface ViewColumnConfig {
  key: string
  visible?: boolean
  width?: number
  order?: number
  frozen?: boolean
}

// 视图排序配置（P1-11 标准化）
export interface ViewSortConfig {
  sort_by?: string
  sort_order?: 'asc' | 'desc'
}

// 视图本地字段（vlf_ 前缀）
export interface ViewLocalField {
  id: number
  view_id: number
  key: string  // vlf_xxx
  name: string
  field_type: string
  options?: string[] | null
  description?: string | null
  default_value?: string | null
  is_required?: boolean
  sort_order?: number
  is_promoted?: boolean
  promoted_field_key?: string | null
  created_at?: string
  updated_at?: string
}

// 视图本体
export interface PatentView {
  id: number
  name: string
  description?: string | null
  database_id: number
  owner_id?: number | null
  view_type: ViewType
  is_department_master?: boolean
  filter_config?: Record<string, ViewFilterRule>
  column_config?: ViewColumnConfig[]
  sort_config?: ViewSortConfig
  is_archived?: boolean
  local_fields?: ViewLocalField[]
  created_at?: string
  updated_at?: string
}

// 视图内单条专利 = 大表专利 + 本地字段值
export interface ViewPatent extends Patent {
  view_local_fields?: Record<string, any>  // vlf_key -> value
}

export interface ViewPatentListResponse {
  total: number
  items: ViewPatent[]
  page: number
  page_size: number
  view_id: number
  view_filter_config?: Record<string, ViewFilterRule>
  view_column_config?: ViewColumnConfig[]
}

// 字段来源类型常量（与后端 HistorySource 枚举一致）
export const HISTORY_SOURCES = {
  MANUAL: 'manual',
  VIEW_EDIT: 'view_edit',
  IMPORT: 'import',
  AI: 'ai',
  PROMOTE: 'promote',
  BULK: 'bulk',
  API: 'api',
} as const

export type HistorySource = typeof HISTORY_SOURCES[keyof typeof HISTORY_SOURCES]

// 字段来源元数据（P1-12：get_all_fields_meta 支持 view_id 后的扩展字段）
export interface FieldMetaWithView extends FieldMeta {
  source?: 'system' | 'custom' | 'view_local' | 'ai'
  view_id?: number | null
  view_name?: string | null
  is_promoted?: boolean
  promoted_from_view_id?: number | null
  promoted_from_view_name?: string | null
  promoted_field_key?: string | null
}

// ============================================================
// 权限管理与协作
// ============================================================
export interface User {
  id: number
  username: string
  display_name?: string
  email?: string
  role: string  // admin / member
  is_active: boolean
  created_at?: string
}

export interface DatabaseMember {
  id: number
  user_id: number
  username: string
  display_name?: string
  role: string  // owner / editor / viewer
  created_at?: string
}

export interface SharedDatabase extends PatentDatabase {
  my_role?: string
  owner_id?: number
}

export type FilterCondition = {
  field: string
  operator: 'eq' | 'contains' | 'gt' | 'lt' | 'gte' | 'lte' | 'in' | 'is_empty' | 'is_not_empty'
  value?: any
}
