export type JsonPrimitive = string | number | boolean | null
export type JsonValue = JsonPrimitive | JsonValue[] | { [key: string]: JsonValue }
export type JsonObject = { [key: string]: JsonValue | undefined }

export interface AIConfig extends JsonObject {
  ai_enabled?: boolean
  prompt_template?: string
}

export type FormulaReturnType = 'text' | 'number' | 'date' | 'boolean'

export interface FormulaConfig {
  expression: string
  return_type: FormulaReturnType
}

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
  custom_fields?: JsonObject
  ai_fields?: JsonObject
  // P2-8：同族聚拢相关
  family_id?: number | null
  family_size?: number | null
  tags?: Tag[]
  projects?: Project[]
  created_at: string
  updated_at: string
}

export interface PatentShare {
  id: number
  patent_id: number
  token: string
  title_override?: string | null
  is_active: boolean
  expires_at?: string | null
  access_count: number
  last_accessed_at?: string | null
  created_at?: string | null
  updated_at?: string | null
  share_path: string
}

export interface PublicPatent {
  id: number
  title: string
  application_number?: string | null
  publication_number?: string | null
  grant_number?: string | null
  applicant?: string | null
  inventor?: string | null
  assignee?: string | null
  agent?: string | null
  filing_date?: string | null
  publication_date?: string | null
  grant_date?: string | null
  priority_date?: string | null
  priority_number?: string | null
  priority_country?: string | null
  country?: string | null
  patent_type?: string | null
  legal_status?: string | null
  legal_status_date?: string | null
  ipc_main?: string | null
  ipc_all?: string | null
  cpc_main?: string | null
  cpc_all?: string | null
  abstract?: string | null
  category?: string | null
  subcategory?: string | null
  module?: string | null
  technical_problem?: string | null
  technical_solution?: string | null
  technical_effect?: string | null
  scope_description?: string | null
  claims?: string | null
  has_risk?: boolean | null
  risk_level?: string | null
  risk_description?: string | null
  tags: { id: number; name: string; color?: string | null }[]
  projects: { id: number; name: string }[]
}

export interface PublicPatentShare {
  share: PatentShare
  patent: PublicPatent
}

export interface SearchSuggestion {
  kind: string
  kind_label: string
  value: string
  label: string
  patent_id: number
  patent_title: string
}

export interface PatentGraphNode {
  id: string
  patent_id: number
  kind: 'root' | 'family' | 'citation' | string
  label: string
  title: string
  number: string
  is_placeholder: boolean
}

export interface PatentGraphEdge {
  id: string
  source: string
  target: string
  relation: 'family' | 'citation' | string
  label: string
}

