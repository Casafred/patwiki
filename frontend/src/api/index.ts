import api from '../lib/api'
import type {
  Patent, PatentListResponse, Product, Project, Tag, TagGroup,
  CustomField, ImportBatch, ImportPreview, ImportResult, FieldMapping, Stats, Person, Department, ProductLine,
  AITask, AIFieldValue, FieldMeta, CellUpdateRequest, PatentDatabase,
  User, DatabaseMember, SharedDatabase, PatentHistory, PatentView, ViewPatentListResponse,
  GroupedViewResponse, ViewGroupField, ConditionalFormatRule, KanbanResponse, JsonObject, JsonValue,
  AgentAnalysisResult, LinkRecord, LinkTarget, RelationBatchItem, PatentShare, PublicPatentShare, SearchSuggestion,
  PatentGraphResponse, FormulaReturnType, FormDefinition, FormShareLink, GanttResponse, AttachmentMeta,
  Dashboard, DashboardCard, DashboardData, AutomationRule, AutomationLog, CommentRecord,
  GovernanceAction, GovernanceDecision, GovernanceObservation, GovernanceBatch,
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
    is_department_master?: boolean
    membership_based?: boolean
  }): Promise<PatentView> => api.post('/views', data),

  update: (id: number, data: Partial<PatentView>): Promise<PatentView> =>
    api.put(`/views/${id}`, data),

  master: (databaseId: number): Promise<PatentView> =>
    api.get(`/databases/${databaseId}/master-view`),

  // P0-14：把专利加入/移出视图（成员型视图）
  addPatents: (viewId: number, patentIds: number[]): Promise<{ success: boolean; updated_count: number }> =>
    api.post(`/views/${viewId}/patents`, { patent_ids: patentIds }),

  removePatents: (viewId: number, patentIds: number[]): Promise<{ success: boolean; updated_count: number }> =>
    api.delete(`/views/${viewId}/patents`, { data: { patent_ids: patentIds } }),

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

  form: (viewId: number): Promise<FormDefinition> =>
    api.get(`/views/${viewId}/form`),

  submitForm: (viewId: number, data: JsonObject, patentId?: number | null): Promise<{
    success: boolean
    patent_id: number
    patent: Patent
  }> => api.post(`/views/${viewId}/form/submit`, { data, patent_id: patentId ?? null }),

  createFormShare: (viewId: number, expiresDays?: number | null): Promise<FormShareLink> =>
    api.post(`/views/${viewId}/form/share`, { expires_days: expiresDays ?? null }),

  gantt: (viewId: number, params: { page_size?: number; search?: string } = {}): Promise<GanttResponse> =>
    api.get(`/views/${viewId}/gantt`, { params }),

  updateGanttDates: (viewId: number, data: {
    patent_id: number
    new_start: string
    new_end: string
    changed_by?: string
  }): Promise<{ success: boolean; patent_id: number; new_start: string; new_end: string }> =>
    api.post(`/views/${viewId}/gantt/update-dates`, data),

  updateSharedField: (viewId: number, patentId: number, fieldKey: string, value: JsonValue): Promise<{
    success: boolean
    patent_id: number
    field_key: string
  }> => api.patch(`/views/${viewId}/patents/${patentId}/field/${fieldKey}`, { value }),
}

export const formApi = {
  getShared: (token: string): Promise<FormDefinition> =>
    api.get(`/form/shared/${encodeURIComponent(token)}`),

  submitShared: (token: string, data: JsonObject): Promise<{ success: boolean; patent_id: number }> =>
    api.post(`/form/shared/${encodeURIComponent(token)}/submit`, { data }),
}

export const attachmentApi = {
  upload: (data: FormData): Promise<AttachmentMeta> =>
    api.post('/attachments/upload', data, { headers: { 'Content-Type': 'multipart/form-data' } }),
  list: (patentId: number, fieldKey?: string): Promise<AttachmentMeta[]> =>
    api.get(`/attachments/patent/${patentId}`, { params: { field_key: fieldKey } }),
  download: (attachmentId: number, preview = false): Promise<Blob> =>
    api.get(`/attachments/${attachmentId}/${preview ? 'preview' : 'download'}`, { responseType: 'blob' }),
  remove: (attachmentId: number): Promise<{ success: boolean }> =>
    api.delete(`/attachments/${attachmentId}`),
}

