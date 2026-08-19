import { useState, useEffect, useCallback } from 'react'
import {
  patentService as patentApi,
  productService as productApi,
  projectService as projectApi,
  tagService as tagApi,
  aiService as aiApi,
} from '../../services'
import type {
  Patent,
  Product,
  Project,
  Tag,
  CustomField,
  AITask,
  AIFieldValue,
  PatentHistory,
  PatentIdentifier,
  PatentFieldSource,
  PatentIdentityConflict,
} from '../../types'
import { getErrorMessage } from '../../lib/errors'
import PatentShareDialog from './PatentShareDialog'
import PatentGraph from './PatentGraph'
import CommentPanel from './CommentPanel'
import AttachmentField from '../common/AttachmentField'

interface PatentDetailPageProps {
  patentId: number
  onBack: () => void
}

type Tab = 'basic' | 'identity' | 'technical' | 'risk' | 'ai' | 'attachments' | 'custom' | 'relations' | 'history' | 'comments'
type PatentEditData = Partial<Patent> & { tag_ids?: number[]; project_ids?: number[] }

export default function PatentDetailPage({ patentId, onBack }: PatentDetailPageProps) {
  const [patent, setPatent] = useState<Patent | null>(null)
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [editing, setEditing] = useState(false)
  const [activeTab, setActiveTab] = useState<Tab>('basic')
  const [aiFields, setAIFields] = useState<CustomField[]>([])
  const [aiValues, setAIValues] = useState<AIFieldValue[]>([])
  const [products, setProducts] = useState<Product[]>([])
  const [projects, setProjects] = useState<Project[]>([])
  const [tags, setTags] = useState<Tag[]>([])
  const [formData, setFormData] = useState<PatentEditData>({})
  const [aiProcessing, setAiProcessing] = useState<string | null>(null)
  const [aiTaskInfo, setAiTaskInfo] = useState<AITask | null>(null)
  const [history, setHistory] = useState<PatentHistory[]>([])
  const [historyLoading, setHistoryLoading] = useState(false)
  const [identifiers, setIdentifiers] = useState<PatentIdentifier[]>([])
  const [fieldSources, setFieldSources] = useState<PatentFieldSource[]>([])
  const [identityConflicts, setIdentityConflicts] = useState<PatentIdentityConflict[]>([])
  const [identityLoading, setIdentityLoading] = useState(false)
  const [showShareDialog, setShowShareDialog] = useState(false)
  const [openCommentCount, setOpenCommentCount] = useState(0)

  const loadPatent = useCallback(async () => {
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
  }, [patentId])

  const loadHistory = useCallback(async () => {
    setHistoryLoading(true)
    try {
      const list = await patentApi.getHistory(patentId)
      setHistory(list)
    } catch (e) {
      console.error('Failed to load history:', e)
    } finally {
      setHistoryLoading(false)
    }
  }, [patentId])

  const loadIdentity = useCallback(async () => {
    setIdentityLoading(true)
    try {
      const [identityRows, sourceRows, conflictRows] = await Promise.all([
        patentApi.identifiers(patentId),
        patentApi.fieldSources(patentId),
        patentApi.identityConflicts(patentId),
      ])
      setIdentifiers(identityRows)
      setFieldSources(sourceRows)
      setIdentityConflicts(conflictRows)
    } catch (e) {
      console.error('Failed to load patent identity:', e)
      setIdentifiers([])
      setFieldSources([])
      setIdentityConflicts([])
    } finally {
      setIdentityLoading(false)
    }
  }, [patentId])

  const loadAIValues = useCallback(async () => {
    try {
      const values = await aiApi.listValues(patentId)
      setAIValues(values)
    } catch (e) {
      console.error('Failed to load AI values:', e)
      setAIValues([])
    }
  }, [patentId])

  const loadMeta = useCallback(async () => {
    try {
      const [ai, ps, pjs, ts] = await Promise.all([
        aiApi.listAIFields(),
        productApi.list(),
        projectApi.list(),
        tagApi.list(),
      ])
      setAIFields(ai)
      setProducts(ps)
      setProjects(pjs)
      setTags(ts)
    } catch (e) {
      console.error('Failed to load meta:', e)
    }
  }, [])

  useEffect(() => {
    // These requests synchronize the detail view with the selected patent.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    void loadPatent()
    void loadMeta()
    void loadHistory()
    void loadIdentity()
    void loadAIValues()
  }, [loadAIValues, loadHistory, loadIdentity, loadMeta, loadPatent])

  const handleSave = async () => {
    if (!patent) return
    setSaving(true)
    try {
      const updates: PatentEditData = { ...formData }
      // 移除只读字段
      delete updates.id
      delete updates.created_at
      delete updates.updated_at
      delete updates.ai_fields
      delete updates.tags
      delete updates.projects
      await patentApi.update(patent.id, updates)
      setEditing(false)
      await loadPatent()
      await loadHistory()
    } catch (error: unknown) {
      alert('保存失败: ' + getErrorMessage(error, '未知错误'))
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
    } catch (error: unknown) {
      alert('删除失败: ' + getErrorMessage(error, '未知错误'))
    }
  }

  const handleAIProcess = async (fieldKey: string, forceRecalculate = false) => {
    if (!patent) return
    setAiProcessing(fieldKey)
    try {
      const task = await aiApi.process([patent.id], fieldKey, { force_recalculate: forceRecalculate })
      setAiTaskInfo(task)
      // 轮询任务状态
      pollTask(task.id)
    } catch (error: unknown) {
      alert('AI 处理启动失败: ' + getErrorMessage(error, '请先在设置页配置 LLM API'))
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
          await Promise.all([loadPatent(), loadAIValues(), loadHistory()])
        }
      } catch {
        setAiProcessing(null)
      }
    }
    setTimeout(poll, 1500)
  }

  const handleAIOverride = async (fieldKey: string, value: string) => {
    if (!patent) return
    try {
      await aiApi.overrideValue(patent.id, fieldKey, value)
      await Promise.all([loadPatent(), loadAIValues(), loadHistory()])
    } catch (error: unknown) {
      alert('保存人工覆盖失败: ' + getErrorMessage(error, '未知错误'))
    }
  }

  const handleClearAIOverride = async (fieldKey: string) => {
    if (!patent) return
    try {
      await aiApi.clearOverride(patent.id, fieldKey)
      await Promise.all([loadPatent(), loadAIValues(), loadHistory()])
    } catch (error: unknown) {
      alert('清除人工覆盖失败: ' + getErrorMessage(error, '未知错误'))
    }
  }

  const updateField = (key: keyof PatentEditData, value: unknown) => {
    setFormData(prev => ({ ...prev, [key]: value } as PatentEditData))
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
        <div className="empty-state-title">专利不存在</div>
        <button className="btn btn-primary" onClick={onBack}>返回列表</button>
      </div>
    )
  }

  const tabs: { key: Tab; label: string }[] = [
    { key: 'basic', label: '基础著录' },
    { key: 'identity', label: '身份与来源' },
    { key: 'technical', label: '技术信息' },
    { key: 'risk', label: '风险与应用' },
    { key: 'ai', label: 'AI 分析' },
    { key: 'attachments', label: '关联附件' },
    { key: 'custom', label: '自定义字段' },
    { key: 'relations', label: '关联关系' },
    { key: 'history', label: `修改历史${history.length > 0 ? ` (${history.length})` : ''}` },
    { key: 'comments', label: `评论${openCommentCount > 0 ? ` (${openCommentCount})` : ''}` },
  ]

  return (
    <>
      <div className="detail-page">
      {/* 顶部导航 */}
      <div className="detail-header">
        <button className="btn btn-ghost detail-back" onClick={onBack}>‹ 返回专利列表</button>
        <div className="detail-identity">
          <h2>
            {patent.title}
          </h2>
          <div className="detail-identifiers">
            {patent.application_number && <span>申请号 {patent.application_number}</span>}
            {patent.publication_number && <span>公开号 {patent.publication_number}</span>}
            {patent.grant_number && <span>授权号 {patent.grant_number}</span>}
          </div>
          <div className="detail-meta">
            {patent.created_at && <span>创建于 {new Date(patent.created_at).toLocaleString('zh-CN')}</span>}
            {patent.updated_at && patent.updated_at !== patent.created_at && (
              <span> · 最后修改于 {new Date(patent.updated_at).toLocaleString('zh-CN')}</span>
            )}
            {history.length > 0 && (
              <span> · 共 {history.length} 次修改</span>
            )}
          </div>
        </div>
        <div className="detail-actions">
          {editing ? (
            <>
              <button className="btn btn-primary" onClick={handleSave} disabled={saving}>{saving ? '保存中...' : '保存修改'}</button>
              <button className="btn btn-secondary" onClick={handleCancelEdit}>取消</button>
            </>
          ) : (
            <>
              <button className="btn btn-secondary" onClick={() => setShowShareDialog(true)}>分享</button>
              <button className="btn btn-primary" onClick={() => setEditing(true)}>编辑专利</button>
              <button className="btn btn-danger" onClick={handleDelete}>删除</button>
            </>
          )}
        </div>
      </div>

      {/* Tab 导航 */}
      <div className="detail-tabs" role="tablist" aria-label="专利详情分区">
        {tabs.map(tab => (
          <button
            key={tab.key}
            onClick={() => setActiveTab(tab.key)}
            className={`detail-tab ${activeTab === tab.key ? 'active' : ''}`}
            role="tab"
            aria-selected={activeTab === tab.key}
          >
            {tab.label}
          </button>
        ))}
      </div>

      {/* Tab 内容 */}
      <div className="detail-content">
        {activeTab === 'basic' && (
          <BasicInfoTab patent={patent} formData={formData} editing={editing} updateField={updateField} products={products} />
        )}
        {activeTab === 'identity' && (
          <IdentityTab
            patent={patent}
            identifiers={identifiers}
            fieldSources={fieldSources}
            identityConflicts={identityConflicts}
            loading={identityLoading}
          />
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
            aiValues={aiValues}
            onProcess={handleAIProcess}
            onOverride={handleAIOverride}
            onClearOverride={handleClearAIOverride}
            processing={aiProcessing}
            taskInfo={aiTaskInfo}
          />
        )}
        {activeTab === 'custom' && (
          <CustomTab patent={patent} editing={editing} updateField={updateField} />
        )}
        {activeTab === 'relations' && (
          <RelationsTab patent={patent} formData={formData} tags={tags} projects={projects} editing={editing} updateField={updateField} />
        )}
        {activeTab === 'history' && (
          <HistoryTab patent={patent} history={history} loading={historyLoading} onReload={loadHistory} />
        )}
        {activeTab === 'attachments' && (
          <AttachmentsTab patent={patent} />
        )}
        {activeTab === 'comments' && (
          <CommentPanel patentId={patent.id} onCountChange={setOpenCommentCount} />
        )}
      </div>
      </div>
      {showShareDialog && (
        <PatentShareDialog patentId={patent.id} onClose={() => setShowShareDialog(false)} />
      )}
    </>
  )
}

