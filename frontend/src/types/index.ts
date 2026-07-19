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
  status: string
  total_items: number
  processed_items: number
  success_count: number
  failed_count: number
  started_at?: string
  completed_at?: string
}
