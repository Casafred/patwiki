import { useState, useEffect } from 'react'
import { customFieldApi } from '../../api'
import { CustomField } from '../../types'
import { useAppStore } from '../../store'

export default function FieldSettingsPage() {
  const [fields, setFields] = useState<CustomField[]>([])
  const [loading, setLoading] = useState(true)
  const [editingId, setEditingId] = useState<number | null>(null)
  const [editForm, setEditForm] = useState<Partial<CustomField>>({})
  const [saving, setSaving] = useState(false)
  const [showAddForm, setShowAddForm] = useState(false)
  const [newField, setNewField] = useState<Partial<CustomField>>({
    key: '',
    name: '',
    field_type: 'text',
    is_active: true,
    ai_config: {},
  })
  const { setCustomFields } = useAppStore()

  useEffect(() => {
    loadFields()
  }, [])

  const loadFields = async () => {
    try {
      const data = await customFieldApi.list()
      setFields(data)
    } catch (e) {
      console.error('Failed to load fields:', e)
    } finally {
      setLoading(false)
    }
  }

  const startEdit = (field: CustomField) => {
    setEditingId(field.id)
    setEditForm({
      name: field.name,
      description: field.description,
      field_type: field.field_type,
      options: field.options,
      is_active: field.is_active,
      is_required: field.is_required,
      ai_config: field.ai_config ? { ...field.ai_config } : {},
      group_name: field.group_name,
    })
  }

  const cancelEdit = () => {
    setEditingId(null)
    setEditForm({})
  }

  const saveEdit = async (id: number) => {
    setSaving(true)
    try {
      const updated = await customFieldApi.update(id, editForm)
      setFields(fields.map(f => f.id === id ? updated : f))
      setCustomFields(fields.map(f => f.id === id ? updated : f))
      setEditingId(null)
      setEditForm({})
    } catch (e: any) {
      alert('保存失败: ' + (e?.response?.data?.detail || e?.message || ''))
    } finally {
      setSaving(false)
    }
  }

  const handleAddField = async () => {
    if (!newField.key?.trim() || !newField.name?.trim()) {
      alert('请填写字段key和名称')
      return
    }
    setSaving(true)
    try {
      const created = await customFieldApi.create(newField)
      const updatedList = [...fields, created]
      setFields(updatedList)
      setCustomFields(updatedList)
      setShowAddForm(false)
      setNewField({
        key: '',
        name: '',
        field_type: 'text',
        is_active: true,
        ai_config: {},
      })
    } catch (e: any) {
      alert('创建失败: ' + (e?.response?.data?.detail || e?.message || ''))
    } finally {
      setSaving(false)
    }
  }

  const handleDelete = async (id: number, name: string) => {
    if (!confirm(`确定要删除字段"${name}"吗？已存在的数据不会丢失，但新数据将不再显示该字段。`)) {
      return
    }
    try {
      await customFieldApi.delete(id)
      const updatedList = fields.filter(f => f.id !== id)
      setFields(updatedList)
      setCustomFields(updatedList)
    } catch (e: any) {
      alert('删除失败: ' + (e?.response?.data?.detail || e?.message || ''))
    }
  }

  const isAiField = (field: CustomField) => {
    return field.ai_config && (field.ai_config.prompt_template || field.ai_config.ai_enabled)
  }

  const fieldTypeLabels: Record<string, string> = {
    text: '文本',
    textarea: '长文本',
    select: '单选',
    multi_select: '多选',
    number: '数字',
    date: '日期',
    boolean: '是/否',
  }

  if (loading) {
    return (
      <div className="loading-spinner">
        <div className="spinner"></div>
        加载中...
      </div>
    )
  }

  return (
    <div style={{ maxWidth: 900 }}>
      <div className="page-header" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <div>
          <h2 className="page-title">字段管理</h2>
          <p className="page-subtitle">管理自定义字段，配置AI字段的提取提示词</p>
        </div>
        <button
          className="btn btn-primary"
          onClick={() => setShowAddForm(true)}
        >
          + 新增字段
        </button>
      </div>

      {showAddForm && (
        <div style={{
          background: 'white',
          border: '1px solid #e2e8f0',
          borderRadius: 8,
          padding: 20,
          marginBottom: 20,
        }}>
          <h3 style={{ margin: '0 0 16px 0', fontSize: 15, fontWeight: 600 }}>新增字段</h3>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12, marginBottom: 12 }}>
            <div>
              <label style={{ display: 'block', fontSize: 13, color: '#475569', marginBottom: 4, fontWeight: 500 }}>字段Key (英文)</label>
              <input
                className="form-input"
                value={newField.key || ''}
                onChange={(e) => setNewField({ ...newField, key: e.target.value })}
                placeholder="例如: technical_field"
              />
            </div>
            <div>
              <label style={{ display: 'block', fontSize: 13, color: '#475569', marginBottom: 4, fontWeight: 500 }}>显示名称</label>
              <input
                className="form-input"
                value={newField.name || ''}
                onChange={(e) => setNewField({ ...newField, name: e.target.value })}
                placeholder="例如: 技术领域"
              />
            </div>
            <div>
              <label style={{ display: 'block', fontSize: 13, color: '#475569', marginBottom: 4, fontWeight: 500 }}>字段类型</label>
              <select
                className="form-input"
                value={newField.field_type}
                onChange={(e) => setNewField({ ...newField, field_type: e.target.value })}
              >
                <option value="text">文本</option>
                <option value="textarea">长文本</option>
                <option value="select">单选</option>
                <option value="multi_select">多选</option>
                <option value="number">数字</option>
                <option value="date">日期</option>
                <option value="boolean">是/否</option>
              </select>
            </div>
            <div>
              <label style={{ display: 'block', fontSize: 13, color: '#475569', marginBottom: 4, fontWeight: 500 }}>分组</label>
              <input
                className="form-input"
                value={newField.group_name || ''}
                onChange={(e) => setNewField({ ...newField, group_name: e.target.value })}
                placeholder="例如: AI分析"
              />
            </div>
          </div>
          <div style={{ marginBottom: 12 }}>
            <label style={{ display: 'block', fontSize: 13, color: '#475569', marginBottom: 4, fontWeight: 500 }}>描述</label>
            <input
              className="form-input"
              value={newField.description || ''}
              onChange={(e) => setNewField({ ...newField, description: e.target.value })}
              placeholder="字段说明（可选）"
            />
          </div>
          <div style={{ display: 'flex', gap: 8 }}>
            <button className="btn btn-primary" onClick={handleAddField} disabled={saving}>
              {saving ? '保存中...' : '创建'}
            </button>
            <button className="btn btn-secondary" onClick={() => {
              setShowAddForm(false)
              setNewField({ key: '', name: '', field_type: 'text', is_active: true, ai_config: {} })
            }}>
              取消
            </button>
          </div>
        </div>
      )}

      <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
        {fields.map(field => (
          <div
            key={field.id}
            style={{
              background: 'white',
              border: '1px solid #e2e8f0',
              borderRadius: 8,
              padding: 16,
            }}
          >
            {editingId === field.id ? (
              <div>
                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: 12, marginBottom: 12 }}>
                  <div>
                    <label style={{ display: 'block', fontSize: 12, color: '#64748b', marginBottom: 4 }}>显示名称</label>
                    <input
                      className="form-input"
                      value={editForm.name || ''}
                      onChange={(e) => setEditForm({ ...editForm, name: e.target.value })}
                    />
                  </div>
                  <div>
                    <label style={{ display: 'block', fontSize: 12, color: '#64748b', marginBottom: 4 }}>字段类型</label>
                    <select
                      className="form-input"
                      value={editForm.field_type || 'text'}
                      onChange={(e) => setEditForm({ ...editForm, field_type: e.target.value })}
                    >
                      <option value="text">文本</option>
                      <option value="textarea">长文本</option>
                      <option value="select">单选</option>
                      <option value="multi_select">多选</option>
                      <option value="number">数字</option>
                      <option value="date">日期</option>
                      <option value="boolean">是/否</option>
                    </select>
                  </div>
                  <div>
                    <label style={{ display: 'block', fontSize: 12, color: '#64748b', marginBottom: 4 }}>分组</label>
                    <input
                      className="form-input"
                      value={editForm.group_name || ''}
                      onChange={(e) => setEditForm({ ...editForm, group_name: e.target.value })}
                    />
                  </div>
                </div>
                <div style={{ marginBottom: 12 }}>
                  <label style={{ display: 'block', fontSize: 12, color: '#64748b', marginBottom: 4 }}>描述</label>
                  <input
                    className="form-input"
                    value={editForm.description || ''}
                    onChange={(e) => setEditForm({ ...editForm, description: e.target.value })}
                  />
                </div>
                <div style={{ display: 'flex', gap: 16, marginBottom: 12 }}>
                  <label style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 13, color: '#475569', cursor: 'pointer' }}>
                    <input
                      type="checkbox"
                      checked={editForm.is_active ?? true}
                      onChange={(e) => setEditForm({ ...editForm, is_active: e.target.checked })}
                    />
                    启用
                  </label>
                  <label style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 13, color: '#475569', cursor: 'pointer' }}>
                    <input
                      type="checkbox"
                      checked={editForm.is_required ?? false}
                      onChange={(e) => setEditForm({ ...editForm, is_required: e.target.checked })}
                    />
                    必填
                  </label>
                  <label style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 13, color: '#475569', cursor: 'pointer' }}>
                    <input
                      type="checkbox"
                      checked={!!(editForm.ai_config?.ai_enabled || editForm.ai_config?.prompt_template)}
                      onChange={(e) => setEditForm({
                        ...editForm,
                        ai_config: {
                          ...(editForm.ai_config || {}),
                          ai_enabled: e.target.checked,
                        }
                      })}
                    />
                    AI自动提取
                  </label>
                </div>
                {(editForm.ai_config?.ai_enabled || editForm.ai_config?.prompt_template) && (
                  <div style={{ marginBottom: 12 }}>
                    <label style={{ display: 'block', fontSize: 12, color: '#64748b', marginBottom: 4 }}>
                      AI提取提示词 (Prompt Template)
                    </label>
                    <div style={{ fontSize: 11, color: '#94a3b8', marginBottom: 6 }}>
                      可用变量：{`{title}`}（标题）、{`{abstract}`}（摘要）、{`{claims}`}（权利要求）、{`{description}`}（说明书）
                    </div>
                    <textarea
                      className="form-input"
                      style={{ minHeight: 150, fontFamily: 'monospace', fontSize: 12 }}
                      value={editForm.ai_config?.prompt_template || ''}
                      onChange={(e) => setEditForm({
                        ...editForm,
                        ai_config: {
                          ...(editForm.ai_config || {}),
                          prompt_template: e.target.value,
                          ai_enabled: true,
                        }
                      })}
                      placeholder="请输入提示词，告诉AI如何提取该字段..."
                    />
                  </div>
                )}
                <div style={{ display: 'flex', gap: 8 }}>
                  <button className="btn btn-primary" onClick={() => saveEdit(field.id)} disabled={saving}>
                    {saving ? '保存中...' : '保存'}
                  </button>
                  <button className="btn btn-secondary" onClick={cancelEdit}>
                    取消
                  </button>
                </div>
              </div>
            ) : (
              <div>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
                  <div>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 4 }}>
                      <span style={{ fontWeight: 600, fontSize: 14 }}>{field.name}</span>
                      <span style={{ fontSize: 11, color: '#94a3b8', fontFamily: 'monospace' }}>{field.key}</span>
                      <span style={{
                        padding: '1px 6px',
                        borderRadius: 4,
                        fontSize: 10,
                        background: '#f1f5f9',
                        color: '#64748b',
                      }}>
                        {fieldTypeLabels[field.field_type] || field.field_type}
                      </span>
                      {isAiField(field) && (
                        <span style={{
                          padding: '1px 6px',
                          borderRadius: 4,
                          fontSize: 10,
                          background: '#dbeafe',
                          color: '#2563eb',
                        }}>
                          AI
                        </span>
                      )}
                      {!field.is_active && (
                        <span style={{
                          padding: '1px 6px',
                          borderRadius: 4,
                          fontSize: 10,
                          background: '#fef2f2',
                          color: '#dc2626',
                        }}>
                          已禁用
                        </span>
                      )}
                    </div>
                    {field.description && (
                      <div style={{ fontSize: 12, color: '#64748b', marginBottom: 4 }}>{field.description}</div>
                    )}
                    {field.group_name && (
                      <div style={{ fontSize: 11, color: '#94a3b8' }}>分组: {field.group_name}</div>
                    )}
                    {isAiField(field) && field.ai_config?.prompt_template && (
                      <div style={{
                        marginTop: 8,
                        padding: 8,
                        background: '#f8fafc',
                        borderRadius: 4,
                        fontSize: 11,
                        color: '#475569',
                        maxHeight: 60,
                        overflow: 'hidden',
                        textOverflow: 'ellipsis',
                        display: '-webkit-box',
                        WebkitLineClamp: 2,
                        WebkitBoxOrient: 'vertical',
                      }}>
                        {field.ai_config.prompt_template}
                      </div>
                    )}
                  </div>
                  <div style={{ display: 'flex', gap: 4 }}>
                    <button
                      className="btn btn-secondary"
                      style={{ fontSize: 12, padding: '4px 10px' }}
                      onClick={() => startEdit(field)}
                    >
                      编辑
                    </button>
                    <button
                      className="btn btn-secondary"
                      style={{ fontSize: 12, padding: '4px 10px', color: '#dc2626', borderColor: '#fecaca' }}
                      onClick={() => handleDelete(field.id, field.name)}
                    >
                      删除
                    </button>
                  </div>
                </div>
              </div>
            )}
          </div>
        ))}
      </div>

      {fields.length === 0 && !loading && (
        <div style={{
          textAlign: 'center',
          padding: 60,
          color: '#94a3b8',
        }}>
          暂无自定义字段
        </div>
      )}
    </div>
  )
}
