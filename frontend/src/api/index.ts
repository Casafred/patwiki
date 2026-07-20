import api from '../lib/api'
import type {
  Patent, PatentListResponse, Product, Project, Tag, TagGroup,
  CustomField, ImportBatch, ImportPreview, ImportResult, FieldMapping, Stats, Person, Department,
  AITask, FieldMetaWithView, CellUpdateRequest, PatentDatabase,
  User, DatabaseMember, SharedDatabase, PatentHistory,
  PatentView, ViewLocalField, ViewPatentListResponse, ViewFilterRule,
  ViewColumnConfig, ViewSortConfig, FieldSource, AIFieldValueInfo, SearchSuggestion,
  PatentGraph,
} from '../types'

export const fieldApi = {
  // P1-12：可选 view_id，传入时返回值会附加 vlf_ 本地字段
  list: (viewId?: number): Promise<FieldMetaWithView[]> => {
    const params = viewId != null ? { view_id: viewId } : {}
    return api.get('/fields', { params })
  },
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

  delete: (id: number): Promise<{ success: boolean }> =>
    api.delete(`/databases/${id}`),

  refreshCount: (id: number): Promise<{ success: boolean; patent_count: number }> =>
    api.post(`/databases/${id}/refresh-count`),

  // 设置/转移所有者
  setOwner: (id: number, userId: number): Promise<PatentDatabase> =>
    api.post(`/databases/${id}/set-owner`, { user_id: userId }),

  // P0-13：获取或创建某库的部门总表视图
  getOrCreateMasterView: (id: number): Promise<PatentView> =>
    api.get(`/databases/${id}/master-view`),
}

export const patentApi = {
  list: (params: Record<string, any> = {}): Promise<PatentListResponse> =>
    api.get('/patents', { params }),

  get: (id: number): Promise<Patent> => api.get(`/patents/${id}`),

  create: (data: Partial<Patent>): Promise<Patent> => api.post('/patents', data),

  update: (id: number, data: Partial<Patent>): Promise<Patent> => api.put(`/patents/${id}`, data),

  delete: (id: number): Promise<{ success: boolean }> => api.delete(`/patents/${id}`),

  bulkUpdate: (ids: number[], updates: Partial<Patent>): Promise<{ success: boolean; updated_count: number }> =>
    api.post('/patents/bulk-update', { patent_ids: ids, updates }),

  // P2-6：搜索自动补全
  searchSuggest: (q: string, limit: number = 10, databaseId?: number): Promise<{ suggestions: SearchSuggestion[] }> => {
    const params: Record<string, any> = { q, limit }
    if (databaseId != null) params.database_id = databaseId
    return api.get('/patents/search/suggest', { params })
  },

  // P1-10：合并后的单字段更新端点，支持 source_view_id（在视图内编辑时传入）
  updateCell: (
    patentId: number,
    fieldKey: string,
    value: any,
    options: { changed_by?: string; source_view_id?: number } = {},
  ): Promise<Patent & { source_view_id?: number; source_view_name?: string }> =>
    api.patch(`/patents/${patentId}/field/${fieldKey}`, {
      value,
      changed_by: options.changed_by,
      source_view_id: options.source_view_id,
    } as CellUpdateRequest),

  // 修改历史
  getHistory: (patentId: number, limit: number = 100): Promise<PatentHistory[]> =>
    api.get(`/patents/${patentId}/history`, { params: { limit } }),

  // P0-13：字段来源追溯
  getFieldSources: (patentId: number): Promise<{
    sources: FieldSource[]
    view_local_sources: FieldSource[]
  }> => api.get(`/patents/${patentId}/field-sources`),

  // P2-3：AI 字段值人工覆盖
  getAIValues: (patentId: number): Promise<AIFieldValueInfo[]> =>
    api.get(`/patents/${patentId}/ai-values`),

  overrideAIValue: (
    patentId: number,
    fieldKey: string,
    value: string | null,
    changedBy?: string,
  ): Promise<AIFieldValueInfo> =>
    api.put(`/patents/${patentId}/ai-values/${fieldKey}`, {
      value,
      changed_by: changedBy,
    }),

  clearAIOverride: (patentId: number, fieldKey: string): Promise<AIFieldValueInfo> =>
    api.delete(`/patents/${patentId}/ai-values/${fieldKey}/override`),

  // P2-7：专利关系图谱
  getGraph: (patentId: number, depth: number = 1): Promise<PatentGraph> =>
    api.get(`/patents/${patentId}/graph`, { params: { depth } }),

  addCitation: (
    patentId: number,
    citedPatentId: number,
    citationType: string = 'citation',
  ): Promise<{ success: boolean; id: number; already_exists: boolean }> =>
    api.post(`/patents/${patentId}/citations`, {
      cited_patent_id: citedPatentId,
      citation_type: citationType,
    }),

  removeCitation: (patentId: number, citedPatentId: number): Promise<{ success: boolean }> =>
    api.delete(`/patents/${patentId}/citations/${citedPatentId}`),
}