export interface PatentGraphResponse {
  root_id: number
  depth: number
  nodes: PatentGraphNode[]
  edges: PatentGraphEdge[]
  counts: {
    nodes: number
    edges: number
    family_edges: number
    citation_edges: number
  }
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

export type ViewLayoutType = 'table' | 'kanban' | 'form' | 'gantt' | 'calendar'

export interface ViewGroupField {
  field: string
  direction?: 'asc' | 'desc'
  collapsed?: boolean
}

export interface ConditionalFormatCondition {
  op: string
  value?: JsonValue
  unit?: 'day' | 'week' | 'month'
  style?: {
    bgColor?: string
    color?: string
    fontWeight?: string | number
    fontStyle?: string
    textDecoration?: string
    opacity?: number
  }
}

export interface ConditionalFormatRule {
  id: string
  field: string
  conditions: ConditionalFormatCondition[]
}

export interface ViewGroup {
  key: JsonValue
  label: string
  field: string
  count: number
  collapsed: boolean
  subgroups?: ViewGroup[]
  patents?: Patent[]
}

export interface GroupedViewResponse {
  view_id: number
  total: number
  page: number
  page_size: number
  groups: ViewGroup[]
  group_by_config: { fields: ViewGroupField[] }
  conditional_formatting: ConditionalFormatRule[]
}

export interface PatentView {
  id: number
  name: string
  description?: string
  database_id: number
  // view_type 表示可见范围；layout_type 表示展示形态。
  view_type: 'personal' | 'shared' | 'department_master' | string
  layout_type: ViewLayoutType
  is_department_master?: boolean
  is_archived?: boolean
  filter_config?: JsonObject
  column_config?: { key: string; visible?: boolean; width?: number; order?: number }[]
  sort_config?: { sort_by?: string; sort_order?: 'asc' | 'desc' }
  group_by_config?: { fields?: ViewGroupField[] } | JsonObject
  conditional_formatting?: ConditionalFormatRule[]
  kanban_config?: JsonObject
  form_config?: JsonObject
  gantt_config?: JsonObject
  local_fields?: ViewLocalField[]
  created_at?: string
  updated_at?: string
}

export interface KanbanConfig {
  group_by_field: string
  group_values?: JsonValue[]
  card_fields: string[]
  card_title_field: string
}

export interface KanbanCard {
  id: number
  title: string
  group_value: JsonValue
  fields: JsonObject
}

export interface KanbanGroup {
  key: JsonValue
  label: string
  count: number
  cards: KanbanCard[]
}

export interface KanbanResponse {
  view_id: number
  total: number
  returned: number
  truncated: boolean
  group_by_field: string
  config: KanbanConfig
  groups: KanbanGroup[]
}

export interface FormFieldConfig {
  key: string
  required?: boolean
  col_span?: number
  default?: JsonValue
  visible_when?: JsonObject
}

export interface FormSectionConfig {
  title: string
  fields: FormFieldConfig[]
  visible_when?: JsonObject
}

export interface FormConfig {
  layout: 'single_column' | 'two_column'
  submit_label: string
  sections: FormSectionConfig[]
}

export interface FormFieldMeta {
  key: string
  name: string
  field_type: string
  options?: string[] | null
  description?: string | null
  is_required?: boolean
}

export interface FormDefinition {
  view_id: number
  view_name: string
  database_id: number
  config: FormConfig
  fields: FormFieldMeta[]
  public: boolean
}

export interface FormShareLink {
  id: number
  view_id: number
  token: string
  is_active: boolean
  expires_at?: string | null
  created_at?: string | null
}

export type GanttTimeScale = 'day' | 'week' | 'month' | 'quarter' | 'year'

export interface GanttConfig {
  start_field: string
  end_field: string
  title_field: string
  group_by_field?: string
  time_scale: GanttTimeScale
  bar_color_field?: string
  bar_color_map?: Record<string, string>
}

export interface GanttItem {
  id: number
  title: string
  start: string
  end: string
  color: string
}

export interface GanttGroup {
  key: JsonValue
  label: string
  items: GanttItem[]
}

export interface GanttResponse {
  view_id: number
  total: number
  returned: number
  truncated: boolean
  config: GanttConfig
  groups: GanttGroup[]
  time_range: { start: string | null; end: string | null }
}

export interface ViewLocalField {
  id: number
  view_id: number
  key: string
  name: string
  field_type: string
  options?: string[]
  is_promoted?: boolean
  promoted_field_key?: string
}

export interface ViewPatentListResponse {
  total: number
  items: (Patent & { view_local_fields?: Record<string, string | null> })[]
  page: number
  page_size: number
  view_id: number
  view_filter_config?: JsonObject
  view_column_config?: PatentView['column_config']
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

export interface ProductLine {
  id: number
  name: string
  code?: string
  description?: string
  created_at?: string
  updated_at?: string
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
  ai_config?: AIConfig
  formula_config?: FormulaConfig
  link_config?: LinkConfig
  lookup_config?: LookupConfig
  rollup_config?: RollupConfig
  created_at: string
  updated_at: string
}

export interface LinkConfig {
  target_table: 'patents' | 'projects' | 'products' | 'people' | 'departments' | 'product-lines' | 'tags' | string
  display_field?: string
  allow_multiple?: boolean
}

export interface LookupConfig {
  link_field_key: string
  source_field: string
  allow_multiple?: boolean
}

export interface RollupConfig {
  link_field_key: string
  source_field?: string
  aggregation: 'COUNT' | 'SUM' | 'AVG' | 'MIN' | 'MAX'
}

export interface LinkRecord {
  id: number
  field_key: string
  source_table: string
  source_record_id: number
  target_table: string
  target_record_id: number
  label: string
  created_at?: string
}

export interface LinkTarget {
  id: number
  label: string
  target_table: string
}

export interface RelationBatchItem {
  record_id: number
  links?: LinkRecord[]
  value?: JsonValue
  aggregation?: string
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
  errors?: JsonObject[]
  started_at?: string
  completed_at?: string
  created_at: string
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
  batch_id?: number | null
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
  created_at?: string
  updated_at?: string
}

export interface Department {
  id: number
  name: string
  description?: string
  members?: Person[]
  created_at?: string
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
  errors?: AITaskError[] | null
  started_at?: string
  completed_at?: string
  created_at?: string
}

export interface AIFieldValue {
  field_key: string
  value: JsonValue | null
  generated_value: JsonValue | null
  is_overridden: boolean
  overridden_at?: string | null
  updated_at?: string | null
}

export interface FieldMeta {
  key: string
  name: string
  field_type: 'text' | 'longtext' | 'number' | 'date' | 'select' | 'multiselect' | 'boolean' | 'link' | 'lookup' | 'rollup' | 'formula' | 'textarea' | 'ai_field' | 'multi_select' | 'url' | 'rating'
  group_name: string
  options?: string[] | null
  width?: number
  sortable?: boolean
  filterable?: boolean
  editable?: boolean
  frozen?: boolean
  visible?: boolean
  is_system?: boolean
  ai_config?: AIConfig | null
  formula_config?: FormulaConfig | null
  is_formula?: boolean
  dependencies?: string[]
  link_config?: LinkConfig | null
  lookup_config?: LookupConfig | null
  rollup_config?: RollupConfig | null
}

export interface CellUpdateRequest {
  value: JsonValue
}

// 专利修改历史
export interface PatentHistory {
  id: number
  patent_id: number
  field_key: string
  field_display_name?: string
  old_value?: string | null
  new_value?: string | null
  source: string  // manual / bulk / ai / import / api
  changed_by?: string | null
  created_at?: string
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
  value?: JsonValue
}

export interface AITaskError {
  patent_id?: number
  error?: string
}

export interface AnalyticsDimensionItem {
  value: string
  count: number
  percentage: number
}

export interface AgentAnalysisResult {
  requirement: string
  base_stats: {
    total: number
    summary: string
    dimensions: Record<string, AnalyticsDimensionItem[]>
    filing_trend: { year: string; count: number }[]
  }
  ai_analysis: {
    overview: string
    key_findings: string[]
    dimension_analysis: Record<string, string>
    anomalies: string[]
    recommendations: string[]
    risk_warnings: string[]
  }
  created_at: string
}