export const dashboardApi = {
  list: (databaseId?: number | null): Promise<Dashboard[]> =>
    api.get('/dashboards', { params: { database_id: databaseId ?? undefined } }),
  create: (data: { database_id: number; name: string; description?: string; layout?: DashboardCard[] }): Promise<Dashboard> =>
    api.post('/dashboards', data),
  update: (id: number, data: { name?: string; description?: string; layout?: DashboardCard[] }): Promise<Dashboard> =>
    api.put(`/dashboards/${id}`, data),
  remove: (id: number): Promise<{ success: boolean }> => api.delete(`/dashboards/${id}`),
  data: (id: number, viewId?: number | null): Promise<DashboardData> =>
    api.get(`/dashboards/${id}/data`, { params: { view_id: viewId ?? undefined } }),
  addCard: (id: number, card: Omit<DashboardCard, 'id'> & { id?: string }): Promise<DashboardCard> =>
    api.post(`/dashboards/${id}/cards`, card),
  removeCard: (id: number, cardId: string): Promise<{ success: boolean }> =>
    api.delete(`/dashboards/${id}/cards/${encodeURIComponent(cardId)}`),
}

export const automationApi = {
  listRules: (databaseId?: number | null): Promise<AutomationRule[]> =>
    api.get('/automation/rules', { params: { database_id: databaseId ?? undefined } }),
  createRule: (data: {
    database_id: number
    name: string
    priority?: number
    trigger_config: JsonObject
    condition_config: JsonObject[]
    action_config: JsonObject[]
  }): Promise<AutomationRule> => api.post('/automation/rules', data),
  toggleRule: (id: number): Promise<AutomationRule> => api.post(`/automation/rules/${id}/toggle`),
  removeRule: (id: number): Promise<{ success: boolean }> => api.delete(`/automation/rules/${id}`),
  executeRule: (id: number, patentId: number): Promise<JsonObject> =>
    api.post(`/automation/rules/${id}/execute`, { patent_id: patentId }),
  logs: (databaseId?: number | null): Promise<AutomationLog[]> =>
    api.get('/automation/logs', { params: { database_id: databaseId ?? undefined, limit: 80 } }),
  scheduleTick: (databaseId?: number | null): Promise<JsonObject> =>
    api.post('/automation/schedule/tick', undefined, { params: { database_id: databaseId ?? undefined } }),
}

export const commentApi = {
  list: (patentId: number, params: { include_resolved?: boolean; field_key?: string } = {}): Promise<CommentRecord[]> =>
    api.get(`/patents/${patentId}/comments`, { params }),
  create: (patentId: number, data: {
    content: string
    author_name?: string
    parent_id?: number | null
    field_key?: string | null
  }): Promise<CommentRecord> => api.post(`/patents/${patentId}/comments`, data),
  get: (commentId: number): Promise<CommentRecord> => api.get(`/comments/${commentId}`),
  update: (commentId: number, content: string): Promise<CommentRecord> => api.put(`/comments/${commentId}`, { content }),
  resolve: (commentId: number, resolved: boolean, resolvedBy?: string): Promise<CommentRecord> =>
    api.post(`/comments/${commentId}/resolve`, { resolved, resolved_by: resolvedBy }),
  remove: (commentId: number): Promise<{ success: boolean }> => api.delete(`/comments/${commentId}`),
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

  // 批量打标签 / 移除标签 / 替换标签
  bulkTag: (patentIds: number[], tagIds: number[], mode: 'add' | 'remove' | 'replace' = 'add'): Promise<{ success: boolean; updated_count: number }> =>
    api.post('/patents/bulk-tag', { patent_ids: patentIds, tag_ids: tagIds, mode }),

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

  getGraph: (patentId: number, params: { depth?: number; include_family?: boolean; include_citations?: boolean } = {}): Promise<PatentGraphResponse> =>
    api.get(`/patents/${patentId}/graph`, { params }),
}

export const patentShareApi = {
  list: (patentId: number): Promise<PatentShare[]> =>
    api.get(`/patents/${patentId}/shares`),

  create: (patentId: number, data: { title_override?: string; expires_at?: string | null } = {}): Promise<PatentShare> =>
    api.post(`/patents/${patentId}/shares`, data),

  revoke: (patentId: number, token: string): Promise<{ success: boolean; token: string }> =>
    api.delete(`/patents/${patentId}/shares/${encodeURIComponent(token)}`),

  getPublic: (token: string): Promise<PublicPatentShare> =>
    api.get(`/share/patents/${encodeURIComponent(token)}`),
}

