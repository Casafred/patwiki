import { useState, useEffect } from 'react'
import { patentApi, productApi, projectApi, tagApi, aiApi } from '../../api'
import type { Patent, Product, Project, Tag, CustomField, AITask } from '../../types'

interface PatentDetailPageProps {
  patentId: number
  onBack: () => void
}

type Tab = 'basic' | 'technical' | 'risk' | 'ai' | 'custom' | 'relations'

export default function PatentDetailPage({ patentId, onBack }: PatentDetailPageProps) {
  const [patent, setPatent] = useState<Patent | null>(null)
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [editing, setEditing] = useState(false)
  const [activeTab, setActiveTab] = useState<Tab>('basic')
  const [aiFields, setAIFields] = useState<CustomField[]>([])
  const [products, setProducts] = useState<Product[]>([])
  const [projects, setProjects] = useState<Project[]>([])
  const [tags, setTags] = useState<Tag[]>([])
  const [formData, setFormData] = useState<Partial<Patent>>({})
  const [aiProcessing, setAiProcessing] = useState<string | null>(null)
  const [aiTaskInfo, setAiTaskInfo] = useState<AITask | null>(null)

  useEffect(() => {
    loadPatent()
    loadMeta()
  }, [patentId])

  const loadPatent = async () => {
    setLoading(true)
    try {
      const data = await patentApi.get(patentId)
      setPatent(data)
      setFormData(data)
    } catch (e) {
      console.error('Failed to load patent:', e)
      alert('加载专利失败')
    } finally {
      setLoading(false)
    }
  }

  const loadMeta = async () => {
    try {
      const [ai, ps, pjs, ts] = await Promise.all([
        aiApi.listAIFields(),
        productApi.list(),
        projectApi.list(),
        tagApi.list(),
      ])
      setAIFields(ai as any)
      setProducts(ps)
      setProjects(pjs)
      setTags(ts)
    } catch (e) {
      console.error('Failed to load meta:', e)
    }
  }

  const handleSave = async () => {
    if (!patent) return
    setSaving(true)
    try {
      const updates: any = { ...formData }
      // 把编辑期间累积的 tag_ids/project_ids 带上
      if ((patent as any)._editTagIds !== undefined) {
        updates.tag_ids = (patent as any)._editTagIds
      }
      if ((patent as any)._editProjectIds !== undefined) {
        updates.project_ids = (patent as any)._editProjectIds
      }
      // 移除只读字段
      delete updates.id
      delete updates.created_at
      delete updates.updated_at
      delete updates.ai_fields
      delete updates.tags
      delete updates.projects
      await patentApi.update(patent.id, updates)
      // 清理编辑态临时数据
      delete (patent as any)._editTagIds
      delete (patent as any)._editProjectIds
      setEditing(false)
      await loadPatent()
    } catch (e: any) {
      alert('保存失败: ' + (e?.message || '未知错误'))
    } finally {
      setSaving(false)
    }
  }

  const handleCancelEdit = () => {
    setFormData(patent || {})
    setEditing(false)
  }

  const handleDelete = async () => {
    if (!patent) return
    if (!confirm(`确定要删除专利 "${patent.title}" 吗？此操作不可撤销。`)) return
    try {
      await patentApi.delete(patent.id)
      onBack()
    } catch (e: any) {
      alert('删除失败: ' + (e?.message || '未知错误'))
    }
  }

  const handleAIProcess = async (fieldKey: string) => {
    if (!patent) return
    setAiProcessing(fieldKey)
    try {
      const task = await aiApi.process([patent.id], fieldKey)
      setAiTaskInfo(task)
      // 轮询任务状态
      pollTask(task.id)
    } catch (e: any) {
      alert('AI 处理启动失败: ' + (e?.response?.data?.detail || e?.message || '请先在设置页配置 LLM API'))
      setAiProcessing(null)
    }
  }

  const pollTask = async (taskId: number) => {
    const poll = async () => {
      try {
        const task = await aiApi.getTask(taskId)
        setAiTaskInfo(task)
        if (task.status === 'running' || task.status === 'pending') {
          setTimeout(poll, 1500)
        } else {
          setAiProcessing(null)
          // 完成后刷新专利数据
          await loadPatent()
        }
      } catch (e) {
        setAiProcessing(null)
      }
    }
    setTimeout(poll, 1500)
  }

  const updateField = (key: keyof Patent, value: any) => {
    setFormData(prev => ({ ...prev, [key]: value }))
  }

  if (loading) {
    return (
      <div className="loading-spinner">
        <div className="spinner"></div>
        加载中...
      </div>
    )
  }

  if (!patent) {
    return (
      <div className="empty-state">
        <div className="empty-state-icon">❌</div>
        <div className="empty-state-title">专利不存在</div>
        <button className="btn btn-primary" onClick={onBack}>返回列表</button>
      </div>
    )
  }

  const tabs: { key: Tab; label: string }[] = [
    { key: 'basic', label: '基础著录' },
    { key: 'technical', label: '技术信息' },
    { key: 'risk', label: '风险与应用' },
    { key: 'ai', label: 'AI 分析' },
    { key: 'custom', label: '自定义字段' },
    { key: 'relations', label: '关联关系' },
  ]

  return (
    <div>
      {/* 顶部导航 */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 16 }}>
        <button className="btn btn-secondary" onClick={onBack}>← 返回列表</button>
        <div style={{ flex: 1 }}>
          <h2 style={{ margin: 0, fontSize: 18, fontWeight: 600, color: '#0f172a' }}>
            {patent.title}
          </h2>
          <div style={{ fontSize: 12, color: '#64748b', marginTop: 4 }}>
            {patent.application_number && <span>申请号: {patent.application_number}</span>}
            {patent.publication_number && <span> | 公开号: {patent.publication_number}</span>}
            {patent.grant_number && <span> | 授权号: {patent.grant_number}</span>}
          </div>
        </div>
        {editing ? (
          <>
            <button className="btn btn-primary" onClick={handleSave} disabled={saving}>
              {saving ? '保存中...' : '💾 保存'}
            </button>
            <button className="btn btn-secondary" onClick={handleCancelEdit}>取消</button>
          </>
        ) : (
          <>
            <button className="btn btn-primary" onClick={() => setEditing(true)}>✏️ 编辑</button>
            <button className="btn btn-secondary" onClick={handleDelete} style={{ color: '#dc2626' }}>🗑️ 删除</button>
          </>
        )}
      </div>

      {/* Tab 导航 */}
      <div style={{ display: 'flex', gap: 4, borderBottom: '2px solid #e2e8f0', marginBottom: 20 }}>
        {tabs.map(tab => (
          <button
            key={tab.key}
            onClick={() => setActiveTab(tab.key)}
            style={{
              padding: '10px 16px',
              border: 'none',
              background: 'transparent',
              cursor: 'pointer',
              fontSize: 14,
              fontWeight: activeTab === tab.key ? 600 : 400,
              color: activeTab === tab.key ? '#2563eb' : '#64748b',
              borderBottom: activeTab === tab.key ? '2px solid #2563eb' : '2px solid transparent',
              marginBottom: '-2px',
            }}
          >
            {tab.label}
          </button>
        ))}
      </div>

      {/* Tab 内容 */}
      <div style={{ maxWidth: 900 }}>
        {activeTab === 'basic' && (
          <BasicInfoTab patent={patent} formData={formData} editing={editing} updateField={updateField} products={products} />
        )}
        {activeTab === 'technical' && (
          <TechnicalTab patent={patent} formData={formData} editing={editing} updateField={updateField} />
        )}
        {activeTab === 'risk' && (
          <RiskTab patent={patent} formData={formData} editing={editing} updateField={updateField} />
        )}
        {activeTab === 'ai' && (
          <AITab
            patent={patent}
            aiFields={aiFields}
            onProcess={handleAIProcess}
            processing={aiProcessing}
            taskInfo={aiTaskInfo}
          />
        )}
        {activeTab === 'custom' && (
          <CustomTab patent={patent} editing={editing} updateField={updateField} />
        )}
        {activeTab === 'relations' && (
          <RelationsTab patent={patent} tags={tags} projects={projects} editing={editing} updateField={updateField} />
        )}
      </div>
    </div>
  )
}