export const productApi = {
  list: (params: Record<string, any> = {}): Promise<Product[]> => api.get('/products', { params }),
  create: (data: Partial<Product>): Promise<Product> => api.post('/products', data),
  update: (id: number, data: Partial<Product>): Promise<Product> => api.put(`/products/${id}`, data),
  delete: (id: number): Promise<{ success: boolean }> => api.delete(`/products/${id}`),
}

export const projectApi = {
  list: (params: Record<string, any> = {}): Promise<Project[]> => api.get('/projects', { params }),
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
  list: (params: Record<string, any> = {}): Promise<CustomField[]> => api.get('/custom-fields', { params }),
  create: (data: Partial<CustomField>): Promise<CustomField> => api.post('/custom-fields', data),
  update: (id: number, data: Partial<CustomField>): Promise<CustomField> => api.put(`/custom-fields/${id}`, data),
  delete: (id: number): Promise<{ success: boolean }> => api.delete(`/custom-fields/${id}`),
}

export const importApi = {
  // P1-15：可选 view_id，传入时未知列自动建为视图本地字段（vlf_）
  upload: (file: File, viewId?: number): Promise<ImportPreview & { view?: PatentView }> => {
    const formData = new FormData()
    formData.append('file', file)
    if (viewId != null) {
      formData.append('view_id', String(viewId))
    }
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
    // P1-15：导入到视图
    viewId?: number,
  ): Promise<ImportResult> => {
    return api.post('/import/confirm', {
      import_id: importId,
      field_mappings: fieldMappings,
      dedupe_by: dedupeBy,
      update_on_duplicate: updateOnDuplicate,
      product_id: productId,
      project_id: projectId,
      database_id: databaseId,
      view_id: viewId,
    }, {
      timeout: 600000,
    })
  },

  // P2-2：返回 {total, items}
  listBatches: (params: Record<string, any> = {}): Promise<{ total: number; items: ImportBatch[] }> =>
    api.get('/import/batches', { params }),

  getBatch: (id: number): Promise<ImportBatch & { errors?: any[] }> => api.get(`/import/batches/${id}`),
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
    filters?: Record<string, any>
    top_n?: number
  }): Promise<{
    field_key: string
    total_distinct: number
    total_rows: number
    items: { value: string; raw_value: any; count: number; percentage: number }[]
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
    filters?: Record<string, any>
    dimensions?: string[]
    top_n?: number
  }): Promise<{
    requirement: string
    base_stats: any
    ai_analysis: {
      overview: string
      key_findings: string[]
      dimension_analysis: Record<string, string>
      anomalies: string[]
      recommendations: string[]
      risk_warnings: string[]
    }
    created_at: string
  }> => api.post('/analytics/agent-analysis', data, { timeout: 180000 }),

  crossTab: (data: {
    row_field: string
    col_field: string
    database_id?: number | null
    product_id?: number | null
    project_id?: number | null
    filters?: Record<string, any>
    top_n?: number
  }): Promise<any> => api.post('/analytics/crosstab', data),
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

export const aiApi = {
  process: (patentIds: number[], fieldKey: string, options: { model?: string; force_recalculate?: boolean } = {}): Promise<AITask> =>
    api.post('/ai/process', { patent_ids: patentIds, field_key: fieldKey, ...options }),

  getTask: (id: number): Promise<AITask> => api.get(`/ai/tasks/${id}`),

  listTasks: (params: { status?: string; limit?: number } = {}): Promise<AITask[]> =>
    api.get('/ai/tasks', { params }),

  deleteTask: (id: number): Promise<{ success: boolean }> => api.delete(`/ai/tasks/${id}`),

  listAIFields: (): Promise<{ key: string; name: string; description: string; ai_config: any }[]> =>
    api.get('/ai/fields'),
}

