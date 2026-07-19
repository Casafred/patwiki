import api from '../lib/api'
import type {
  Patent, PatentListResponse, Product, Project, Tag, TagGroup,
  CustomField, ImportBatch, ImportPreview, ImportResult, FieldMapping, Stats, Person, Department,
  AITask, FieldMeta, CellUpdateRequest,
} from '../types'

export const fieldApi = {
  list: (): Promise<FieldMeta[]> => api.get('/fields'),
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

  updateCell: (patentId: number, fieldKey: string, value: any): Promise<Patent> =>
    api.patch(`/patents/${patentId}/field/${fieldKey}`, { value } as CellUpdateRequest),
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
  ): Promise<ImportResult> => {
    return api.post('/import/confirm', {
      import_id: importId,
      field_mappings: fieldMappings,
      dedupe_by: dedupeBy,
      update_on_duplicate: updateOnDuplicate,
      product_id: productId,
      project_id: projectId,
    })
  },

  listBatches: (params: Record<string, any> = {}): Promise<ImportBatch[]> =>
    api.get('/import/batches', { params }),

  getBatch: (id: number): Promise<ImportBatch> => api.get(`/import/batches/${id}`),
}

export const statsApi = {
  get: (): Promise<Stats> => api.get('/stats'),
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