// ============ 基础著录 Tab ============
function BasicInfoTab({ patent, formData, editing, updateField, products }: {
  patent: Patent
  formData: Partial<Patent>
  editing: boolean
  updateField: (key: keyof Patent, value: any) => void
  products: Product[]
}) {
  return (
    <div className="detail-grid">
      <Field label="标题" required>
        {editing ? (
          <input className="form-input" value={formData.title || ''} onChange={e => updateField('title', e.target.value)} />
        ) : <div className="field-value">{patent.title}</div>}
      </Field>

      <Field label="申请号">
        {editing ? (
          <input className="form-input" value={formData.application_number || ''} onChange={e => updateField('application_number', e.target.value)} />
        ) : <div className="field-value mono">{patent.application_number || '-'}</div>}
      </Field>

      <Field label="公开号">
        {editing ? (
          <input className="form-input" value={formData.publication_number || ''} onChange={e => updateField('publication_number', e.target.value)} />
        ) : <div className="field-value mono">{patent.publication_number || '-'}</div>}
      </Field>

      <Field label="授权号">
        {editing ? (
          <input className="form-input" value={formData.grant_number || ''} onChange={e => updateField('grant_number', e.target.value)} />
        ) : <div className="field-value mono">{patent.grant_number || '-'}</div>}
      </Field>

      <Field label="申请人">
        {editing ? (
          <input className="form-input" value={formData.applicant || ''} onChange={e => updateField('applicant', e.target.value)} />
        ) : <div className="field-value">{patent.applicant || '-'}</div>}
      </Field>

      <Field label="发明人">
        {editing ? (
          <input className="form-input" value={formData.inventor || ''} onChange={e => updateField('inventor', e.target.value)} />
        ) : <div className="field-value">{patent.inventor || '-'}</div>}
      </Field>

      <Field label="代理人/代理机构">
        {editing ? (
          <input className="form-input" value={formData.agent || ''} onChange={e => updateField('agent', e.target.value)} />
        ) : <div className="field-value">{patent.agent || '-'}</div>}
      </Field>

      <Field label="受让人">
        {editing ? (
          <input className="form-input" value={formData.assignee || ''} onChange={e => updateField('assignee', e.target.value)} />
        ) : <div className="field-value">{patent.assignee || '-'}</div>}
      </Field>

      <Field label="申请日">
        {editing ? (
          <input type="date" className="form-input" value={formData.filing_date || ''} onChange={e => updateField('filing_date', e.target.value)} />
        ) : <div className="field-value">{patent.filing_date ? new Date(patent.filing_date).toLocaleDateString('zh-CN') : '-'}</div>}
      </Field>

      <Field label="公开日">
        {editing ? (
          <input type="date" className="form-input" value={formData.publication_date || ''} onChange={e => updateField('publication_date', e.target.value)} />
        ) : <div className="field-value">{patent.publication_date ? new Date(patent.publication_date).toLocaleDateString('zh-CN') : '-'}</div>}
      </Field>

      <Field label="授权日">
        {editing ? (
          <input type="date" className="form-input" value={formData.grant_date || ''} onChange={e => updateField('grant_date', e.target.value)} />
        ) : <div className="field-value">{patent.grant_date ? new Date(patent.grant_date).toLocaleDateString('zh-CN') : '-'}</div>}
      </Field>

      <Field label="法律状态">
        {editing ? (
          <select className="form-input" value={formData.legal_status || ''} onChange={e => updateField('legal_status', e.target.value)}>
            <option value="unknown">未知</option>
            <option value="pending">待审</option>
            <option value="published">公开</option>
            <option value="examining">实审中</option>
            <option value="granted">授权</option>
            <option value="rejected">驳回</option>
            <option value="withdrawn">撤回</option>
            <option value="deemed_withdrawn">视撤</option>
            <option value="expired">终止</option>
            <option value="abandoned">放弃</option>
          </select>
        ) : <div className="field-value">{patent.legal_status || '-'}</div>}
      </Field>

      <Field label="专利类型">
        {editing ? (
          <select className="form-input" value={formData.patent_type || ''} onChange={e => updateField('patent_type', e.target.value)}>
            <option value="invention">发明</option>
            <option value="utility_model">实用新型</option>
            <option value="design">外观设计</option>
            <option value="pct">PCT</option>
          </select>
        ) : <div className="field-value">{patent.patent_type || '-'}</div>}
      </Field>

      <Field label="国家">
        {editing ? (
          <input className="form-input" value={formData.country || ''} onChange={e => updateField('country', e.target.value)} />
        ) : <div className="field-value">{patent.country || '-'}</div>}
      </Field>

      <Field label="主 IPC">
        {editing ? (
          <input className="form-input" value={formData.ipc_main || ''} onChange={e => updateField('ipc_main', e.target.value)} />
        ) : <div className="field-value mono">{patent.ipc_main || '-'}</div>}
      </Field>

      <Field label="全部 IPC">
        {editing ? (
          <input className="form-input" value={formData.ipc_all || ''} onChange={e => updateField('ipc_all', e.target.value)} />
        ) : <div className="field-value mono">{patent.ipc_all || '-'}</div>}
      </Field>

      <Field label="主 CPC">
        {editing ? (
          <input className="form-input" value={formData.cpc_main || ''} onChange={e => updateField('cpc_main', e.target.value)} />
        ) : <div className="field-value mono">{patent.cpc_main || '-'}</div>}
      </Field>

      <Field label="优先权号">
        {editing ? (
          <input className="form-input" value={formData.priority_number || ''} onChange={e => updateField('priority_number', e.target.value)} />
        ) : <div className="field-value mono">{patent.priority_number || '-'}</div>}
      </Field>

      <Field label="优先权日">
        {editing ? (
          <input type="date" className="form-input" value={formData.priority_date || ''} onChange={e => updateField('priority_date', e.target.value)} />
        ) : <div className="field-value">{patent.priority_date ? new Date(patent.priority_date).toLocaleDateString('zh-CN') : '-'}</div>}
      </Field>

      <Field label="所属产品">
        {editing ? (
          <select className="form-input" value={formData.product_id || ''} onChange={e => updateField('product_id', e.target.value ? Number(e.target.value) : null)}>
            <option value="">未关联</option>
            {products.map(p => <option key={p.id} value={p.id}>{p.name}</option>)}
          </select>
        ) : <div className="field-value">{products.find(p => p.id === patent.product_id)?.name || '-'}</div>}
      </Field>

      <Field label="摘要" full>
        {editing ? (
          <textarea className="form-input" rows={4} value={formData.abstract || ''} onChange={e => updateField('abstract', e.target.value)} />
        ) : <div className="field-value">{patent.abstract || '-'}</div>}
      </Field>
    </div>
  )
}

