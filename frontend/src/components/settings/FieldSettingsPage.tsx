import { useState, useEffect, useCallback } from 'react'
import { customFieldApi } from '../../api'
import type { CustomField, LinkConfig, LookupConfig, RollupConfig } from '../../types'
import { useAppStore } from '../../store'
import { getErrorMessage } from '../../lib/errors'
import FormulaEditor from './FormulaEditor'

interface RelationConfigFieldsProps {
  fieldType?: string
  field: Partial<CustomField>
  availableFields: CustomField[]
  onChange: (next: Partial<CustomField>) => void
}

function RelationConfigFields({ fieldType, field, availableFields, onChange }: RelationConfigFieldsProps) {
  if (fieldType === 'formula') {
    return (
      <FormulaEditor
        value={field.formula_config}
        fieldKey={field.key}
        availableFields={availableFields}
        onChange={formula_config => onChange({ formula_config })}
      />
    )
  }

  if (fieldType === 'link') {
    const config: LinkConfig = field.link_config || {
      target_table: 'projects',
      display_field: 'name',
      allow_multiple: true,
    }
    return (
      <div style={{ gridColumn: '1 / -1', padding: 12, background: '#f8fafc', border: '1px solid #e2e8f0', borderRadius: 6 }}>
        <div style={{ fontSize: 12, color: '#475569', fontWeight: 600, marginBottom: 10 }}>关联配置</div>
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
          <label style={{ fontSize: 12, color: '#64748b' }}>目标表
            <select className="form-input" style={{ marginTop: 4 }} value={config.target_table} onChange={e => onChange({ link_config: { ...config, target_table: e.target.value } })}>
              <option value="projects">项目</option>
              <option value="products">产品</option>
              <option value="patents">专利</option>
              <option value="people">人员</option>
              <option value="departments">部门</option>
              <option value="product-lines">产品线</option>
              <option value="tags">标签</option>
            </select>
          </label>
          <label style={{ fontSize: 12, color: '#64748b' }}>显示字段
            <input className="form-input" style={{ marginTop: 4 }} value={config.display_field || 'name'} onChange={e => onChange({ link_config: { ...config, display_field: e.target.value } })} placeholder="name 或 title" />
          </label>
        </div>
        <label style={{ display: 'flex', alignItems: 'center', gap: 6, marginTop: 10, fontSize: 12, color: '#475569' }}>
          <input type="checkbox" checked={config.allow_multiple !== false} onChange={e => onChange({ link_config: { ...config, allow_multiple: e.target.checked } })} />
          允许关联多条记录
        </label>
      </div>
    )
  }

  if (fieldType === 'lookup') {
    const config: LookupConfig = field.lookup_config || { link_field_key: '', source_field: 'name', allow_multiple: true }
    const linkFields = availableFields.filter(item => item.field_type === 'link')
    return (
      <div style={{ gridColumn: '1 / -1', padding: 12, background: '#f8fafc', border: '1px solid #e2e8f0', borderRadius: 6 }}>
        <div style={{ fontSize: 12, color: '#475569', fontWeight: 600, marginBottom: 10 }}>Lookup 配置</div>
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
          <label style={{ fontSize: 12, color: '#64748b' }}>关联字段
            <select className="form-input" style={{ marginTop: 4 }} value={config.link_field_key} onChange={e => onChange({ lookup_config: { ...config, link_field_key: e.target.value } })}>
              <option value="">请选择 Link 字段</option>
              {linkFields.map(item => <option key={item.key} value={item.key}>{item.name} ({item.key})</option>)}
            </select>
          </label>
          <label style={{ fontSize: 12, color: '#64748b' }}>拉取字段
            <input className="form-input" style={{ marginTop: 4 }} value={config.source_field} onChange={e => onChange({ lookup_config: { ...config, source_field: e.target.value } })} placeholder="例如 name、status" />
          </label>
        </div>
      </div>
    )
  }

  if (fieldType === 'rollup') {
    const config: RollupConfig = field.rollup_config || { link_field_key: '', source_field: '', aggregation: 'COUNT' }
    const linkFields = availableFields.filter(item => item.field_type === 'link')
    return (
      <div style={{ gridColumn: '1 / -1', padding: 12, background: '#f8fafc', border: '1px solid #e2e8f0', borderRadius: 6 }}>
        <div style={{ fontSize: 12, color: '#475569', fontWeight: 600, marginBottom: 10 }}>Rollup 配置</div>
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: 12 }}>
          <label style={{ fontSize: 12, color: '#64748b' }}>关联字段
            <select className="form-input" style={{ marginTop: 4 }} value={config.link_field_key} onChange={e => onChange({ rollup_config: { ...config, link_field_key: e.target.value } })}>
              <option value="">请选择 Link 字段</option>
              {linkFields.map(item => <option key={item.key} value={item.key}>{item.name} ({item.key})</option>)}
            </select>
          </label>
          <label style={{ fontSize: 12, color: '#64748b' }}>聚合字段
            <input className="form-input" style={{ marginTop: 4 }} value={config.source_field || ''} onChange={e => onChange({ rollup_config: { ...config, source_field: e.target.value } })} placeholder="COUNT 可留空" />
          </label>
          <label style={{ fontSize: 12, color: '#64748b' }}>聚合方式
            <select className="form-input" style={{ marginTop: 4 }} value={config.aggregation} onChange={e => onChange({ rollup_config: { ...config, aggregation: e.target.value as RollupConfig['aggregation'] } })}>
              <option value="COUNT">COUNT 计数</option>
              <option value="SUM">SUM 求和</option>
              <option value="AVG">AVG 平均</option>
              <option value="MIN">MIN 最小</option>
              <option value="MAX">MAX 最大</option>
            </select>
          </label>
        </div>
      </div>
    )
  }

  return null
}

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
    formula_config: { expression: '', return_type: 'text' },
  })
  const { setCustomFields } = useAppStore()

  const loadFields = useCallback(async () => {
    try {
      const data = await customFieldApi.list()
      setFields(data)
    } catch (e) {
      console.error('Failed to load fields:', e)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    // Load the field catalog after the component mounts.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    void loadFields()
  }, [loadFields])

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
      link_config: field.link_config ? { ...field.link_config } : undefined,
      lookup_config: field.lookup_config ? { ...field.lookup_config } : undefined,
      rollup_config: field.rollup_config ? { ...field.rollup_config } : undefined,
      formula_config: field.formula_config ? { ...field.formula_config } : undefined,
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
    } catch (error: unknown) {
      alert('保存失败: ' + getErrorMessage(error))
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
        formula_config: { expression: '', return_type: 'text' },
      })
    } catch (error: unknown) {
      alert('创建失败: ' + getErrorMessage(error))
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
    } catch (error: unknown) {
      alert('删除失败: ' + getErrorMessage(error))
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
    formula: '公式',
    link: '关联',
    lookup: 'Lookup',
    rollup: 'Rollup',
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
                <option value="formula">公式</option>
                <option value="link">关联记录（Link）</option>
                <option value="lookup">查找引用（Lookup）</option>
                <option value="rollup">汇总计算（Rollup）</option>
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
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12, marginBottom: 12 }}>
            <RelationConfigFields
              fieldType={newField.field_type}
              field={newField}
              availableFields={fields}
              onChange={next => setNewField({ ...newField, ...next })}
            />
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
              setNewField({ key: '', name: '', field_type: 'text', is_active: true, ai_config: {}, formula_config: { expression: '', return_type: 'text' } })
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
                      <option value="formula">公式</option>
                      <option value="link">关联记录（Link）</option>
                      <option value="lookup">查找引用（Lookup）</option>
                      <option value="rollup">汇总计算（Rollup）</option>
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
                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12, marginBottom: 12 }}>
                  <RelationConfigFields
                    fieldType={editForm.field_type}
                    field={editForm}
                    availableFields={fields}
                    onChange={next => setEditForm({ ...editForm, ...next })}
                  />
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
                    {field.field_type === 'formula' && field.formula_config?.expression && (
                      <div style={{ marginTop: 8, padding: 8, background: '#eff6ff', borderRadius: 4, fontSize: 11, color: '#1e40af', fontFamily: 'monospace', whiteSpace: 'pre-wrap' }}>
                        {field.formula_config.expression}
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
