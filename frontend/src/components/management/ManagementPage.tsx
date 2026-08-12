import { useCallback, useEffect, useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  customFieldApi,
  departmentApi,
  personApi,
  productApi,
  productLineApi,
  projectApi,
  tagApi,
  tagGroupApi,
} from '../../api'
import type {
  CustomField,
  Department,
  Person,
  Product,
  ProductLine,
  Project,
  Tag,
  TagGroup,
} from '../../types'
import { getErrorMessage } from '../../lib/errors'

type ManagementTab = 'products' | 'projects' | 'tags' | 'organization' | 'product-lines'

const tabs: Array<{ key: ManagementTab; label: string }> = [
  { key: 'products', label: '产品' },
  { key: 'projects', label: '项目' },
  { key: 'tags', label: '标签' },
  { key: 'organization', label: '部门与人员' },
  { key: 'product-lines', label: '产品线' },
]

const inputStyle = { width: '100%', boxSizing: 'border-box' as const }
const fieldLabelStyle = { display: 'block', fontSize: 12, color: '#475569', marginBottom: 4 }

function FormField({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <label style={{ display: 'block' }}>
      <span style={fieldLabelStyle}>{label}</span>
      {children}
    </label>
  )
}

function EmptyState({ text }: { text: string }) {
  return <div style={{ padding: 48, textAlign: 'center', color: '#94a3b8' }}>{text}</div>
}

function TableShell({ children }: { children: React.ReactNode }) {
  return (
    <div className="management-table" style={{ overflowX: 'auto', background: '#fff', border: '1px solid #e2e8f0', borderRadius: 8 }}>
      <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 12 }}>
        {children}
      </table>
    </div>
  )
}

function TableHead({ children }: { children: React.ReactNode }) {
  return <thead><tr style={{ background: '#f8fafc', borderBottom: '1px solid #e2e8f0' }}>{children}</tr></thead>
}

function Th({ children }: { children: React.ReactNode }) {
  return <th style={{ padding: '10px 12px', textAlign: 'left', fontWeight: 600, color: '#475569', whiteSpace: 'nowrap' }}>{children}</th>
}

function Td({ children, muted = false }: { children: React.ReactNode; muted?: boolean }) {
  return <td style={{ padding: '10px 12px', borderTop: '1px solid #f1f5f9', color: muted ? '#94a3b8' : '#334155', verticalAlign: 'top' }}>{children}</td>
}

function RowActions({ onEdit, onDelete }: { onEdit: () => void; onDelete: () => void }) {
  return (
    <div style={{ display: 'flex', gap: 6, whiteSpace: 'nowrap' }}>
      <button className="btn btn-secondary" style={{ padding: '4px 8px', fontSize: 11 }} onClick={onEdit}>编辑</button>
      <button className="btn btn-danger" style={{ padding: '4px 8px', fontSize: 11 }} onClick={onDelete}>删除</button>
    </div>
  )
}

function ManagementHeader({
  title,
  description,
  onCreate,
  createLabel = '新增',
}: {
  title: string
  description: string
  onCreate: () => void
  createLabel?: string
}) {
  return (
    <div className="page-header" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: 16 }}>
      <div>
        <h2 className="page-title">{title}</h2>
        <p className="page-subtitle">{description}</p>
      </div>
      <button className="btn btn-primary" onClick={onCreate}>{createLabel}</button>
    </div>
  )
}

interface ProductForm {
  name: string
  code: string
  product_line_id: string
  owner_id: string
  category: string
  description: string
  is_active: boolean
}

interface ProjectForm {
  name: string
  code: string
  product_id: string
  module: string
  status: string
  start_date: string
  end_date: string
  description: string
}

interface TagForm {
  name: string
  group_id: string
  color: string
  description: string
}

interface TagGroupForm {
  name: string
  color: string
  description: string
}

interface DepartmentForm {
  name: string
  code: string
  department_type: string
  parent_id: string
  description: string
}

interface PersonForm {
  name: string
  email: string
  department_id: string
  role: string
  notes: string
  is_active: boolean
}

interface ProductLineForm {
  name: string
  code: string
  department_id?: string
  description: string
}

const emptyProduct: ProductForm = { name: '', code: '', product_line_id: '', owner_id: '', category: '', description: '', is_active: true }
const emptyProject: ProjectForm = { name: '', code: '', product_id: '', module: '', status: 'active', start_date: '', end_date: '', description: '' }
const emptyTag: TagForm = { name: '', group_id: '', color: '#3b82f6', description: '' }
const emptyTagGroup: TagGroupForm = { name: '', color: '#64748b', description: '' }
const emptyDepartment: DepartmentForm = { name: '', code: '', department_type: 'other', parent_id: '', description: '' }
const emptyPerson: PersonForm = { name: '', email: '', department_id: '', role: '', notes: '', is_active: true }
const emptyProductLine: ProductLineForm = { name: '', code: '', department_id: '', description: '' }