// ============ 技术信息 Tab ============
function TechnicalTab({ patent, formData, editing, updateField }: {
  patent: Patent
  formData: Partial<Patent>
  editing: boolean
  updateField: (key: keyof Patent, value: any) => void
}) {
  return (
    <div className="detail-grid">
      <Field label="分类">
        {editing ? (
          <input className="form-input" value={formData.category || ''} onChange={e => updateField('category', e.target.value)} />
        ) : <div className="field-value">{patent.category || '-'}</div>}
      </Field>

      <Field label="子分类">
        {editing ? (
          <input className="form-input" value={formData.subcategory || ''} onChange={e => updateField('subcategory', e.target.value)} />
        ) : <div className="field-value">{patent.subcategory || '-'}</div>}
      </Field>

      <Field label="技术问题" full>
        {editing ? (
          <textarea className="form-input" rows={3} value={formData.technical_problem || ''} onChange={e => updateField('technical_problem', e.target.value)} />
        ) : <div className="field-value">{patent.technical_problem || '-'}</div>}
      </Field>

      <Field label="技术方案" full>
        {editing ? (
          <textarea className="form-input" rows={5} value={formData.technical_solution || ''} onChange={e => updateField('technical_solution', e.target.value)} />
        ) : <div className="field-value">{patent.technical_solution || '-'}</div>}
      </Field>

      <Field label="技术效果" full>
        {editing ? (
          <textarea className="form-input" rows={3} value={formData.technical_effect || ''} onChange={e => updateField('technical_effect', e.target.value)} />
        ) : <div className="field-value">{patent.technical_effect || '-'}</div>}
      </Field>

      <Field label="权利要求" full>
        {editing ? (
          <textarea className="form-input" rows={8} value={formData.claims || ''} onChange={e => updateField('claims', e.target.value)} />
        ) : <div className="field-value mono" style={{ whiteSpace: 'pre-wrap', fontSize: 13 }}>{patent.claims || '-'}</div>}
      </Field>

      <Field label="保护范围说明" full>
        {editing ? (
          <textarea className="form-input" rows={3} value={formData.scope_description || ''} onChange={e => updateField('scope_description', e.target.value)} />
        ) : <div className="field-value">{patent.scope_description || '-'}</div>}
      </Field>
    </div>
  )
}

