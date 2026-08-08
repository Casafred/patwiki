import api from '../lib/api'
import type {
  Patent, PatentListResponse, Product, Project, Tag, TagGroup,
  CustomField, ImportBatch, ImportPreview, ImportResult, FieldMapping, Stats, Person, Department, ProductLine,
  AITask, AIFieldValue, FieldMeta, CellUpdateRequest, PatentDatabase,
  User, DatabaseMember, SharedDatabase, PatentHistory, PatentView, ViewPatentListResponse,
  GroupedViewResponse, ViewGroupField, ConditionalFormatRule, KanbanResponse, JsonObject, JsonValue,
  AgentAnalysisResult, LinkRecord, LinkTarget, RelationBatchItem,
} from '../types'

export const fieldApi = {
  list: (): Promise<FieldMeta[]> => api.get('/fields'),
}

// P0-11：库（Database）API
export const databaseApi = {
  list: (includeArchived = false): Promise<PatentDatabase[]> =>
    api.get('/databases', { params: { include_archived: includeArchived } }),

  getDefault: (): Promise<PatentDatabase> => api.get('/databases/default'),

  get: (id: number): Promise<PatentDatabase> => api.get(`/databases/${id}`),

  create: (data: { name: string; code?: string; description?: string; color?: string; icon?: string; owner_id?: number | null }): Promise<PatentDatabase> =>
    api.post('/databases', data),

  update: (id: number, data: Partial<PatentDatabase>): Promise<PatentDatabase> =>
    api.put(`/databases/${id}`, data),

  archive: (id: number): Promise<PatentDatabase> =>
    api.post(`/databases/${id}/archive`),

  delete: (id: number, force: boolean = false): Promise<{ success: boolean; force?: boolean; deleted_patent_count?: number }> =>
    api.delete(`/databases/${id}`, { params: { force } }),

  // 清空库内所有专利（不删库本身）
  clearPatents: (id: number): Promise<{ success: boolean; deleted_count: number }> =>
    api.delete(`/patents/by-database/${id}`),

  refreshCount: (id: number): Promise<{ success: boolean; patent_count: number }> =>
    api.post(`/databases/${id}/refresh-count`),

  // 设置/转移所有者
  setOwner: (id: number, userId: number): Promise<PatentDatabase> =>
    api.post(`/databases/${id}/set-owner`, { user_id: userId }),
}

export const linkApi = {
  create: (data: {
    field_key: string
    source_record_id: number
    target_record_id: number
    source_table?: string
    created_by?: string
  }): Promise<LinkRecord> => api.post('/links', data),

  delete: (data: {
    field_key: string
    source_record_id: number
    target_record_id: number
    source_table?: string
  }): Promise<{ success: boolean }> => api.delete('/links', { data }),

  list: (fieldKey: string, recordId: number, sourceTable = 'patents'): Promise<LinkRecord[]> =>
    api.get(`/links/${fieldKey}/${recordId}`, { params: { source_table: sourceTable } }),

  search: (fieldKey: string, search = '', limit = 50): Promise<LinkTarget[]> =>
    api.get('/links/search', { params: { field_key: fieldKey, search, limit } }),

  lookup: (fieldKey: string, recordId: number, sourceTable = 'patents'): Promise<{ field_key: string; record_id: number; value: JsonValue }> =>
    api.post('/lookup/resolve', { field_key: fieldKey, record_id: recordId, source_table: sourceTable }),

  rollup: (fieldKey: string, recordId: number, sourceTable = 'patents'): Promise<{ field_key: string; record_id: number; aggregation: string; value: JsonValue }> =>
    api.post('/rollup/resolve', { field_key: fieldKey, record_id: recordId, source_table: sourceTable }),

  batch: (fieldKey: string, recordIds: number[], sourceTable = 'patents'): Promise<RelationBatchItem[]> =>
    api.post('/relations/resolve-batch', { field_key: fieldKey, record_ids: recordIds, source_table: sourceTable }),
}