function AttachmentsTab({ patent }: { patent: Patent }) {
  return (
    <div>
      <div style={{ color: '#64748b', fontSize: 13, marginBottom: 14 }}>
        将 Outlook 邮件、分享 PPT、专利原文 PDF、样机图片、Excel、Word 和会议材料直接关联到本专利。
      </div>
      <AttachmentField
        patentId={patent.id}
        databaseId={patent.database_id ?? null}
        fieldKey="attachments"
        value={patent.custom_fields?.attachments ?? null}
      />
    </div>
  )
}

const IDENTIFIER_TYPE_LABELS: Record<string, string> = {
  application: '申请号',
  publication: '公开号',
  grant: '授权号',
  external: '外部编号',
}

const FIELD_SOURCE_LABELS: Record<string, string> = {
  manual: '人工',
  bulk: '批量',
  import: '外部导入',
  governance: '治理回填',
  governance_revert: '治理恢复',
  ai: 'AI',
  api: 'API',
}

function formatDateTime(value?: string | null): string {
  return value ? new Date(value).toLocaleString('zh-CN') : '-'
}

function IdentityTab({ patent, identifiers, fieldSources, identityConflicts, loading }: {
  patent: Patent
  identifiers: PatentIdentifier[]
  fieldSources: PatentFieldSource[]
  identityConflicts: PatentIdentityConflict[]
  loading: boolean
}) {
  const [copied, setCopied] = useState<string | null>(null)

  const copyValue = async (value: string) => {
    try {
      await navigator.clipboard.writeText(value)
      setCopied(value)
      window.setTimeout(() => setCopied(current => current === value ? null : current), 1600)
    } catch {
      setCopied(null)
    }
  }

  const projections = [
    { label: '申请号', value: patent.application_number },
    { label: '公开号', value: patent.publication_number },
    { label: '授权号', value: patent.grant_number },
  ]

  return (
    <div className="identity-tab-content">
      <section className="identity-summary-panel">
        <div>
          <div className="section-eyebrow">专利身份锚点</div>
          <h3>公开号优先，申请链归并</h3>
          <p>申请号、公开号和授权号只在同一法域申请链内归入本篇专利；同族成员仍保持独立记录。</p>
        </div>
        <div className={`identity-status ${identifiers.length > 0 ? 'is-ready' : 'is-missing'}`}>
          <strong>{identifiers.length > 0 ? '身份索引已建立' : '身份索引待补充'}</strong>
          <span>{identifiers.length} 条身份事实</span>
        </div>
      </section>

      <section className="identity-section">
        <div className="identity-section-heading">
          <div>
            <h3>当前主表投影</h3>
            <p>详情页兼容展示值；真正的匹配依据和历史别名见下方身份索引。</p>
          </div>
        </div>
        <div className="identity-projection-grid">
          {projections.map(item => (
            <div className="identity-projection" key={item.label}>
              <span>{item.label}</span>
              <strong className="mono">{item.value || '未填写'}</strong>
              {item.value && (
                <button className="btn btn-ghost identity-copy-btn" onClick={() => void copyValue(item.value || '')}>
                  {copied === item.value ? '已复制' : '复制'}
                </button>
              )}
            </div>
          ))}
        </div>
      </section>

      {identityConflicts.length > 0 && (
        <section className="identity-section identity-conflict-section">
          <div className="identity-section-heading">
            <div>
              <h3>待确认身份冲突</h3>
              <p>以下导入行的多个号码命中了不同专利。系统已阻断整行写入，请依据原始行确认后再治理。</p>
            </div>
            <span className="identity-conflict-count">{identityConflicts.length} 行</span>
          </div>
          <div className="identity-conflict-list">
            {identityConflicts.map(conflict => (
              <div className="identity-conflict-row" key={conflict.source_row_id}>
                <div>
                  <strong>{conflict.source_table_title || conflict.filename}</strong>
                  <span>{conflict.worksheet_name ? `${conflict.worksheet_name} · ` : ''}第 {conflict.source_row} 行</span>
                </div>
                <div className="identity-conflict-detail">
                  <span>{conflict.resolution_reason || '身份命中多个专利'}</span>
                  <span>候选专利：{conflict.candidate_patent_ids.map(id => `#${id}`).join('、')}</span>
                </div>
                <div className="identity-conflict-values">
                  {conflict.observations.slice(0, 4).map(item => (
                    <span key={item.id}><b>{item.source_field_name}</b>：{item.raw_value || item.candidate_value || '-'}</span>
                  ))}
                </div>
                {patent.database_id && (
                  <a className="btn btn-secondary identity-governance-link" href={`/db/${patent.database_id}/governance?source_row_id=${conflict.source_row_id}`}>
                    打开治理工作台
                  </a>
                )}
              </div>
            ))}
          </div>
        </section>
      )}

      <section className="identity-section">
        <div className="identity-section-heading">
          <div>
            <h3>身份索引与来源别名</h3>
            <p>规范化值只用于匹配，原始写法永久保留；来源时间是该身份事实的观察时间。</p>
          </div>
          {loading && <span className="identity-loading">刷新中...</span>}
        </div>
        {identifiers.length === 0 ? (
          <div className="identity-empty">尚未建立身份索引。可以先在基础著录中补充公开号，再通过导入或保存动作建立来源记录。</div>
        ) : (
          <div className="identity-table-wrap">
            <table className="identity-table">
              <thead>
                <tr>
                  <th>类型</th>
                  <th>原始写法</th>
                  <th>规范化值</th>
                  <th>法域 / kind code</th>
                  <th>来源</th>
                  <th>来源时间</th>
                </tr>
              </thead>
              <tbody>
                {identifiers.map(identifier => (
                  <tr key={identifier.id}>
                    <td>
                      <span className="identity-type">{IDENTIFIER_TYPE_LABELS[identifier.identifier_type] || identifier.identifier_type}</span>
                      {identifier.is_primary && <span className="identity-primary">主标识</span>}
                    </td>
                    <td>
                      <div className="identity-raw-value">
                        <span className="mono">{identifier.raw_value || '-'}</span>
                        <button className="btn btn-ghost identity-copy-btn" onClick={() => void copyValue(identifier.raw_value)}>
                          {copied === identifier.raw_value ? '已复制' : '复制'}
                        </button>
                      </div>
                      {identifier.raw_values.length > 1 && (
                        <div className="identity-aliases">别名：{identifier.raw_values.join(' / ')}</div>
                      )}
                    </td>
                    <td className="mono">{identifier.normalized_value || '-'}</td>
                    <td className="mono">{[identifier.jurisdiction_code, identifier.kind_code].filter(Boolean).join(' / ') || '-'}</td>
                    <td>{identifier.source_system || '未标注来源'}</td>
                    <td>{formatDateTime(identifier.source_timestamp)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>

      <section className="identity-section">
        <div className="identity-section-heading">
          <div>
            <h3>字段最近来源</h3>
            <p>这里显示每个已记录字段最近一次写入的来源；完整变更前后值仍在 Wiki 历史中。</p>
          </div>
        </div>
        {fieldSources.length === 0 ? (
          <div className="identity-empty">暂无字段来源历史。首次导入或人工保存后，这里会显示来源和时间。</div>
        ) : (
          <div className="field-source-list">
            {fieldSources.map(source => (
              <div className="field-source-row" key={source.field_key}>
                <div className="field-source-name">
                  <strong>{source.field_display_name || source.field_key}</strong>
                  <span className="mono">{source.field_key}</span>
                </div>
                <div className="field-source-value">{source.current_value || '（空）'}</div>
                <div className="field-source-meta">
                  <span className="source-badge">{FIELD_SOURCE_LABELS[source.last_source || ''] || source.last_source || '未知来源'}</span>
                  <span>{source.last_changed_by || '未标注操作者'}</span>
                  <span>{formatDateTime(source.last_changed_at)}</span>
                  {source.last_source_view_name && <span>视图：{source.last_source_view_name}</span>}
                  {source.source_table_title && <span>来源表：{source.source_table_title}</span>}
                  {source.source_row && <span>第 {source.source_row} 行</span>}
                </div>
              </div>
            ))}
          </div>
        )}
      </section>
    </div>
  )
}

// ============ 基础著录 Tab ============
function BasicInfoTab({ patent, formData, editing, updateField, products }: {
  patent: Patent
  formData: PatentEditData
  editing: boolean
  updateField: (key: keyof PatentEditData, value: unknown) => void
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
  formData: PatentEditData
  editing: boolean
  updateField: (key: keyof PatentEditData, value: unknown) => void
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
  formData: PatentEditData
  editing: boolean
  updateField: (key: keyof PatentEditData, value: unknown) => void
}) {
  return (
    <div className="detail-grid">
      <Field label="是否有风险">
        {editing ? (
          <select className="form-input" value={formData.has_risk ? 'true' : 'false'} onChange={e => updateField('has_risk', e.target.value === 'true')}>
            <option value="false">无风险</option>
            <option value="true">有风险</option>
          </select>
        ) : <div className="field-value">{patent.has_risk ? '有风险' : '无风险'}</div>}
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
function formatAIValue(value: unknown): string {
  if (value === null || value === undefined || value === '') return ''
  return typeof value === 'string' ? value : JSON.stringify(value) ?? String(value)
}

function AITab({ patent, aiFields, aiValues, onProcess, onOverride, onClearOverride, processing, taskInfo }: {
  patent: Patent
  aiFields: CustomField[]
  aiValues: AIFieldValue[]
  onProcess: (fieldKey: string, forceRecalculate?: boolean) => void
  onOverride: (fieldKey: string, value: string) => Promise<void>
  onClearOverride: (fieldKey: string) => Promise<void>
  processing: string | null
  taskInfo: AITask | null
}) {
  const aiData = patent.ai_fields || {}
  const [editingKey, setEditingKey] = useState<string | null>(null)
  const [draftValue, setDraftValue] = useState('')
  const [savingKey, setSavingKey] = useState<string | null>(null)

  const startEditing = (fieldKey: string, value: unknown) => {
    setEditingKey(fieldKey)
    setDraftValue(formatAIValue(value))
  }

  const saveOverride = async (fieldKey: string) => {
    setSavingKey(fieldKey)
    try {
      await onOverride(fieldKey, draftValue)
      setEditingKey(null)
    } finally {
      setSavingKey(null)
    }
  }

  return (
    <div>
      {taskInfo && (
        <div style={{
          padding: 12, marginBottom: 16, borderRadius: 8,
          background: taskInfo.status === 'completed' ? '#f0fdf4' : taskInfo.status === 'failed' ? '#fef2f2' : '#eff6ff',
          border: `1px solid ${taskInfo.status === 'completed' ? '#bbf7d0' : taskInfo.status === 'failed' ? '#fecaca' : '#bfdbfe'}`,
        }}>
          <div style={{ fontWeight: 600, marginBottom: 4 }}>
            {taskInfo.status === 'completed' ? 'AI 处理完成' :
             taskInfo.status === 'failed' ? 'AI 处理失败' :
             `处理中... (${taskInfo.processed_items}/${taskInfo.total_items})`}
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
          <div className="empty-state-title">暂无 AI 字段</div>
          <div className="empty-state-desc">AI 字段模板在系统初始化时自动创建，若未生成请检查后端 init_data</div>
        </div>
      ) : (
         <div className="detail-grid">
           {aiFields.map(field => {
             const stored = aiValues.find(item => item.field_key === field.key)
             const value = stored?.value ?? aiData[field.key]
             const generatedValue = stored?.generated_value
             const hasValue = value !== null && value !== undefined && value !== ''
             const isOverridden = stored?.is_overridden === true
             const isProcessing = processing === field.key
             return (
               <Field key={field.id} label={field.name} full>
                 {editingKey === field.key ? (
                   <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
                     <textarea
                       className="form-input"
                       rows={4}
                       value={draftValue}
                       onChange={e => setDraftValue(e.target.value)}
                       autoFocus
                     />
                     <div style={{ display: 'flex', gap: 8 }}>
                       <button
                         className="btn btn-primary"
                         onClick={() => void saveOverride(field.key)}
                         disabled={savingKey === field.key}
                       >
                         {savingKey === field.key ? '保存中...' : '保存覆盖'}
                       </button>
                       <button className="btn btn-secondary" onClick={() => setEditingKey(null)} disabled={savingKey === field.key}>
                         取消
                       </button>
                     </div>
                   </div>
                 ) : (
                   <div style={{ display: 'flex', gap: 8, alignItems: 'flex-start', flexWrap: 'wrap' }}>
                     <div className="field-value" style={{
                       flex: '1 1 420px',
                       padding: 12,
                       background: hasValue ? '#f8fafc' : '#fffbeb',
                       border: `1px solid ${hasValue ? '#e2e8f0' : '#fde68a'}`,
                       borderRadius: 6,
                       minHeight: 60,
                       whiteSpace: 'pre-wrap',
                       fontSize: 13,
                     }}>
                       {hasValue ? formatAIValue(value) : '尚未生成，点击右侧按钮运行 AI 抽取'}
                     </div>
                     <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
                       <button
                         className="btn btn-primary"
                         onClick={() => onProcess(field.key, hasValue || isOverridden)}
                         disabled={isProcessing || !!processing}
                         style={{ flexShrink: 0 }}
                       >
                         {isProcessing ? '处理中' : hasValue ? '重新生成' : '生成'}
                       </button>
                       <button
                         className="btn btn-secondary"
                         onClick={() => startEditing(field.key, value)}
                         disabled={isProcessing || !!processing}
                       >
                         {isOverridden ? '编辑覆盖' : '人工覆盖'}
                       </button>
                       {isOverridden && (
                         <button
                           className="btn btn-secondary"
                           onClick={() => void onClearOverride(field.key)}
                           disabled={isProcessing || !!processing}
                         >
                           清除覆盖
                         </button>
                       )}
                     </div>
                   </div>
                 )}
                 {isOverridden && editingKey !== field.key && (
                   <div style={{ fontSize: 12, color: '#64748b', marginTop: 8 }}>
                     <span style={{ color: '#b45309', fontWeight: 600, marginRight: 6 }}>人工覆盖</span>
                     AI 原值：{formatAIValue(generatedValue) || '暂无'}
                   </div>
                 )}
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
  updateField: (key: keyof PatentEditData, value: unknown) => void
}) {
  const customData = patent.custom_fields || {}
  const keys = Object.keys(customData)

  return (
    <div>
      {keys.length === 0 ? (
        <div className="empty-state">
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
                  value={String(customData[key] ?? '')}
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
function RelationsTab({ patent, formData, tags, projects, editing, updateField }: {
  patent: Patent
  formData: PatentEditData
  tags: Tag[]
  projects: Project[]
  editing: boolean
  updateField: (key: keyof PatentEditData, value: unknown) => void
}) {
  const patentTags = patent.tags || []
  const patentProjects = patent.projects || []

  // 编辑态下从 patent 现有标签初始化，后续变更通过 updateField 写入 formData
  // 这里直接用 patent 数据作为初始选中态，保存时由父组件的 formData 决定
  const currentTagIds = editing ? (formData.tag_ids ?? patentTags.map(t => t.id)) : patentTags.map(t => t.id)
  const currentProjectIds = editing ? (formData.project_ids ?? patentProjects.map(p => p.id)) : patentProjects.map(p => p.id)

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
                      updateField('tag_ids', next)
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
                      updateField('project_ids', next)
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
                  {proj.name} {proj.module && <span style={{ color: '#94a3b8' }}>· {proj.module}</span>}
                </div>
              ))
            }
          </div>
        )}
      </Field>

      <div style={{ gridColumn: '1 / -1' }}>
        <PatentGraph patentId={patent.id} />
      </div>
    </div>
  )
}

// ============ 修改历史 Tab ============
const SOURCE_LABELS: Record<string, { label: string; color: string; bg: string }> = {
  manual:  { label: '手动', color: '#1e40af', bg: '#dbeafe' },
  bulk:    { label: '批量', color: '#6b21a8', bg: '#f3e8ff' },
  ai:      { label: 'AI', color: '#065f46', bg: '#d1fae5' },
  import:  { label: '导入', color: '#92400e', bg: '#fef3c7' },
  api:     { label: 'API', color: '#475569', bg: '#e2e8f0' },
}

function formatValue(v: string | null | undefined): string {
  if (v === null || v === undefined || v === '') return '（空）'
  // 尝试解析为 JSON
  try {
    const parsed = JSON.parse(v)
    if (typeof parsed === 'object') return JSON.stringify(parsed, null, 2)
    return String(parsed)
  } catch {
    return v
  }
}

function HistoryTab({ patent, history, loading, onReload }: {
  patent: Patent
  history: PatentHistory[]
  loading: boolean
  onReload: () => void
}) {
  const [sourceFilter, setSourceFilter] = useState<string>('all')

  const filtered = sourceFilter === 'all'
    ? history
    : history.filter(h => h.source === sourceFilter)

  // 按日期分组
  const groups: Record<string, PatentHistory[]> = {}
  filtered.forEach(h => {
    const day = h.created_at ? new Date(h.created_at).toLocaleDateString('zh-CN') : '未知日期'
    if (!groups[day]) groups[day] = []
    groups[day].push(h)
  })

  const sourceOptions = ['all', 'manual', 'bulk', 'ai', 'import', 'api']

  return (
    <div>
      {/* 工具条 */}
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 16, flexWrap: 'wrap', gap: 8 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: 13 }}>
          <span style={{ color: '#64748b' }}>来源筛选：</span>
          <select
            className="form-input"
            style={{ width: 'auto', padding: '4px 8px', fontSize: 13 }}
            value={sourceFilter}
            onChange={e => setSourceFilter(e.target.value)}
          >
            {sourceOptions.map(s => (
              <option key={s} value={s}>
                {s === 'all' ? '全部' : (SOURCE_LABELS[s]?.label || s)}
              </option>
            ))}
          </select>
          <span style={{ color: '#94a3b8' }}>·</span>
          <span style={{ color: '#64748b' }}>共 {filtered.length} 条</span>
        </div>
        <button className="btn btn-secondary" onClick={onReload} disabled={loading} style={{ fontSize: 13, padding: '4px 12px' }}>
          {loading ? '刷新中...' : '刷新'}
        </button>
      </div>

      {loading && history.length === 0 ? (
        <div className="loading-spinner">
          <div className="spinner"></div>
          加载中...
        </div>
      ) : filtered.length === 0 ? (
        <div className="empty-state">
          <div className="empty-state-title">暂无修改记录</div>
          <div className="empty-state-desc">
            当此专利的任何字段被修改时（手动编辑、批量更新、AI 处理、导入），修改记录会自动写入此处。
          </div>
          <div style={{ marginTop: 12, fontSize: 12, color: '#94a3b8' }}>
            <div>创建时间：{patent.created_at ? new Date(patent.created_at).toLocaleString('zh-CN') : '-'}</div>
            <div style={{ marginTop: 2 }}>最后修改：{patent.updated_at ? new Date(patent.updated_at).toLocaleString('zh-CN') : '-'}</div>
          </div>
        </div>
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 20 }}>
          {Object.entries(groups).map(([day, items]) => (
            <div key={day}>
              <div style={{
                fontSize: 12, color: '#94a3b8', marginBottom: 8,
                paddingBottom: 4, borderBottom: '1px solid #e2e8f0',
              }}>
                {day} · {items.length} 次修改
              </div>
              <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
                {items.map(h => {
                  const src = SOURCE_LABELS[h.source] || { label: h.source, color: '#475569', bg: '#e2e8f0' }
                  const time = h.created_at ? new Date(h.created_at).toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit', second: '2-digit' }) : ''
                  return (
                    <div key={h.id} style={{
                      display: 'flex', gap: 12, padding: 12,
                      background: '#fff', border: '1px solid #e2e8f0', borderRadius: 8,
                    }}>
                      {/* 时间轴圆点 */}
                      <div style={{
                        width: 8, height: 8, borderRadius: '50%', background: '#3b82f6',
                        marginTop: 6, flexShrink: 0,
                        boxShadow: '0 0 0 3px #dbeafe',
                      }} />
                      {/* 修改详情 */}
                      <div style={{ flex: 1, minWidth: 0 }}>
                        <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 6, flexWrap: 'wrap' }}>
                          <span style={{ fontWeight: 600, color: '#0f172a', fontSize: 13 }}>
                            {h.field_display_name || h.field_key}
                          </span>
                          <span style={{
                            padding: '1px 8px', borderRadius: 10, fontSize: 11,
                            background: src.bg, color: src.color, fontWeight: 500,
                          }}>
                            {src.label}
                          </span>
                          {h.changed_by && (
                            <span style={{ fontSize: 11, color: '#94a3b8' }}>· {h.changed_by}</span>
                          )}
                          <span style={{ fontSize: 11, color: '#94a3b8', marginLeft: 'auto' }}>{time}</span>
                        </div>
                        <div style={{ display: 'flex', gap: 8, alignItems: 'stretch', fontSize: 12, flexWrap: 'wrap' }}>
                          <div style={{
                            flex: 1, minWidth: 120, padding: '6px 10px',
                            background: '#fef2f2', border: '1px solid #fecaca', borderRadius: 6,
                            color: '#7f1d1d',
                          }}>
                            <div style={{ fontSize: 10, color: '#dc2626', marginBottom: 2 }}>旧值</div>
                            <div style={{ whiteSpace: 'pre-wrap', wordBreak: 'break-word' }}>
                              {formatValue(h.old_value)}
                            </div>
                          </div>
                          <div style={{ display: 'flex', alignItems: 'center', color: '#94a3b8', fontSize: 16 }}>
                            →
                          </div>
                          <div style={{
                            flex: 1, minWidth: 120, padding: '6px 10px',
                            background: '#f0fdf4', border: '1px solid #bbf7d0', borderRadius: 6,
                            color: '#065f46',
                          }}>
                            <div style={{ fontSize: 10, color: '#16a34a', marginBottom: 2 }}>新值</div>
                            <div style={{ whiteSpace: 'pre-wrap', wordBreak: 'break-word' }}>
                              {formatValue(h.new_value)}
                            </div>
                          </div>
                        </div>
                      </div>
                    </div>
                  )
                })}
              </div>
            </div>
          ))}
        </div>
      )}
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