// ============ 风险与应用 Tab ============
function RiskTab({ patent, formData, editing, updateField }: {
  patent: Patent
  formData: Partial<Patent>
  editing: boolean
  updateField: (key: keyof Patent, value: any) => void
}) {
  return (
    <div className="detail-grid">
      <Field label="是否有风险">
        {editing ? (
          <select className="form-input" value={formData.has_risk ? 'true' : 'false'} onChange={e => updateField('has_risk', e.target.value === 'true')}>
            <option value="false">无风险</option>
            <option value="true">有风险</option>
          </select>
        ) : <div className="field-value">{patent.has_risk ? '⚠️ 有风险' : '✅ 无风险'}</div>}
      </Field>

      <Field label="风险等级">
        {editing ? (
          <select className="form-input" value={formData.risk_level || 'none'} onChange={e => updateField('risk_level', e.target.value)}>
            <option value="none">无</option>
            <option value="low">低</option>
            <option value="medium">中</option>
            <option value="high">高</option>
            <option value="critical">严重</option>
          </select>
        ) : <div className="field-value">{patent.risk_level || '-'}</div>}
      </Field>

      <Field label="风险描述" full>
        {editing ? (
          <textarea className="form-input" rows={4} value={formData.risk_description || ''} onChange={e => updateField('risk_description', e.target.value)} />
        ) : <div className="field-value">{patent.risk_description || '-'}</div>}
      </Field>

      <Field label="关联模块">
        {editing ? (
          <input className="form-input" value={formData.module || ''} onChange={e => updateField('module', e.target.value)} />
        ) : <div className="field-value">{patent.module || '-'}</div>}
      </Field>

      <Field label="应用状态">
        {editing ? (
          <input className="form-input" value={formData.application_status || ''} onChange={e => updateField('application_status', e.target.value)} placeholder="如：已应用 / 评估中 / 未应用" />
        ) : <div className="field-value">{patent.application_status || '-'}</div>}
      </Field>

      <Field label="备注" full>
        {editing ? (
          <textarea className="form-input" rows={4} value={formData.notes || ''} onChange={e => updateField('notes', e.target.value)} />
        ) : <div className="field-value">{patent.notes || '-'}</div>}
      </Field>
    </div>
  )
}

