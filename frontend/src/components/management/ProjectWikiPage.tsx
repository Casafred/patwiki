import { useCallback, useEffect, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { attachmentApi, departmentApi, patentApi, projectApi, productApi } from '../../api'
import type { AttachmentMeta, Department, Patent, Project, ProjectHistoryEntry, Product } from '../../types'
import Icon from '../common/Icon'
import { getErrorMessage } from '../../lib/errors'

const fieldLabels: Record<string, string> = {
  name: '项目名称', code: '项目号', product_id: '关联产品记录', product_category: '产品分类',
  department_ids: '所属部门', project_level: '项目等级', project_type: '项目类型', brands: '所涉品牌',
  project_manager: '项目管理', research_owner: '研发', shipping_regions: '出货地区',
  current_stage: '当前项目阶段', product_model: '产品型号', description: '项目描述',
  module: '功能模块', start_date: '开始日期', end_date: '结束日期', status: '状态',
}

function display(value: unknown): string {
  if (Array.isArray(value)) return value.join('、') || '未填写'
  if (value == null || value === '') return '未填写'
  if (value === 'in_progress' || value === 'active') return '进行中'
  if (value === 'paused') return '暂停'
  if (value === 'shipped' || value === 'completed') return '已出货'
  if (value === 'archived') return '暂停'
  if (value === 'planned' || value === 'active') return '进行中'
  if (value === 'pre_research') return '预研'
  return String(value)
}

function fieldValue(project: Project, key: string, departments: Department[], products: Product[]): string {
  if (key === 'department_ids') return departments.filter(item => (project.department_ids || []).includes(item.id)).map(item => item.name).join('、') || '未填写'
  if (key === 'product_id') return products.find(item => item.id === project.product_id)?.name || '未填写'
  if (key === 'status') return display(project.status)
  if (key === 'current_stage') return display(project.current_stage)
  if (key === 'brands') return display(project.brands)
  if (key === 'code') return project.project_no || project.code || '未填写'
  return display((project as unknown as Record<string, unknown>)[key])
}

function historyValue(key: string, value: unknown, departments: Department[], products: Product[]): string {
  if (key === 'department_ids' && Array.isArray(value)) {
    return departments.filter(item => value.map(Number).includes(item.id)).map(item => item.name).join('、') || '未填写'
  }
  if (key === 'product_id' && value != null) {
    return products.find(item => item.id === Number(value))?.name || '未填写'
  }
  return display(value)
}

export default function ProjectWikiPage() {
  const { projectId } = useParams<{ projectId: string }>()
  const navigate = useNavigate()
  const id = Number(projectId)
  const [project, setProject] = useState<Project | null>(null)
  const [history, setHistory] = useState<ProjectHistoryEntry[]>([])
  const [attachments, setAttachments] = useState<AttachmentMeta[]>([])
  const [departments, setDepartments] = useState<Department[]>([])
  const [products, setProducts] = useState<Product[]>([])
  const [patents, setPatents] = useState<Patent[]>([])
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')
  const [scope, setScope] = useState<'project' | 'project_patent'>('project')
  const [patentId, setPatentId] = useState('')
  const [uploadFile, setUploadFile] = useState<File | null>(null)
  const [uploadNote, setUploadNote] = useState('')
  const [editingNoteId, setEditingNoteId] = useState<number | null>(null)
  const [editingNote, setEditingNote] = useState('')

  const load = useCallback(async () => {
    if (!Number.isInteger(id) || id < 1) return
    setLoading(true)
    setError('')
    try {
      const [loadedProject, loadedHistory, loadedAttachments, loadedDepartments, loadedProducts, patentResponse] = await Promise.all([
        projectApi.get(id), projectApi.history(id), attachmentApi.listForProject(id),
        departmentApi.list(), productApi.list(), patentApi.list({ project_id: id, page_size: 100 }),
      ])
      setProject(loadedProject)
      setHistory(loadedHistory)
      setAttachments(loadedAttachments)
      setDepartments(loadedDepartments)
      setProducts(loadedProducts)
      setPatents(patentResponse.items)
    } catch (loadError: unknown) {
      setError(getErrorMessage(loadError, '项目 Wiki 加载失败'))
    } finally {
      setLoading(false)
    }
  }, [id])

  useEffect(() => { void load() }, [load])

  const upload = async () => {
    if (!uploadFile || saving || (scope === 'project_patent' && !patentId)) return
    const body = new FormData()
    body.append('file', uploadFile)
    body.append('scope', scope)
    body.append('note', uploadNote)
    body.append('uploaded_by', 'local-user')
    if (scope === 'project_patent') body.append('patent_id', patentId)
    setSaving(true)
    setError('')
    try {
      await attachmentApi.uploadForProject(id, body)
      setUploadFile(null)
      setUploadNote('')
      await load()
    } catch (uploadError: unknown) {
      setError(getErrorMessage(uploadError, '附件上传失败'))
    } finally {
      setSaving(false)
    }
  }

  const saveNote = async (attachmentId: number) => {
    try {
      await attachmentApi.updateProject(attachmentId, { note: editingNote.trim() || null })
      setEditingNoteId(null)
      await load()
    } catch (updateError: unknown) {
      setError(getErrorMessage(updateError, '备注保存失败'))
    }
  }

  const removeAttachment = async (item: AttachmentMeta) => {
    if (!window.confirm(`删除附件“${item.filename}”？`)) return
    try {
      await attachmentApi.removeProject(item.attachment_id)
      await load()
    } catch (deleteError: unknown) {
      setError(getErrorMessage(deleteError, '附件删除失败'))
    }
  }

  if (loading) return <div className="page-loading">正在加载项目 Wiki…</div>
  if (!project) return <section className="page-section"><div className="page-header"><h2 className="page-title">项目 Wiki</h2><button className="btn btn-secondary" onClick={() => navigate(-1)}><Icon name="chevron-left" size={15} /> 返回</button></div><p>{error || '项目不存在'}</p></section>

  const fields: Array<[string, string | null | undefined]> = [
    ['项目号', project.project_no || project.code], ['项目分类', project.product_category],
    ['所属部门', fieldValue(project, 'department_ids', departments, products)], ['项目等级', project.project_level],
    ['项目类型', project.project_type], ['所涉品牌', (project.brands || []).join('、')],
    ['项目管理', project.project_manager], ['研发', project.research_owner], ['出货地区', project.shipping_regions],
    ['当前项目阶段', display(project.current_stage)], ['产品型号', project.product_model],
    ['状态', display(project.status)], ['关联产品记录', fieldValue(project, 'product_id', departments, products)],
    ['开始日期', project.start_date], ['结束日期', project.end_date],
  ]

  return <div className="project-wiki-page">
    <div className="page-header" style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 12 }}>
      <div><div style={{ color: '#64748b', fontSize: 12, marginBottom: 4 }}>项目 Wiki</div><h2 className="page-title" style={{ margin: 0 }}>{project.name}</h2></div>
      <button type="button" className="btn btn-secondary" onClick={() => navigate(-1)}><Icon name="chevron-left" size={15} /> 返回</button>
    </div>
    {error && <div role="alert" style={{ padding: 10, margin: '12px 0', color: '#991b1b', background: '#fef2f2', border: '1px solid #fecaca', borderRadius: 6 }}>{error}</div>}
    <section className="project-wiki-section">
      <div className="management-section-title"><strong>项目信息</strong><span style={{ color: '#64748b', fontSize: 12 }}>记录由业务管理台维护</span></div>
      <div className="project-wiki-grid">{fields.map(([label, value]) => <div key={label} className="project-wiki-field"><span>{label}</span><strong>{value || '未填写'}</strong></div>)}</div>
      {project.description && <div className="project-wiki-description"><span>项目描述</span><p>{project.description}</p></div>}
    </section>

    <section className="project-wiki-section">
      <div className="management-section-title"><strong>关联专利</strong><span style={{ color: '#64748b', fontSize: 12 }}>{patents.length} 件</span></div>
      {patents.length ? <div className="project-wiki-patents">{patents.map(patent => <button key={patent.id} type="button" onClick={() => navigate(`/patents/${patent.id}`)}><span>{patent.title}</span><small>{patent.application_number || patent.publication_number || `#${patent.id}`}</small></button>)}</div> : <div style={{ color: '#94a3b8', padding: '12px 0' }}>暂无关联专利</div>}
    </section>

    <section className="project-wiki-section">
      <div className="management-section-title"><strong>项目附件</strong><span style={{ color: '#64748b', fontSize: 12 }}>文件统一存放于附件目录</span></div>
      <div className="project-attachment-upload">
        <div className="project-attachment-scope" role="group" aria-label="附件归属">
          <button type="button" className={scope === 'project' ? 'active' : ''} onClick={() => setScope('project')}>项目资料</button>
          <button type="button" className={scope === 'project_patent' ? 'active' : ''} onClick={() => setScope('project_patent')}>项目与专利关系说明</button>
        </div>
        {scope === 'project_patent' && <select className="form-input" value={patentId} onChange={event => setPatentId(event.target.value)}><option value="">选择关联专利</option>{patents.map(patent => <option key={patent.id} value={patent.id}>{patent.application_number || patent.publication_number || patent.title} · {patent.title}</option>)}</select>}
        <input type="file" onChange={event => setUploadFile(event.target.files?.[0] || null)} />
        <input className="form-input" placeholder="附件备注" value={uploadNote} onChange={event => setUploadNote(event.target.value)} />
        <button className="btn btn-primary" disabled={!uploadFile || saving || (scope === 'project_patent' && !patentId)} onClick={() => void upload()}><Icon name="file" size={15} />{saving ? '上传中…' : '上传附件'}</button>
      </div>
      <div className="project-attachment-list">{attachments.map(item => <article key={item.id} className="project-attachment-row">
        <div className="project-attachment-main"><a href={item.download_url} target="_blank" rel="noreferrer">{item.filename}</a><span>{item.scope === 'project_patent' ? `项目/专利关系说明 · ${patents.find(patent => patent.id === item.patent_id)?.title || `专利 #${item.patent_id}`}` : '项目资料'} · {(item.file_size / 1024).toFixed(1)} KB</span>{editingNoteId === item.attachment_id ? <div className="project-attachment-note-edit"><input className="form-input" value={editingNote} onChange={event => setEditingNote(event.target.value)} /><button className="btn btn-secondary" onClick={() => void saveNote(item.attachment_id)}>保存备注</button><button className="btn btn-ghost" onClick={() => setEditingNoteId(null)}>取消</button></div> : <small>{item.note || '无备注'}</small>}</div>
        <div style={{ display: 'flex', gap: 6 }}><button className="btn btn-secondary" onClick={() => { setEditingNoteId(item.attachment_id); setEditingNote(item.note || '') }}>备注</button><button className="btn btn-danger" onClick={() => void removeAttachment(item)}>删除</button></div>
      </article>)}{attachments.length === 0 && <div style={{ color: '#94a3b8', padding: '14px 0' }}>暂无项目附件</div>}</div>
    </section>

    <section className="project-wiki-section">
      <div className="management-section-title"><strong>信息变更记录</strong><span style={{ color: '#64748b', fontSize: 12 }}>{history.length} 条</span></div>
      <div className="project-history-list">{history.map(entry => <article key={entry.id} className="project-history-entry"><div className="project-history-meta"><strong>{entry.action === 'created' ? '创建项目' : '更新项目资料'}</strong><span>{entry.created_at ? new Date(entry.created_at).toLocaleString() : ''} · {entry.changed_by}</span></div><div className="project-history-changes">{Object.entries(entry.changes).map(([key, change]) => <div key={key}><span>{fieldLabels[key] || key}</span><s>{historyValue(key, change.before, departments, products)}</s><b>{historyValue(key, change.after, departments, products)}</b></div>)}</div></article>)}{history.length === 0 && <div style={{ color: '#94a3b8', padding: '14px 0' }}>暂无变更记录</div>}</div>
    </section>
  </div>
}