export const searchApi = {
  suggest: (query: string, databaseId?: number | null, limit = 8): Promise<SearchSuggestion[]> =>
    api.get('/search/suggest', { params: { q: query, database_id: databaseId ?? undefined, limit } }),
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
  upload: (file: File, sheetName?: string | null): Promise<ImportPreview> => {
    const formData = new FormData()
    formData.append('file', file)
    if (sheetName) formData.append('sheet_name', sheetName)
    // Let the browser/Axios add the multipart boundary.
    return api.post('/import/preview', formData)
  },

  confirmImport: (
    importId: string,
    fieldMappings: FieldMapping[],
    dedupeBy: string = 'both',
    updateOnDuplicate: boolean = true,
    productId?: number,
    projectId?: number,
    databaseId?: number,
    viewId?: number,
    sheetName?: string,
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
      sheet_name: sheetName,
    }, {
      timeout: 600000,
    })
  },

  listBatches: (params: JsonObject = {}): Promise<ImportBatch[]> =>
    api.get('/import/batches', { params }),

  getBatch: (id: number): Promise<ImportBatch> => api.get(`/import/batches/${id}`),
  listUnmapped: (params: JsonObject = {}): Promise<{ total: number; offset: number; limit: number; items: GovernanceObservation[] }> =>
    api.get('/import/unmapped', { params }),
  decideObservation: (
    observationId: number,
    request: {
      action: GovernanceAction
      canonical_field_key?: string
      apply_to_batch?: boolean
      adopted_value?: boolean
      decided_by?: string
      reason?: string
    },
  ): Promise<{ action: GovernanceAction; scope: string; decision_batch_id: string; updated_count: number; adopted_value_count: number; items: GovernanceObservation[] }> =>
    api.patch(`/import/observations/${observationId}`, request),
  listObservationDecisions: (observationId: number): Promise<GovernanceDecision[]> =>
    api.get(`/import/observations/${observationId}/decisions`),
  listGovernanceBatches: (params: JsonObject = {}): Promise<{ total: number; offset: number; limit: number; items: GovernanceBatch[] }> =>
    api.get('/import/governance/batches', { params }),
  revertGovernanceBatch: (decisionBatchId: string, request: { reversed_by?: string; reason?: string } = {}): Promise<{ decision_batch_id: string; restored_observation_count: number; restored_value_count: number }> =>
    api.post(`/import/governance/batches/${decisionBatchId}/revert`, request),
  exportUnmapped: (params: JsonObject = {}): Promise<Blob> =>
    api.get('/import/unmapped/export', { params, responseType: 'blob' }),

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

export const formulaApi = {
  list: (): Promise<Array<CustomField & { dependencies?: string[] }>> => api.get('/formula/fields'),
  create: (data: {
    key: string
    name: string
    expression: string
    return_type: FormulaReturnType
    group_name?: string
    description?: string
    sort_order?: number
    is_active?: boolean
  }): Promise<CustomField> => api.post('/formula/fields', data),
  update: (id: number, data: {
    name?: string
    expression?: string
    return_type?: FormulaReturnType
    group_name?: string
    description?: string
    sort_order?: number
    is_active?: boolean
  }): Promise<CustomField> => api.put(`/formula/fields/${id}`, data),
  validate: (expression: string, formulaKey?: string): Promise<{
    valid: boolean
    expression: string
    dependencies: string[]
    error?: string | null
  }> => api.post('/formula/validate', { expression, formula_key: formulaKey }),
  functions: (): Promise<Array<{ name: string; category: string; description: string }>> => api.get('/formula/functions'),
  recalculate: (formulaKey: string, patentIds?: number[]): Promise<{
    patent_count: number
    formula_count: number
    errors: Record<string, number>
  }> => api.post(`/formula/recalculate/${encodeURIComponent(formulaKey)}`, { patent_ids: patentIds }),
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

  quickAnalyze: (params: {
    patent_ids: number[]
    input_fields: string[]
    prompt: string
    extractions: { name: string; target_field_key?: string; new_field_name?: string; new_field_type?: string }[]
  }): Promise<AITask> =>
    api.post('/ai/quick-analyze', params),
}

export const exportApi = {
  exportPatents: (params: JsonObject = {}): Promise<Blob> =>
    api.get('/export', { params, responseType: 'blob' }),
  excel: (payload: JsonObject): Promise<Blob> =>
    api.post('/export/excel', payload, { responseType: 'blob' }),
  csv: (payload: JsonObject): Promise<Blob> =>
    api.post('/export/csv', payload, { responseType: 'blob' }),
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
    employee_no?: string | null
    department_id?: number | null
    group_id?: number | null
    product_line_id?: number | null
    organization_role?: string | null
  }): Promise<User> => api.post('/users', data),

  getUser: (userId: number): Promise<User> => api.get(`/users/${userId}`),

  updateUser: (userId: number, data: {
    display_name?: string
    email?: string
    role?: string
    employee_no?: string | null
    department_id?: number | null
    group_id?: number | null
    product_line_id?: number | null
    organization_role?: string | null
    is_active?: boolean
  }): Promise<User> => api.put(`/users/${userId}`, data),

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