export const viewApi = {
  list: (databaseId: number, includeArchived = false): Promise<PatentView[]> =>
    api.get('/views', { params: { database_id: databaseId, include_archived: includeArchived } }),

  get: (id: number): Promise<PatentView> => api.get(`/views/${id}`),

  create: (data: {
    name: string
    database_id: number
    description?: string
    view_type?: PatentView['view_type']
    layout_type?: PatentView['layout_type']
    filter_config?: JsonObject
    column_config?: PatentView['column_config']
    sort_config?: PatentView['sort_config']
    group_by_config?: PatentView['group_by_config']
    conditional_formatting?: ConditionalFormatRule[]
    kanban_config?: PatentView['kanban_config']
    form_config?: PatentView['form_config']
    gantt_config?: PatentView['gantt_config']
  }): Promise<PatentView> => api.post('/views', data),

  update: (id: number, data: Partial<PatentView>): Promise<PatentView> =>
    api.put(`/views/${id}`, data),

  master: (databaseId: number): Promise<PatentView> =>
    api.get(`/databases/${databaseId}/master-view`),

  listPatents: (viewId: number, params: {
    page?: number
    page_size?: number
    search?: string
    sort_by?: string
    sort_order?: 'asc' | 'desc'
    extra_filters?: JsonObject
  } = {}): Promise<ViewPatentListResponse> => {
    const { extra_filters, ...query } = params
    return api.get(`/views/${viewId}/patents`, {
      params: {
        ...query,
        extra_filters: extra_filters && Object.keys(extra_filters).length > 0
          ? JSON.stringify(extra_filters)
          : undefined,
      },
    })
  },

  grouped: (viewId: number, params: {
    page?: number
    page_size?: number
    search?: string
    sort_by?: string
    sort_order?: 'asc' | 'desc'
    extra_filters?: JsonObject
  } = {}): Promise<GroupedViewResponse> => {
    const { extra_filters, ...query } = params
    return api.get(`/views/${viewId}/grouped`, {
      params: {
        ...query,
        extra_filters: extra_filters && Object.keys(extra_filters).length > 0
          ? JSON.stringify(extra_filters)
          : undefined,
      },
    })
  },

  updateGroupConfig: (viewId: number, config: { fields: ViewGroupField[] }): Promise<{
    success: boolean
    group_by_config: { fields: ViewGroupField[] }
  }> => api.put(`/views/${viewId}/group-config`, config),

  updateConditionalFormatting: (viewId: number, config: ConditionalFormatRule[]): Promise<{
    success: boolean
    conditional_formatting: ConditionalFormatRule[]
  }> => api.put(`/views/${viewId}/conditional-formatting`, config),

  kanban: (viewId: number, params: { page_size?: number; search?: string } = {}): Promise<KanbanResponse> =>
    api.get(`/views/${viewId}/kanban`, { params }),

  moveKanbanCard: (viewId: number, data: {
    patent_id: number
    to_value: JsonValue
    from_value?: JsonValue
    changed_by?: string
  }): Promise<{ success: boolean; patent_id: number; field_key: string; value: JsonValue }> =>
    api.post(`/views/${viewId}/kanban/move`, data),

  updateSharedField: (viewId: number, patentId: number, fieldKey: string, value: JsonValue): Promise<{
    success: boolean
    patent_id: number
    field_key: string
  }> => api.patch(`/views/${viewId}/patents/${patentId}/field/${fieldKey}`, { value }),
}

export const patentApi = {
  list: (params: JsonObject = {}): Promise<PatentListResponse> =>
    api.get('/patents', { params }),

  get: (id: number): Promise<Patent> => api.get(`/patents/${id}`),

  create: (data: Partial<Patent>): Promise<Patent> => api.post('/patents', data),

  update: (id: number, data: Partial<Patent> & { tag_ids?: number[]; project_ids?: number[] }): Promise<Patent> => api.put(`/patents/${id}`, data),

  delete: (id: number): Promise<{ success: boolean }> => api.delete(`/patents/${id}`),

  bulkUpdate: (ids: number[], updates: Partial<Patent>): Promise<{ success: boolean; updated_count: number }> =>
    api.post('/patents/bulk-update', { patent_ids: ids, updates }),

  // 批量删除专利（请求体为 [id1, id2, ...] 数组）
  bulkDelete: (ids: number[]): Promise<{ success: boolean; deleted_count: number }> =>
    api.post('/patents/bulk-delete', ids),

  // 清理无效占位专利（title="待补全" 且号格式不合法的历史残留）
  cleanupInvalidPlaceholders: (dryRun: boolean = true): Promise<{
    deleted_count: number
    deleted_items: Array<{ id: number; application_number: string | null; publication_number: string | null; notes: string | null; created_at: string | null }>
    dry_run: boolean
  }> => api.post('/patents/cleanup/invalid-placeholders', null, { params: { dry_run: dryRun } }),

  updateCell: (patentId: number, fieldKey: string, value: JsonValue): Promise<Patent> =>
    api.patch(`/patents/${patentId}/field/${fieldKey}`, { value } as CellUpdateRequest),

  // 修改历史
  getHistory: (patentId: number, limit: number = 100): Promise<PatentHistory[]> =>
    api.get(`/patents/${patentId}/history`, { params: { limit } }),
}