// ============ AI 分析 Tab ============
function AITab({ patent, aiFields, onProcess, processing, taskInfo }: {
  patent: Patent
  aiFields: CustomField[]
  onProcess: (fieldKey: string) => void
  processing: string | null
  taskInfo: AITask | null
}) {
  const aiData = patent.ai_fields || {}

  return (
    <div>
      {taskInfo && (
        <div style={{
          padding: 12, marginBottom: 16, borderRadius: 8,
          background: taskInfo.status === 'completed' ? '#f0fdf4' : taskInfo.status === 'failed' ? '#fef2f2' : '#eff6ff',
          border: `1px solid ${taskInfo.status === 'completed' ? '#bbf7d0' : taskInfo.status === 'failed' ? '#fecaca' : '#bfdbfe'}`,
        }}>
          <div style={{ fontWeight: 600, marginBottom: 4 }}>
            {taskInfo.status === 'completed' ? '✅ AI 处理完成' :
             taskInfo.status === 'failed' ? '❌ AI 处理失败' :
             `⏳ 处理中... (${taskInfo.processed_items}/${taskInfo.total_items})`}
          </div>
          {taskInfo.status === 'completed' && (
            <div style={{ fontSize: 12, color: '#475569' }}>
              成功 {taskInfo.success_count} 条 / 失败 {taskInfo.failed_count} 条
            </div>
          )}
        </div>
      )}

      {aiFields.length === 0 ? (
        <div className="empty-state">
          <div className="empty-state-icon">🤖</div>
          <div className="empty-state-title">暂无 AI 字段</div>
          <div className="empty-state-desc">AI 字段模板在系统初始化时自动创建，若未生成请检查后端 init_data</div>
        </div>
      ) : (
        <div className="detail-grid">
          {aiFields.map(field => {
            const value = aiData[field.key]
            const isProcessing = processing === field.key
            return (
              <Field key={field.id} label={field.name} full>
                <div style={{ display: 'flex', gap: 8, alignItems: 'flex-start' }}>
                  <div className="field-value" style={{
                    flex: 1,
                    padding: 12,
                    background: value ? '#f8fafc' : '#fffbeb',
                    border: `1px solid ${value ? '#e2e8f0' : '#fde68a'}`,
                    borderRadius: 6,
                    minHeight: 60,
                    whiteSpace: 'pre-wrap',
                    fontSize: 13,
                  }}>
                    {value || '尚未生成，点击右侧按钮运行 AI 抽取'}
                  </div>
                  <button
                    className="btn btn-primary"
                    onClick={() => onProcess(field.key)}
                    disabled={isProcessing || !!processing}
                    style={{ flexShrink: 0 }}
                  >
                    {isProcessing ? '⏳ 处理中' : '🤖 生成'}
                  </button>
                </div>
                {field.description && (
                  <div style={{ fontSize: 11, color: '#94a3b8', marginTop: 4 }}>{field.description}</div>
                )}
              </Field>
            )
          })}
        </div>
      )}
    </div>
  )
}

