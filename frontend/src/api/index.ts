import api from '../lib/api'
import type {
  Patent, PatentListResponse, Product, Project, Tag, TagGroup,
  CustomField, ImportBatch, ImportPreview, ImportResult, FieldMapping, Stats, Person, Department,
  AITask, FieldMeta, CellUpdateRequest, PatentDatabase,
  User, DatabaseMember, SharedDatabase, PatentHistory,
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

export const patentApi = {
  list: (params: Record<string, any> = {}): Promise<PatentListResponse> =>
    api.get('/patents', { params }),

  get: (id: number): Promise<Patent> => api.get(`/patents/${id}`),

  create: (data: Partial<Patent>): Promise<Patent> => api.post('/patents', data),

  update: (id: number, data: Partial<Patent>): Promise<Patent> => api.put(`/patents/${id}`, data),

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

  updateCell: (patentId: number, fieldKey: string, value: any): Promise<Patent> =>
    api.patch(`/patents/${patentId}/field/${fieldKey}`, { value } as CellUpdateRequest),

  // 修改历史
  getHistory: (patentId: number, limit: number = 100): Promise<PatentHistory[]> =>
    api.get(`/patents/${patentId}/history`, { params: { limit } }),
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
}

export const customFieldApi = {
  list: (params: Record<string, any> = {}): Promise<CustomField[]> => api.get('/custom-fields', { params }),
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

  listBatches: (params: Record<string, any> = {}): Promise<ImportBatch[]> =>
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
}

export const departmentApi = {
  list: (): Promise<Department[]> => api.get('/departments'),
  create: (data: Partial<Department>): Promise<Department> => api.post('/departments', data),
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