export const exportApi = {
  exportPatents: (params: Record<string, any> = {}): Promise<Blob> =>
    api.get('/export', { params, responseType: 'blob' }),
}

export const settingsApi = {
  get: (): Promise<any> => api.get('/settings'),

  update: (payload: any): Promise<{ success: boolean; message: string }> =>
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

// ============================================================
// P0-13/P0-14：视图（小表 / 部门总表）API
// ============================================================
export const viewApi = {
  // ===== 视图 CRUD =====
  list: (params: {
    database_id?: number
    owner_id?: number
    view_type?: string
    include_archived?: boolean
  } = {}): Promise<PatentView[]> => api.get('/views', { params }),

  get: (viewId: number): Promise<PatentView> => api.get(`/views/${viewId}`),

  create: (data: {
    name: string
    database_id: number
    description?: string
    view_type?: 'personal' | 'shared'
    is_department_master?: boolean
    filter_config?: Record<string, ViewFilterRule>
    column_config?: ViewColumnConfig[]
    sort_config?: ViewSortConfig
  }): Promise<PatentView> => api.post('/views', data),

  update: (viewId: number, data: {
    name?: string
    description?: string
    filter_config?: Record<string, ViewFilterRule>
    column_config?: ViewColumnConfig[]
    sort_config?: ViewSortConfig
  }): Promise<PatentView> => api.put(`/views/${viewId}`, data),

  delete: (viewId: number): Promise<{ success: boolean }> =>
    api.delete(`/views/${viewId}`),

  archive: (viewId: number): Promise<PatentView> =>
    api.post(`/views/${viewId}/archive`),

  // ===== 视图数据查询 =====
  listPatents: (
    viewId: number,
    params: { page?: number; page_size?: number; extra_filters?: Record<string, any> } = {},
  ): Promise<ViewPatentListResponse> => {
    const query: Record<string, any> = {
      page: params.page ?? 1,
      page_size: params.page_size ?? 50,
    }
    if (params.extra_filters) {
      query.extra_filters = JSON.stringify(params.extra_filters)
    }
    return api.get(`/views/${viewId}/patents`, { params: query })
  },

  // ===== 视图本地字段（vlf_）CRUD =====
  listLocalFields: (viewId: number): Promise<ViewLocalField[]> =>
    api.get(`/views/${viewId}/local-fields`),

  createLocalField: (viewId: number, data: {
    key: string
    name: string
    field_type?: string
    options?: string[]
    description?: string
    default_value?: string
    is_required?: boolean
    sort_order?: number
  }): Promise<ViewLocalField> => api.post(`/views/${viewId}/local-fields`, data),

  updateLocalField: (
    viewId: number,
    fieldId: number,
    data: Partial<ViewLocalField>,
  ): Promise<ViewLocalField> => api.put(`/views/${viewId}/local-fields/${fieldId}`, data),

  deleteLocalField: (viewId: number, fieldId: number): Promise<{ success: boolean }> =>
    api.delete(`/views/${viewId}/local-fields/${fieldId}`),

  // ===== 视图本地字段值 =====
  setLocalFieldValue: (
    viewId: number,
    fieldKey: string,
    patentId: number,
    value: any,
    changedBy?: string,
  ): Promise<{ success: boolean; patent_id: number; view_id: number; field_key: string; value: any }> =>
    api.put(`/views/${viewId}/local-fields/${fieldKey}/values/${patentId}`, {
      value,
      changed_by: changedBy,
    }),

  getLocalFieldValue: (
    viewId: number,
    fieldKey: string,
    patentId: number,
  ): Promise<{ patent_id: number; view_id: number; field_key: string; value: any }> =>
    api.get(`/views/${viewId}/local-fields/${fieldKey}/values/${patentId}`),

  // ===== 字段提升（vlf_ -> cf_） =====
  promoteLocalField: (
    viewId: number,
    fieldId: number,
    options: { global_name?: string; global_group?: string } = {},
  ): Promise<{
    success: boolean
    global_field_key: string
    global_field_name: string
    global_field_id: number
    source_view_id: number
    source_view_name: string
  }> => api.post(`/views/${viewId}/local-fields/${fieldId}/promote`, options),
}