// ============ 自定义字段 Tab ============
function CustomTab({ patent, editing, updateField }: {
  patent: Patent
  editing: boolean
  updateField: (key: keyof Patent, value: any) => void
}) {
  const customData = patent.custom_fields || {}
  const keys = Object.keys(customData)

  return (
    <div>
      {keys.length === 0 ? (
        <div className="empty-state">
          <div className="empty-state-icon">📝</div>
          <div className="empty-state-title">暂无自定义字段数据</div>
          <div className="empty-state-desc">自定义字段可在"自定义字段管理"页面定义，导入时映射或手动填写</div>
        </div>
      ) : (
        <div className="detail-grid">
          {keys.map(key => (
            <Field key={key} label={key}>
              {editing ? (
                <input
                  className="form-input"
                  value={customData[key] || ''}
                  onChange={e => {
                    const newData = { ...customData, [key]: e.target.value }
                    updateField('custom_fields', newData)
                  }}
                />
              ) : <div className="field-value">{String(customData[key] ?? '-')}</div>}
            </Field>
          ))}
        </div>
      )}
    </div>
  )
}

// ============ 关联关系 Tab ============
function RelationsTab({ patent, tags, projects, editing, updateField }: {
  patent: Patent
  tags: Tag[]
  projects: Project[]
  editing: boolean
  updateField: (key: keyof Patent, value: any) => void
}) {
  const patentTags = patent.tags || []
  const patentProjects = patent.projects || []

  // 编辑态下从 patent 现有标签初始化，后续变更通过 updateField 写入 formData
  // 这里直接用 patent 数据作为初始选中态，保存时由父组件的 formData 决定
  const currentTagIds = (editing ? ((patent as any)._editTagIds ?? patentTags.map(t => t.id)) : patentTags.map(t => t.id))
  const currentProjectIds = (editing ? ((patent as any)._editProjectIds ?? patentProjects.map(p => p.id)) : patentProjects.map(p => p.id))

  return (
    <div className="detail-grid">
      <Field label="标签" full>
        {editing ? (
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8 }}>
            {tags.map(tag => {
              const selected = currentTagIds.includes(tag.id)
              return (
                <label key={tag.id} style={{
                  display: 'flex', alignItems: 'center', gap: 4,
                  padding: '4px 10px', borderRadius: 16, fontSize: 13,
                  background: selected ? '#dbeafe' : '#f1f5f9',
                  cursor: 'pointer',
                  border: `1px solid ${selected ? '#93c5fd' : '#e2e8f0'}`,
                }}>
                  <input
                    type="checkbox"
                    checked={selected}
                    onChange={e => {
                      const next = e.target.checked
                        ? [...currentTagIds, tag.id]
                        : currentTagIds.filter((id: number) => id !== tag.id)
                      ;(patent as any)._editTagIds = next
                      updateField('tag_ids' as any, next)
                    }}
                    style={{ marginRight: 4 }}
                  />
                  <span style={{ color: tag.color || '#475569' }}>●</span>
                  {tag.name}
                </label>
              )
            })}
          </div>
        ) : (
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>
            {patentTags.length === 0 ? <span style={{ color: '#94a3b8' }}>-</span> :
              patentTags.map(tag => (
                <span key={tag.id} style={{
                  padding: '3px 10px', borderRadius: 16, fontSize: 12,
                  background: '#f1f5f9', color: tag.color || '#475569',
                }}>
                  ● {tag.name}
                </span>
              ))
            }
          </div>
        )}
      </Field>

      <Field label="关联项目" full>
        {editing ? (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
            {projects.map(proj => {
              const selected = currentProjectIds.includes(proj.id)
              return (
                <label key={proj.id} style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 13 }}>
                  <input
                    type="checkbox"
                    checked={selected}
                    onChange={e => {
                      const next = e.target.checked
                        ? [...currentProjectIds, proj.id]
                        : currentProjectIds.filter((id: number) => id !== proj.id)
                      ;(patent as any)._editProjectIds = next
                      updateField('project_ids' as any, next)
                    }}
                  />
                  {proj.name} {proj.status && <span style={{ color: '#94a3b8' }}>({proj.status})</span>}
                </label>
              )
            })}
          </div>
        ) : (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
            {patentProjects.length === 0 ? <span style={{ color: '#94a3b8' }}>-</span> :
              patentProjects.map(proj => (
                <div key={proj.id} style={{ fontSize: 13 }}>
                  📁 {proj.name} {proj.module && <span style={{ color: '#94a3b8' }}>· {proj.module}</span>}
                </div>
              ))
            }
          </div>
        )}
      </Field>
    </div>
  )
}

// ============ 通用 Field 组件 ============
function Field({ label, children, required, full }: {
  label: string
  children: React.ReactNode
  required?: boolean
  full?: boolean
}) {
  return (
    <div style={{
      display: 'flex',
      flexDirection: 'column',
      gap: 4,
      gridColumn: full ? '1 / -1' : undefined,
    }}>
      <label style={{ fontSize: 12, color: '#64748b', fontWeight: 500 }}>
        {label} {required && <span style={{ color: '#dc2626' }}>*</span>}
      </label>
      {children}
    </div>
  )
}