export const productApi = {
  list: (params: JsonObject = {}): Promise<Product[]> => api.get('/products', { params }),
  create: (data: Partial<Product>): Promise<Product> => api.post('/products', data),
  update: (id: number, data: Partial<Product>): Promise<Product> => api.put(`/products/${id}`, data),
  delete: (id: number): Promise<{ success: boolean }> => api.delete(`/products/${id}`),
}

export const projectApi = {
  list: (params: JsonObject = {}): Promise<Project[]> => api.get('/projects', { params }),
  create: (data: Partial<Project>): Promise<Project> => api.post('/projects', data),
  update: (id: number, data: Partial<Project>): Promise<Project> => api.put(`/projects/${id}`, data),
  delete: (id: number): Promise<{ success: boolean }> => api.delete(`/projects/${id}`),
}

export const tagApi = {
  list: (): Promise<Tag[]> => api.get('/tags'),
  create: (data: Partial<Tag>): Promise<Tag> => api.post('/tags', data),
  update: (id: number, data: Partial<Tag>): Promise<Tag> => api.put(`/tags/${id}`, data),
  delete: (id: number): Promise<{ success: boolean }> => api.delete(`/tags/${id}`),
}

export const tagGroupApi = {
  list: (): Promise<TagGroup[]> => api.get('/tag-groups'),
  create: (data: Partial<TagGroup>): Promise<TagGroup> => api.post('/tag-groups', data),
  update: (id: number, data: Partial<TagGroup>): Promise<TagGroup> => api.put(`/tag-groups/${id}`, data),
  delete: (id: number): Promise<{ success: boolean }> => api.delete(`/tag-groups/${id}`),
}

export const customFieldApi = {
  list: (params: JsonObject = {}): Promise<CustomField[]> => api.get('/custom-fields', { params }),
  create: (data: Partial<CustomField>): Promise<CustomField> => api.post('/custom-fields', data),
  update: (id: number, data: Partial<CustomField>): Promise<CustomField> => api.put(`/custom-fields/${id}`, data),
  delete: (id: number): Promise<{ success: boolean }> => api.delete(`/custom-fields/${id}`),
}

export const importApi = {
  upload: (file: File): Promise<ImportPreview> => {
    const formData = new FormData()
    formData.append('file', file)
    return api.post('/import/preview', formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
    })
  },

  confirmImport: (
    importId: string,
    fieldMappings: FieldMapping[],
    dedupeBy: string = 'both',
    updateOnDuplicate: boolean = true,
    productId?: number,
    projectId?: number,
    databaseId?: number,
  ): Promise<ImportResult> => {
    return api.post('/import/confirm', {
      import_id: importId,
      field_mappings: fieldMappings,
      dedupe_by: dedupeBy,
      update_on_duplicate: updateOnDuplicate,
      product_id: productId,
      project_id: projectId,
      database_id: databaseId,
    }, {
      timeout: 600000,
    })
  },

  listBatches: (params: JsonObject = {}): Promise<ImportBatch[]> =>
    api.get('/import/batches', { params }),

  getBatch: (id: number): Promise<ImportBatch> => api.get(`/import/batches/${id}`),
}

export const statsApi = {
  get: (params?: { database_id?: number | null; product_id?: number | null }): Promise<Stats> =>
    api.get('/stats', { params }),
}

// ============================================================
// 统计分析 API（列统计 / AGENTAI看板 / 转标签）
// ============================================================
export const analyticsApi = {
  columnStats: (data: {
    field_key: string
    database_id?: number | null
    product_id?: number | null
    project_id?: number | null
    tag_id?: number | null
    filters?: JsonObject
    top_n?: number
  }): Promise<{
    field_key: string
    total_distinct: number
    total_rows: number
    items: { value: string; raw_value: JsonValue; count: number; percentage: number }[]
  }> => api.post('/analytics/column-stats', data),

  statsToTags: (data: {
    field_key: string
    group_name?: string
    group_color?: string
    tag_color?: string
    only_non_empty?: boolean
    auto_apply_to_patents?: boolean
    database_id?: number | null
    product_id?: number | null
    project_id?: number | null
  }): Promise<{
    group: { id: number; name: string }
    tags: { id: number; name: string; count: number }[]
    total_tags: number
    applied_count: number
  }> => api.post('/analytics/stats-to-tags', data),

  agentAnalysis: (data: {
    requirement: string
    database_id?: number | null
    product_id?: number | null
    project_id?: number | null
    tag_id?: number | null
    filters?: JsonObject
    dimensions?: string[]
    top_n?: number
  }): Promise<AgentAnalysisResult> => api.post('/analytics/agent-analysis', data, { timeout: 180000 }),

  crossTab: (data: {
    row_field: string
    col_field: string
    database_id?: number | null
    product_id?: number | null
    project_id?: number | null
    filters?: JsonObject
    top_n?: number
  }): Promise<JsonValue> => api.post('/analytics/crosstab', data),
}