function optionalNumber(value: string): number | undefined {
  return value ? Number(value) : undefined
}

export default function ManagementPage() {
  const navigate = useNavigate()
  const [tab, setTab] = useState<ManagementTab>('products')
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')
  const [products, setProducts] = useState<Product[]>([])
  const [projects, setProjects] = useState<Project[]>([])
  const [tags, setTags] = useState<Tag[]>([])
  const [tagGroups, setTagGroups] = useState<TagGroup[]>([])
  const [departments, setDepartments] = useState<Department[]>([])
  const [people, setPeople] = useState<Person[]>([])
  const [productLines, setProductLines] = useState<ProductLine[]>([])
  const [customFields, setCustomFields] = useState<CustomField[]>([])

  const [editingProductId, setEditingProductId] = useState<number | null>(null)
  const [productForm, setProductForm] = useState<ProductForm>(emptyProduct)
  const [editingProjectId, setEditingProjectId] = useState<number | null>(null)
  const [projectForm, setProjectForm] = useState<ProjectForm>(emptyProject)
  const [editingTagId, setEditingTagId] = useState<number | null>(null)
  const [tagForm, setTagForm] = useState<TagForm>(emptyTag)
  const [editingTagGroupId, setEditingTagGroupId] = useState<number | null>(null)
  const [tagGroupForm, setTagGroupForm] = useState<TagGroupForm>(emptyTagGroup)
  const [editingDepartmentId, setEditingDepartmentId] = useState<number | null>(null)
  const [departmentForm, setDepartmentForm] = useState<DepartmentForm>(emptyDepartment)
  const [editingPersonId, setEditingPersonId] = useState<number | null>(null)
  const [personForm, setPersonForm] = useState<PersonForm>(emptyPerson)
  const [editingProductLineId, setEditingProductLineId] = useState<number | null>(null)
  const [productLineForm, setProductLineForm] = useState<ProductLineForm>(emptyProductLine)
  const [showProductForm, setShowProductForm] = useState(false)
  const [showProjectForm, setShowProjectForm] = useState(false)
  const [showTagForm, setShowTagForm] = useState(false)
  const [showTagGroupForm, setShowTagGroupForm] = useState(false)
  const [showDepartmentForm, setShowDepartmentForm] = useState(false)
  const [showPersonForm, setShowPersonForm] = useState(false)
  const [showProductLineForm, setShowProductLineForm] = useState(false)

  const loadData = useCallback(async () => {
    setLoading(true)
    setError('')
    try {
      const [loadedProducts, loadedProjects, loadedTags, loadedGroups, loadedDepartments, loadedPeople, loadedLines, loadedFields] = await Promise.all([
        productApi.list(), projectApi.list(), tagApi.list(), tagGroupApi.list(),
        departmentApi.list(), personApi.list(), productLineApi.list(), customFieldApi.list(),
      ])
      setProducts(loadedProducts)
      setProjects(loadedProjects)
      setTags(loadedTags)
      setTagGroups(loadedGroups)
      setDepartments(loadedDepartments)
      setPeople(loadedPeople)
      setProductLines(loadedLines)
      setCustomFields(loadedFields)
    } catch (loadError: unknown) {
      setError(getErrorMessage(loadError, '管理数据加载失败'))
    } finally {
      setLoading(false)
    }
  }, [])

  // Loading remote metadata is the external synchronization this effect owns.
  // eslint-disable-next-line react-hooks/set-state-in-effect
  useEffect(() => { void loadData() }, [loadData])

  const groupNameById = useMemo(() => new Map(tagGroups.map(group => [group.id, group.name])), [tagGroups])
  const departmentNameById = useMemo(() => new Map(departments.map(department => [department.id, department.name])), [departments])
  const productLineNameById = useMemo(() => new Map(productLines.map(line => [line.id, line.name])), [productLines])
  const productNameById = useMemo(() => new Map(products.map(product => [product.id, product.name])), [products])
  const personNameById = useMemo(() => new Map(people.map(person => [person.id, person.name])), [people])

  const beginCreate = () => {
    setError('')
    setEditingProductId(null); setProductForm(emptyProduct)
    setEditingProjectId(null); setProjectForm(emptyProject)
    setEditingTagId(null); setTagForm(emptyTag)
    setEditingTagGroupId(null); setTagGroupForm(emptyTagGroup)
    setEditingDepartmentId(null); setDepartmentForm(emptyDepartment)
    setEditingPersonId(null); setPersonForm(emptyPerson)
    setEditingProductLineId(null); setProductLineForm(emptyProductLine)
    setShowProductForm(false); setShowProjectForm(false); setShowTagForm(false)
    setShowTagGroupForm(false); setShowDepartmentForm(false); setShowPersonForm(false)
    setShowProductLineForm(false)
  }

  const fail = (actionError: unknown) => setError(getErrorMessage(actionError, '保存失败'))

  const saveProduct = async () => {
    if (!productForm.name.trim()) { setError('产品名称不能为空'); return }
    setSaving(true); setError('')
    try {
      const payload = {
        name: productForm.name.trim(), code: productForm.code.trim() || undefined,
        product_line_id: optionalNumber(productForm.product_line_id), owner_id: optionalNumber(productForm.owner_id),
        category: productForm.category.trim() || undefined, description: productForm.description.trim() || undefined,
        is_active: productForm.is_active,
      }
      const result = editingProductId ? await productApi.update(editingProductId, payload) : await productApi.create(payload)
      setProducts(current => editingProductId ? current.map(item => item.id === result.id ? result : item) : [...current, result])
      setEditingProductId(null); setProductForm(emptyProduct); setShowProductForm(false)
    } catch (actionError: unknown) { fail(actionError) } finally { setSaving(false) }
  }

  const saveProject = async () => {
    if (!projectForm.name.trim()) { setError('项目名称不能为空'); return }
    setSaving(true); setError('')
    try {
      const payload = {
        name: projectForm.name.trim(), code: projectForm.code.trim() || undefined,
        product_id: optionalNumber(projectForm.product_id), module: projectForm.module.trim() || undefined,
        status: projectForm.status, start_date: projectForm.start_date || undefined,
        end_date: projectForm.end_date || undefined, description: projectForm.description.trim() || undefined,
      }
      const result = editingProjectId ? await projectApi.update(editingProjectId, payload) : await projectApi.create(payload)
      setProjects(current => editingProjectId ? current.map(item => item.id === result.id ? result : item) : [...current, result])
      setEditingProjectId(null); setProjectForm(emptyProject); setShowProjectForm(false)
    } catch (actionError: unknown) { fail(actionError) } finally { setSaving(false) }
  }

  const saveTag = async () => {
    if (!tagForm.name.trim()) { setError('标签名称不能为空'); return }
    setSaving(true); setError('')
    try {
      const payload = { name: tagForm.name.trim(), group_id: optionalNumber(tagForm.group_id), color: tagForm.color || undefined, description: tagForm.description.trim() || undefined }
      const result = editingTagId ? await tagApi.update(editingTagId, payload) : await tagApi.create(payload)
      setTags(current => editingTagId ? current.map(item => item.id === result.id ? result : item) : [...current, result])
      setEditingTagId(null); setTagForm(emptyTag); setShowTagForm(false)
    } catch (actionError: unknown) { fail(actionError) } finally { setSaving(false) }
  }

  const saveTagGroup = async () => {
    if (!tagGroupForm.name.trim()) { setError('标签组名称不能为空'); return }
    setSaving(true); setError('')
    try {
      const payload = { name: tagGroupForm.name.trim(), color: tagGroupForm.color || undefined, description: tagGroupForm.description.trim() || undefined }
      const result = editingTagGroupId ? await tagGroupApi.update(editingTagGroupId, payload) : await tagGroupApi.create(payload)
      setTagGroups(current => editingTagGroupId ? current.map(item => item.id === result.id ? result : item) : [...current, result])
      setEditingTagGroupId(null); setTagGroupForm(emptyTagGroup); setShowTagGroupForm(false)
    } catch (actionError: unknown) { fail(actionError) } finally { setSaving(false) }
  }

  const saveDepartment = async () => {
    if (!departmentForm.name.trim()) { setError('部门名称不能为空'); return }
    setSaving(true); setError('')
    try {
      const payload = { name: departmentForm.name.trim(), code: departmentForm.code.trim() || undefined, department_type: departmentForm.department_type, parent_id: optionalNumber(departmentForm.parent_id), description: departmentForm.description.trim() || undefined }
      const result = editingDepartmentId ? await departmentApi.update(editingDepartmentId, payload) : await departmentApi.create(payload)
      setDepartments(current => editingDepartmentId ? current.map(item => item.id === result.id ? result : item) : [...current, result])
      setEditingDepartmentId(null); setDepartmentForm(emptyDepartment); setShowDepartmentForm(false)
    } catch (actionError: unknown) { fail(actionError) } finally { setSaving(false) }
  }

  const savePerson = async () => {
    if (!personForm.name.trim()) { setError('人员姓名不能为空'); return }
    setSaving(true); setError('')
    try {
      const payload = {
        name: personForm.name.trim(), email: personForm.email.trim() || undefined,
        department_id: optionalNumber(personForm.department_id), role: personForm.role.trim() || undefined,
        notes: personForm.notes.trim() || undefined, is_active: personForm.is_active,
      }
      const result = editingPersonId ? await personApi.update(editingPersonId, payload) : await personApi.create(payload)
      setPeople(current => editingPersonId ? current.map(item => item.id === result.id ? result : item) : [...current, result])
      setEditingPersonId(null); setPersonForm(emptyPerson); setShowPersonForm(false)
    } catch (actionError: unknown) { fail(actionError) } finally { setSaving(false) }
  }

  const saveProductLine = async () => {
    if (!productLineForm.name.trim()) { setError('产品线名称不能为空'); return }
    setSaving(true); setError('')
    try {
      const payload = { name: productLineForm.name.trim(), code: productLineForm.code.trim() || undefined, department_id: optionalNumber(productLineForm.department_id || ''), description: productLineForm.description.trim() || undefined }
      const result = editingProductLineId ? await productLineApi.update(editingProductLineId, payload) : await productLineApi.create(payload)
      setProductLines(current => editingProductLineId ? current.map(item => item.id === result.id ? result : item) : [...current, result])
      setEditingProductLineId(null); setProductLineForm(emptyProductLine); setShowProductLineForm(false)
    } catch (actionError: unknown) { fail(actionError) } finally { setSaving(false) }
  }

  const remove = async (label: string, action: () => Promise<unknown>, onSuccess: () => void) => {
    if (!confirm(`确定删除${label}吗？`)) return
    setError(''); setSaving(true)
    try { await action(); onSuccess() } catch (actionError: unknown) { fail(actionError) } finally { setSaving(false) }
  }

  const renderProducts = () => (
    <>
      <ManagementHeader title="产品管理" description="维护产品、产品线和负责人，供专利库与项目关联使用。" onCreate={() => { beginCreate(); setShowProductForm(true) }} createLabel="新增产品" />
      {(showProductForm || editingProductId !== null) && (
        <div className="management-form">
          <div className="management-form-grid">
            <FormField label="产品名称"><input className="form-input" style={inputStyle} value={productForm.name} onChange={e => setProductForm({ ...productForm, name: e.target.value })} /></FormField>
            <FormField label="产品编码"><input className="form-input" style={inputStyle} value={productForm.code} onChange={e => setProductForm({ ...productForm, code: e.target.value })} /></FormField>
            <FormField label="产品线"><select className="form-input" style={inputStyle} value={productForm.product_line_id} onChange={e => setProductForm({ ...productForm, product_line_id: e.target.value })}><option value="">未关联</option>{productLines.map(line => <option key={line.id} value={line.id}>{line.name}</option>)}</select></FormField>
            <FormField label="负责人"><select className="form-input" style={inputStyle} value={productForm.owner_id} onChange={e => setProductForm({ ...productForm, owner_id: e.target.value })}><option value="">未指定</option>{people.map(person => <option key={person.id} value={person.id}>{person.name}</option>)}</select></FormField>
            <FormField label="分类"><input className="form-input" style={inputStyle} value={productForm.category} onChange={e => setProductForm({ ...productForm, category: e.target.value })} /></FormField>
            <label style={{ display: 'flex', alignItems: 'center', gap: 8, paddingTop: 20, color: '#475569', fontSize: 12 }}><input type="checkbox" checked={productForm.is_active} onChange={e => setProductForm({ ...productForm, is_active: e.target.checked })} />启用</label>
          </div>
          <FormField label="描述"><textarea className="form-input" style={{ ...inputStyle, minHeight: 64 }} value={productForm.description} onChange={e => setProductForm({ ...productForm, description: e.target.value })} /></FormField>
          <div className="management-form-actions"><button className="btn btn-primary" disabled={saving} onClick={() => void saveProduct()}>{saving ? '保存中...' : editingProductId ? '保存修改' : '创建产品'}</button><button className="btn btn-secondary" onClick={() => { setEditingProductId(null); setProductForm(emptyProduct); setShowProductForm(false) }}>取消</button></div>
        </div>
      )}
      <TableShell><TableHead><Th>产品</Th><Th>编码</Th><Th>产品线</Th><Th>负责人</Th><Th>专利数</Th><Th>状态</Th><Th>操作</Th></TableHead><tbody>{products.map(product => <tr key={product.id}><Td><strong>{product.name}</strong>{product.category && <div style={{ color: '#94a3b8', marginTop: 3 }}>{product.category}</div>}</Td><Td muted>{product.code || '-'}</Td><Td>{productLineNameById.get(product.product_line_id ?? 0) || '-'}</Td><Td>{personNameById.get(product.owner_id ?? 0) || '-'}</Td><Td>{product.patent_count ?? 0}</Td><Td>{product.is_active === false ? '已停用' : '启用'}</Td><Td><RowActions onEdit={() => { setEditingProductId(product.id); setProductForm({ name: product.name, code: product.code || '', product_line_id: product.product_line_id ? String(product.product_line_id) : '', owner_id: product.owner_id ? String(product.owner_id) : '', category: product.category || '', description: product.description || '', is_active: product.is_active !== false }) }} onDelete={() => void remove(`产品“${product.name}”`, () => productApi.delete(product.id), () => setProducts(current => current.filter(item => item.id !== product.id)))} /></Td></tr>)}</tbody></TableShell>
      {products.length === 0 && <EmptyState text="暂无产品" />}
    </>
  )

  const renderProjects = () => (
    <>
      <ManagementHeader title="项目管理" description="维护项目周期和归属产品，导入专利时可直接关联项目。" onCreate={() => { beginCreate(); setShowProjectForm(true) }} createLabel="新增项目" />
      {(showProjectForm || editingProjectId !== null) && <div className="management-form"><div className="management-form-grid"><FormField label="项目名称"><input className="form-input" style={inputStyle} value={projectForm.name} onChange={e => setProjectForm({ ...projectForm, name: e.target.value })} /></FormField><FormField label="项目编码"><input className="form-input" style={inputStyle} value={projectForm.code} onChange={e => setProjectForm({ ...projectForm, code: e.target.value })} /></FormField><FormField label="所属产品"><select className="form-input" style={inputStyle} value={projectForm.product_id} onChange={e => setProjectForm({ ...projectForm, product_id: e.target.value })}><option value="">未关联</option>{products.map(product => <option key={product.id} value={product.id}>{product.name}</option>)}</select></FormField><FormField label="状态"><select className="form-input" style={inputStyle} value={projectForm.status} onChange={e => setProjectForm({ ...projectForm, status: e.target.value })}><option value="active">进行中</option><option value="planned">计划中</option><option value="completed">已完成</option><option value="archived">已归档</option></select></FormField><FormField label="开始日期"><input className="form-input" style={inputStyle} type="date" value={projectForm.start_date} onChange={e => setProjectForm({ ...projectForm, start_date: e.target.value })} /></FormField><FormField label="结束日期"><input className="form-input" style={inputStyle} type="date" value={projectForm.end_date} onChange={e => setProjectForm({ ...projectForm, end_date: e.target.value })} /></FormField></div><FormField label="功能模块"><input className="form-input" style={inputStyle} value={projectForm.module} onChange={e => setProjectForm({ ...projectForm, module: e.target.value })} /></FormField><div style={{ marginTop: 12 }}><FormField label="描述"><textarea className="form-input" style={{ ...inputStyle, minHeight: 64 }} value={projectForm.description} onChange={e => setProjectForm({ ...projectForm, description: e.target.value })} /></FormField></div><div className="management-form-actions"><button className="btn btn-primary" disabled={saving} onClick={() => void saveProject()}>{saving ? '保存中...' : editingProjectId ? '保存修改' : '创建项目'}</button><button className="btn btn-secondary" onClick={() => { setEditingProjectId(null); setProjectForm(emptyProject); setShowProjectForm(false) }}>取消</button></div></div>}
      <TableShell><TableHead><Th>项目</Th><Th>产品</Th><Th>状态</Th><Th>周期</Th><Th>专利数</Th><Th>操作</Th></TableHead><tbody>{projects.map(project => <tr key={project.id}><Td><strong>{project.name}</strong>{project.code && <div style={{ color: '#94a3b8', marginTop: 3 }}>{project.code}</div>}</Td><Td>{productNameById.get(project.product_id ?? 0) || '-'}</Td><Td>{project.status || 'active'}</Td><Td muted>{project.start_date || '-'} 至 {project.end_date || '-'}</Td><Td>{project.patent_count ?? 0}</Td><Td><RowActions onEdit={() => { setEditingProjectId(project.id); setProjectForm({ name: project.name, code: project.code || '', product_id: project.product_id ? String(project.product_id) : '', module: project.module || '', status: project.status || 'active', start_date: project.start_date || '', end_date: project.end_date || '', description: project.description || '' }) }} onDelete={() => void remove(`项目“${project.name}”`, () => projectApi.delete(project.id), () => setProjects(current => current.filter(item => item.id !== project.id)))} /></Td></tr>)}</tbody></TableShell>{projects.length === 0 && <EmptyState text="暂无项目" />}
    </>
  )

  const renderTags = () => (
    <>
      <ManagementHeader title="标签与标签组" description="用标签沉淀业务分类，并通过标签组保持筛选和分析口径一致。" onCreate={() => { beginCreate(); setShowTagForm(true) }} createLabel="新增标签" />
      <div className="management-split">
        <section><div className="management-section-title"><strong>标签</strong><button className="btn btn-secondary" onClick={() => { beginCreate(); setShowTagForm(true) }}>新增标签</button></div>{(showTagForm || editingTagId !== null) && <div className="management-form compact"><div className="management-form-grid"><FormField label="名称"><input className="form-input" style={inputStyle} value={tagForm.name} onChange={e => setTagForm({ ...tagForm, name: e.target.value })} /></FormField><FormField label="标签组"><select className="form-input" style={inputStyle} value={tagForm.group_id} onChange={e => setTagForm({ ...tagForm, group_id: e.target.value })}><option value="">未分组</option>{tagGroups.map(group => <option key={group.id} value={group.id}>{group.name}</option>)}</select></FormField><FormField label="颜色"><input className="form-input" style={inputStyle} type="color" value={tagForm.color} onChange={e => setTagForm({ ...tagForm, color: e.target.value })} /></FormField></div><div className="management-form-actions"><button className="btn btn-primary" disabled={saving} onClick={() => void saveTag()}>{editingTagId ? '保存修改' : '创建标签'}</button><button className="btn btn-secondary" onClick={() => { setEditingTagId(null); setTagForm(emptyTag); setShowTagForm(false) }}>取消</button></div></div>}<TableShell><TableHead><Th>名称</Th><Th>分组</Th><Th>颜色</Th><Th>操作</Th></TableHead><tbody>{tags.map(tag => <tr key={tag.id}><Td><strong>{tag.name}</strong></Td><Td>{groupNameById.get(tag.group_id ?? 0) || '-'}</Td><Td><span style={{ display: 'inline-block', width: 14, height: 14, borderRadius: 3, background: tag.color || '#94a3b8', verticalAlign: 'middle' }} /></Td><Td><RowActions onEdit={() => { setEditingTagId(tag.id); setTagForm({ name: tag.name, group_id: tag.group_id ? String(tag.group_id) : '', color: tag.color || '#3b82f6', description: tag.description || '' }) }} onDelete={() => void remove(`标签“${tag.name}”`, () => tagApi.delete(tag.id), () => setTags(current => current.filter(item => item.id !== tag.id)))} /></Td></tr>)}</tbody></TableShell>{tags.length === 0 && <EmptyState text="暂无标签" />}</section>
        <section><div className="management-section-title"><strong>标签组</strong><button className="btn btn-secondary" onClick={() => { beginCreate(); setShowTagGroupForm(true) }}>新增标签组</button></div>{(showTagGroupForm || editingTagGroupId !== null) && <div className="management-form compact"><div className="management-form-grid"><FormField label="名称"><input className="form-input" style={inputStyle} value={tagGroupForm.name} onChange={e => setTagGroupForm({ ...tagGroupForm, name: e.target.value })} /></FormField><FormField label="颜色"><input className="form-input" style={inputStyle} type="color" value={tagGroupForm.color} onChange={e => setTagGroupForm({ ...tagGroupForm, color: e.target.value })} /></FormField></div><div className="management-form-actions"><button className="btn btn-primary" disabled={saving} onClick={() => void saveTagGroup()}>{editingTagGroupId ? '保存修改' : '创建标签组'}</button><button className="btn btn-secondary" onClick={() => { setEditingTagGroupId(null); setTagGroupForm(emptyTagGroup); setShowTagGroupForm(false) }}>取消</button></div></div>}<TableShell><TableHead><Th>名称</Th><Th>标签数</Th><Th>操作</Th></TableHead><tbody>{tagGroups.map(group => <tr key={group.id}><Td><strong>{group.name}</strong></Td><Td>{group.tags?.length ?? tags.filter(tag => tag.group_id === group.id).length}</Td><Td><RowActions onEdit={() => { setEditingTagGroupId(group.id); setTagGroupForm({ name: group.name, color: group.color || '#64748b', description: group.description || '' }) }} onDelete={() => void remove(`标签组“${group.name}”`, () => tagGroupApi.delete(group.id), () => { setTagGroups(current => current.filter(item => item.id !== group.id)); setTags(current => current.map(tag => tag.group_id === group.id ? { ...tag, group_id: undefined } : tag)) })} /></Td></tr>)}</tbody></TableShell>{tagGroups.length === 0 && <EmptyState text="暂无标签组" />}</section>
      </div>
    </>
  )

  const renderOrganization = () => (
    <>
      <ManagementHeader title="部门与人员" description="维护组织结构和人员归属，为负责人、权限和协作能力提供统一主体。" onCreate={() => { beginCreate(); setShowPersonForm(true) }} createLabel="新增人员" />
      <div className="management-split">
        <section><div className="management-section-title"><strong>部门 / 小组</strong><button className="btn btn-secondary" onClick={() => { beginCreate(); setShowDepartmentForm(true) }}>新增部门或小组</button></div>{(showDepartmentForm || editingDepartmentId !== null) && <div className="management-form compact"><div className="management-form-grid"><FormField label="名称"><input className="form-input" style={inputStyle} value={departmentForm.name} onChange={e => setDepartmentForm({ ...departmentForm, name: e.target.value })} /></FormField><FormField label="编码"><input className="form-input" style={inputStyle} value={departmentForm.code} onChange={e => setDepartmentForm({ ...departmentForm, code: e.target.value })} /></FormField><FormField label="类型"><select className="form-input" style={inputStyle} value={departmentForm.department_type} onChange={e => setDepartmentForm({ ...departmentForm, department_type: e.target.value })}><option value="patent">专利部门</option><option value="r_and_d">研发部门</option><option value="other">其他</option></select></FormField><FormField label="上级部门"><select className="form-input" style={inputStyle} value={departmentForm.parent_id} onChange={e => setDepartmentForm({ ...departmentForm, parent_id: e.target.value })}><option value="">顶层部门</option>{departments.filter(d => d.id !== editingDepartmentId && !d.parent_id).map(d => <option key={d.id} value={d.id}>{d.name}</option>)}</select></FormField></div><div style={{ marginTop: 12 }}><FormField label="描述"><textarea className="form-input" style={{ ...inputStyle, minHeight: 60 }} value={departmentForm.description} onChange={e => setDepartmentForm({ ...departmentForm, description: e.target.value })} /></FormField></div><div className="management-form-actions"><button className="btn btn-primary" disabled={saving} onClick={() => void saveDepartment()}>{editingDepartmentId ? '保存修改' : '创建'}</button><button className="btn btn-secondary" onClick={() => { setEditingDepartmentId(null); setDepartmentForm(emptyDepartment); setShowDepartmentForm(false) }}>取消</button></div></div>}<TableShell><TableHead><Th>部门 / 小组</Th><Th>类型</Th><Th>人员</Th><Th>操作</Th></TableHead><tbody>{departments.map(department => <tr key={department.id}><Td><strong>{department.parent_id ? '└ ' : ''}{department.name}</strong></Td><Td>{department.parent_id ? '小组' : department.department_type === 'r_and_d' ? '研发部门' : department.department_type === 'patent' ? '专利部门' : '其他'}</Td><Td>{people.filter(person => person.department_id === department.id).length}</Td><Td><RowActions onEdit={() => { setEditingDepartmentId(department.id); setDepartmentForm({ name: department.name, code: department.code || '', department_type: department.department_type || 'other', parent_id: department.parent_id ? String(department.parent_id) : '', description: department.description || '' }) }} onDelete={() => void remove(`部门“${department.name}”`, () => departmentApi.delete(department.id), () => setDepartments(current => current.filter(item => item.id !== department.id)))} /></Td></tr>)}</tbody></TableShell>{departments.length === 0 && <EmptyState text="暂无部门" />}</section>
        <section><div className="management-section-title"><strong>人员</strong><button className="btn btn-secondary" onClick={() => { beginCreate(); setShowPersonForm(true) }}>新增人员</button></div>{(showPersonForm || editingPersonId !== null) && <div className="management-form compact"><div className="management-form-grid"><FormField label="姓名"><input className="form-input" style={inputStyle} value={personForm.name} onChange={e => setPersonForm({ ...personForm, name: e.target.value })} /></FormField><FormField label="邮箱"><input className="form-input" style={inputStyle} type="email" value={personForm.email} onChange={e => setPersonForm({ ...personForm, email: e.target.value })} /></FormField><FormField label="部门"><select className="form-input" style={inputStyle} value={personForm.department_id} onChange={e => setPersonForm({ ...personForm, department_id: e.target.value })}><option value="">未分配</option>{departments.map(department => <option key={department.id} value={department.id}>{department.name}</option>)}</select></FormField><FormField label="角色"><input className="form-input" style={inputStyle} value={personForm.role} onChange={e => setPersonForm({ ...personForm, role: e.target.value })} /></FormField></div><label style={{ display: 'flex', alignItems: 'center', gap: 8, marginTop: 12, color: '#475569', fontSize: 12 }}><input type="checkbox" checked={personForm.is_active} onChange={e => setPersonForm({ ...personForm, is_active: e.target.checked })} />启用</label><div className="management-form-actions"><button className="btn btn-primary" disabled={saving} onClick={() => void savePerson()}>{editingPersonId ? '保存修改' : '创建人员'}</button><button className="btn btn-secondary" onClick={() => { setEditingPersonId(null); setPersonForm(emptyPerson); setShowPersonForm(false) }}>取消</button></div></div>}<TableShell><TableHead><Th>姓名</Th><Th>部门</Th><Th>角色</Th><Th>状态</Th><Th>操作</Th></TableHead><tbody>{people.map(person => <tr key={person.id}><Td><strong>{person.name}</strong>{person.email && <div style={{ color: '#94a3b8', marginTop: 3 }}>{person.email}</div>}</Td><Td>{departmentNameById.get(person.department_id ?? 0) || '-'}</Td><Td>{person.role || '-'}</Td><Td>{person.is_active === false ? '已停用' : '启用'}</Td><Td><RowActions onEdit={() => { setEditingPersonId(person.id); setPersonForm({ name: person.name, email: person.email || '', department_id: person.department_id ? String(person.department_id) : '', role: person.role || '', notes: person.notes || '', is_active: person.is_active !== false }) }} onDelete={() => void remove(`人员“${person.name}”`, () => personApi.delete(person.id), () => setPeople(current => current.filter(item => item.id !== person.id)))} /></Td></tr>)}</tbody></TableShell>{people.length === 0 && <EmptyState text="暂无人员" />}</section>
      </div>
    </>
  )

  const renderProductLines = () => (
    <>
      <ManagementHeader title="产品线管理" description="产品线是产品的上层分类，可用于后续权限、统计和视图筛选。" onCreate={() => { beginCreate(); setShowProductLineForm(true) }} createLabel="新增产品线" />
      {(showProductLineForm || editingProductLineId !== null) && <div className="management-form"><div className="management-form-grid"><FormField label="名称"><input className="form-input" style={inputStyle} value={productLineForm.name} onChange={e => setProductLineForm({ ...productLineForm, name: e.target.value })} /></FormField><FormField label="编码"><input className="form-input" style={inputStyle} value={productLineForm.code} onChange={e => setProductLineForm({ ...productLineForm, code: e.target.value })} /></FormField></div><div style={{ marginTop: 12 }}><FormField label="描述"><textarea className="form-input" style={{ ...inputStyle, minHeight: 64 }} value={productLineForm.description} onChange={e => setProductLineForm({ ...productLineForm, description: e.target.value })} /></FormField></div><div className="management-form-actions"><button className="btn btn-primary" disabled={saving} onClick={() => void saveProductLine()}>{editingProductLineId ? '保存修改' : '创建产品线'}</button><button className="btn btn-secondary" onClick={() => { setEditingProductLineId(null); setProductLineForm(emptyProductLine); setShowProductLineForm(false) }}>取消</button></div></div>}
      <TableShell><TableHead><Th>产品线</Th><Th>编码</Th><Th>关联产品</Th><Th>操作</Th></TableHead><tbody>{productLines.map(line => <tr key={line.id}><Td><strong>{line.name}</strong>{line.description && <div style={{ color: '#94a3b8', marginTop: 3 }}>{line.description}</div>}</Td><Td muted>{line.code || '-'}</Td><Td>{products.filter(product => product.product_line_id === line.id).length}</Td><Td><RowActions onEdit={() => { setEditingProductLineId(line.id); setProductLineForm({ name: line.name, code: line.code || '', description: line.description || '' }) }} onDelete={() => void remove(`产品线“${line.name}”`, () => productLineApi.delete(line.id), () => { setProductLines(current => current.filter(item => item.id !== line.id)); setProducts(current => current.map(product => product.product_line_id === line.id ? { ...product, product_line_id: undefined } : product)) })} /></Td></tr>)}</tbody></TableShell>{productLines.length === 0 && <EmptyState text="暂无产品线" />}
    </>
  )

  if (loading) return <div className="loading-spinner"><div className="spinner" />加载管理数据...</div>

  return (
    <div className="management-page">
      <div className="management-tabs" role="tablist" aria-label="管理资源">
        {tabs.map(item => <button key={item.key} className={`management-tab ${tab === item.key ? 'active' : ''}`} onClick={() => { setTab(item.key); setError('') }}>{item.label}</button>)}
        <button className="management-tab" onClick={() => navigate('/fields')}>自定义字段</button>
      </div>
      {error && <div className="management-error">{error}</div>}
      {tab === 'products' && renderProducts()}
      {tab === 'projects' && renderProjects()}
      {tab === 'tags' && renderTags()}
      {tab === 'organization' && renderOrganization()}
      {tab === 'product-lines' && renderProductLines()}
      {customFields.length > 0 && <div style={{ marginTop: 12, color: '#94a3b8', fontSize: 11 }}>当前已有 {customFields.length} 个自定义字段，字段配置请进入“自定义字段”。</div>}
    </div>
  )
}