export const personApi = {
  list: (): Promise<Person[]> => api.get('/people'),
  create: (data: Partial<Person>): Promise<Person> => api.post('/people', data),
  update: (id: number, data: Partial<Person>): Promise<Person> => api.put(`/people/${id}`, data),
  delete: (id: number): Promise<{ success: boolean }> => api.delete(`/people/${id}`),
}

export const departmentApi = {
  list: (): Promise<Department[]> => api.get('/departments'),
  create: (data: Partial<Department>): Promise<Department> => api.post('/departments', data),
  update: (id: number, data: Partial<Department>): Promise<Department> => api.put(`/departments/${id}`, data),
  delete: (id: number): Promise<{ success: boolean }> => api.delete(`/departments/${id}`),
}

export const productLineApi = {
  list: (): Promise<ProductLine[]> => api.get('/product-lines'),
  create: (data: Partial<ProductLine>): Promise<ProductLine> => api.post('/product-lines', data),
  update: (id: number, data: Partial<ProductLine>): Promise<ProductLine> => api.put(`/product-lines/${id}`, data),
  delete: (id: number): Promise<{ success: boolean }> => api.delete(`/product-lines/${id}`),
}

export const aiApi = {
  process: (patentIds: number[], fieldKey: string, options: { model?: string; force_recalculate?: boolean } = {}): Promise<AITask> =>
    api.post('/ai/process', { patent_ids: patentIds, field_key: fieldKey, ...options }),

  getTask: (id: number): Promise<AITask> => api.get(`/ai/tasks/${id}`),

  listTasks: (params: { status?: string; limit?: number } = {}): Promise<AITask[]> =>
    api.get('/ai/tasks', { params }),

  deleteTask: (id: number): Promise<{ success: boolean }> => api.delete(`/ai/tasks/${id}`),

  listAIFields: (): Promise<CustomField[]> =>
    api.get('/ai/fields'),

  listValues: (patentId: number): Promise<AIFieldValue[]> =>
    api.get(`/patents/${patentId}/ai-values`),

  overrideValue: (patentId: number, fieldKey: string, value: JsonValue): Promise<AIFieldValue> =>
    api.put(`/patents/${patentId}/ai-values`, { field_key: fieldKey, value }),

  clearOverride: (patentId: number, fieldKey: string): Promise<{ success: boolean; field_key: string; value: JsonValue | null }> =>
    api.delete(`/patents/${patentId}/ai-values`, { params: { field_key: fieldKey } }),
}

export const exportApi = {
  exportPatents: (params: JsonObject = {}): Promise<Blob> =>
    api.get('/export', { params, responseType: 'blob' }),
}

export const settingsApi = {
  get: (): Promise<JsonObject> => api.get('/settings'),

  update: (payload: JsonObject): Promise<{ success: boolean; message: string }> =>
    api.put('/settings', payload),

  testLLM: (payload: { api_key?: string; base_url?: string; model?: string }): Promise<{ success: boolean; message: string }> =>
    api.post('/settings/test-llm', payload),
}

// ============================================================
// 用户与协作 API（权限管理 MVP）
// ============================================================
export const sharingApi = {
  // 用户管理
  listUsers: (): Promise<User[]> => api.get('/users'),

  createUser: (data: {
    username: string
    display_name?: string
    email?: string
    role?: string
  }): Promise<User> => api.post('/users', data),

  getUser: (userId: number): Promise<User> => api.get(`/users/${userId}`),

  // 库的成员管理
  listMembers: (databaseId: number): Promise<DatabaseMember[]> =>
    api.get(`/databases/${databaseId}/members`),

  addMember: (databaseId: number, data: {
    username?: string
    user_id?: number
    role: 'editor' | 'viewer'
  }): Promise<DatabaseMember> =>
    api.post(`/databases/${databaseId}/members`, data),

  updateMember: (databaseId: number, userId: number, role: 'editor' | 'viewer'): Promise<DatabaseMember> =>
    api.put(`/databases/${databaseId}/members/${userId}`, { role }),

  removeMember: (databaseId: number, userId: number): Promise<{ success: boolean }> =>
    api.delete(`/databases/${databaseId}/members/${userId}`),

  // 当前用户视角：与我共享的库
  listUserDatabases: (userId: number): Promise<SharedDatabase[]> =>
    api.get(`/users/${userId}/databases`),
}
