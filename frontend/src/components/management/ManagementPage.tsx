import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  departmentApi,
  personApi,
  productApi,
  productLineApi,
  sharingApi,
  projectApi,
  tagApi,
  tagGroupApi,
} from '../../api'
import type {
  Department,
  Person,
  Product,
  ProductLine,
  User,
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

const BRAND_PRESETS = ['EGO', 'FLEX', 'DEVON', 'SKIL', 'CTR', 'ERBAUER', 'KOBALT']

// 受控多选下拉：点击组件外部或按 Esc 关闭，避免 <details> 打开后无法收起。
function MultiSelect({
  options,
  selected,
  onChange,
  placeholder,
}: {
  options: Array<{ value: string; label: string }>
  selected: string[]
  onChange: (values: string[]) => void
  placeholder: string
}) {
  const [open, setOpen] = useState(false)
  const wrapperRef = useRef<HTMLDivElement>(null)
  useEffect(() => {
    if (!open) return
    const handleClickOutside = (event: MouseEvent) => {
      if (!wrapperRef.current?.contains(event.target as Node)) setOpen(false)
    }
    const handleKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape') setOpen(false)
    }
    document.addEventListener('mousedown', handleClickOutside)
    document.addEventListener('keydown', handleKey)
    return () => {
      document.removeEventListener('mousedown', handleClickOutside)
      document.removeEventListener('keydown', handleKey)
    }
  }, [open])
  return (
    <div className="project-multiselect" ref={wrapperRef}>
      <button
        type="button"
        className="project-multiselect-summary"
        aria-expanded={open}
        onClick={() => setOpen(value => !value)}
      >
        {selected.length ? `已选 ${selected.length} 项` : placeholder}
      </button>
      {open && (
        <div className="project-multiselect-options">
          {options.length === 0 && <span style={{ color: '#94a3b8', fontSize: 12 }}>暂无可选项</span>}
          {options.map(option => (
            <label key={option.value}>
              <input
                type="checkbox"
                checked={selected.includes(option.value)}
                onChange={event => onChange(event.target.checked
                  ? [...selected, option.value]
                  : selected.filter(value => value !== option.value))}
              />
              {option.label}
            </label>
          ))}
        </div>
      )}
    </div>
  )
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
  owner_user_id: string
  category: string
  description: string
  is_active: boolean
}

interface ProjectForm {
  name: string
  project_no: string
  product_id: string
  product_category: string
  product_line_ids: string[]
  project_level: string
  project_type: string
  brands: string
  project_manager: string
  research_owner: string
  shipping_regions: string
  current_stage: string
  product_model: string
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

const emptyProduct: ProductForm = { name: '', code: '', product_line_id: '', owner_id: '', owner_user_id: '', category: '', description: '', is_active: true }
const emptyProject: ProjectForm = { name: '', project_no: '', product_id: '', product_category: '', product_line_ids: [], project_level: '', project_type: '', brands: '', project_manager: '', research_owner: '', shipping_regions: '', current_stage: '', product_model: '', module: '', status: 'in_progress', start_date: '', end_date: '', description: '' }
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
  const [accounts, setAccounts] = useState<User[]>([])
  const [productLines, setProductLines] = useState<ProductLine[]>([])

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
  const [bulkCategoryText, setBulkCategoryText] = useState('')
  const [bulkCategorySaving, setBulkCategorySaving] = useState(false)
  const [productSearch, setProductSearch] = useState('')
  const [productLineFilter, setProductLineFilter] = useState('')
  const [productStatusFilter, setProductStatusFilter] = useState<'all' | 'active' | 'inactive'>('all')
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
      const [loadedProducts, loadedProjects, loadedTags, loadedGroups, loadedDepartments, loadedPeople, loadedLines, loadedUsers] = await Promise.all([
        productApi.list(), projectApi.list(), tagApi.list(), tagGroupApi.list(),
        departmentApi.list(), personApi.list(), productLineApi.list(), sharingApi.listUsers(),
      ])
      setProducts(loadedProducts)
      setProjects(loadedProjects)
      setTags(loadedTags)
      setTagGroups(loadedGroups)
      setDepartments(loadedDepartments)
      setPeople(loadedPeople)
      setProductLines(loadedLines)
      setAccounts(loadedUsers)
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
  // 项目“产品分类”的下拉选项来自产品管理中维护的分类，去重后排序。
  const productCategories = useMemo(
    () => Array.from(new Set(products.flatMap(product => [product.name, product.category]).filter((value): value is string => !!value))).sort(),
    [products],
  )
  const filteredProducts = useMemo(() => products.filter(product => {
    const needle = productSearch.trim().toLowerCase()
    const matchesText = !needle || [product.name, product.code, product.category, product.description].some(value => String(value || '').toLowerCase().includes(needle))
    const matchesLine = !productLineFilter || String(product.product_line_id || '') === productLineFilter
    const matchesStatus = productStatusFilter === 'all' || (productStatusFilter === 'active' ? product.is_active !== false : product.is_active === false)
    return matchesText && matchesLine && matchesStatus
  }), [products, productSearch, productLineFilter, productStatusFilter])

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
        owner_user_id: optionalNumber(productForm.owner_user_id),
        category: productForm.category.trim() || undefined, description: productForm.description.trim() || undefined,
        is_active: productForm.is_active,
      }
      const result = editingProductId ? await productApi.update(editingProductId, payload) : await productApi.create(payload)
      setProducts(current => editingProductId ? current.map(item => item.id === result.id ? result : item) : [...current, result])
      setEditingProductId(null); setProductForm(emptyProduct); setShowProductForm(false)
    } catch (actionError: unknown) { fail(actionError) } finally { setSaving(false) }
  }

  const saveBulkCategories = async () => {
    const names = [...new Set(bulkCategoryText.split(/\r?\n/).map(value => value.trim()).filter(Boolean))]
    if (!names.length) return
    setBulkCategorySaving(true); setError('')
    try {
      const created = await Promise.all(names.map(name => productApi.create({ name, category: name, is_active: true })))
      setProducts(current => [...current, ...created]); setBulkCategoryText('')
    } catch (cause) { fail(cause) } finally { setBulkCategorySaving(false) }
  }

  const saveProject = async () => {
    if (!projectForm.name.trim()) { setError('项目名称不能为空'); return }
    setSaving(true); setError('')
    try {
      const payload = {
        name: projectForm.name.trim(), project_no: projectForm.project_no.trim() || (editingProjectId ? null : undefined),
        product_id: optionalNumber(projectForm.product_id), module: projectForm.module.trim() || (editingProjectId ? null : undefined),
        product_category: projectForm.product_category.trim() || (editingProjectId ? null : undefined),
        product_line_ids: projectForm.product_line_ids.map(Number),
        project_level: projectForm.project_level || (editingProjectId ? null : undefined),
        project_type: projectForm.project_type || (editingProjectId ? null : undefined),
        brands: projectForm.brands.split(',').map(value => value.trim()).filter(Boolean),
        project_manager: projectForm.project_manager.trim() || (editingProjectId ? null : undefined),
        research_owner: projectForm.research_owner.trim() || (editingProjectId ? null : undefined),
        shipping_regions: projectForm.shipping_regions.trim() || (editingProjectId ? null : undefined),
        current_stage: projectForm.current_stage || (editingProjectId ? null : undefined),
        product_model: projectForm.product_model.trim() || (editingProjectId ? null : undefined),
        status: projectForm.status, start_date: projectForm.start_date || (editingProjectId ? null : undefined),
        end_date: projectForm.end_date || (editingProjectId ? null : undefined), description: projectForm.description.trim() || (editingProjectId ? null : undefined),
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
      <div className="management-hero">
        <div><span className="management-kicker">业务资产 · 产品目录</span><h2>产品管理</h2><p>统一维护产品、产品线和负责人，产品会同步成为专利库与项目的业务入口。</p></div>
        <button className="btn btn-primary" onClick={() => { beginCreate(); setShowProductForm(true) }}>新增产品</button>
      </div>
      <div className="management-overview-grid">
        <div className="management-overview-card accent"><span>产品总数</span><strong>{products.length}</strong><small>已建立的业务产品</small></div>
        <div className="management-overview-card"><span>启用中</span><strong>{products.filter(item => item.is_active !== false).length}</strong><small>可用于库内关联</small></div>
        <div className="management-overview-card"><span>产品线</span><strong>{productLines.length}</strong><small>上层业务分类</small></div>
        <div className="management-overview-card"><span>专利覆盖</span><strong>{products.reduce((sum, item) => sum + (item.patent_count || 0), 0)}</strong><small>已关联专利记录</small></div>
      </div>
      {(showProductForm || editingProductId !== null) && (
        <div className="management-form">
          <div className="management-form-grid">
            <FormField label="产品名称"><input className="form-input" style={inputStyle} value={productForm.name} onChange={e => setProductForm({ ...productForm, name: e.target.value })} /></FormField>
            <FormField label="产品编码"><input className="form-input" style={inputStyle} value={productForm.code} onChange={e => setProductForm({ ...productForm, code: e.target.value })} /></FormField>
            <FormField label="产品线"><select className="form-input" style={inputStyle} value={productForm.product_line_id} onChange={e => setProductForm({ ...productForm, product_line_id: e.target.value })}><option value="">未关联</option>{productLines.map(line => <option key={line.id} value={line.id}>{line.name}</option>)}</select></FormField>
            <FormField label="负责人账号"><select className="form-input" style={inputStyle} value={productForm.owner_user_id} onChange={e => setProductForm({ ...productForm, owner_user_id: e.target.value })}><option value="">未指定</option>{accounts.filter(account => account.is_active !== false).map(account => <option key={account.id} value={account.id}>{account.display_name || account.username}{account.employee_no ? ` · ${account.employee_no}` : ` · ${account.username}`}</option>)}</select></FormField>
            <FormField label="分类"><input className="form-input" style={inputStyle} value={productForm.category} onChange={e => setProductForm({ ...productForm, category: e.target.value })} /></FormField>
            <label style={{ display: 'flex', alignItems: 'center', gap: 8, paddingTop: 20, color: '#475569', fontSize: 12 }}><input type="checkbox" checked={productForm.is_active} onChange={e => setProductForm({ ...productForm, is_active: e.target.checked })} />启用</label>
          </div>
          <FormField label="描述"><textarea className="form-input" style={{ ...inputStyle, minHeight: 64 }} value={productForm.description} onChange={e => setProductForm({ ...productForm, description: e.target.value })} /></FormField>
          <div className="management-form-actions"><button className="btn btn-primary" disabled={saving} onClick={() => void saveProduct()}>{saving ? '保存中...' : editingProductId ? '保存修改' : '创建产品'}</button><button className="btn btn-secondary" onClick={() => { setEditingProductId(null); setProductForm(emptyProduct); setShowProductForm(false) }}>取消</button></div>
        </div>
      )}
      <div className="management-product-tools">
        <div className="management-search"><span>⌕</span><input value={productSearch} onChange={event => setProductSearch(event.target.value)} placeholder="搜索产品名称、编码或分类" /></div>
        <select className="form-input" value={productLineFilter} onChange={event => setProductLineFilter(event.target.value)}><option value="">全部产品线</option>{productLines.map(line => <option key={line.id} value={line.id}>{line.name}</option>)}</select>
        <div className="management-segmented">{([['all', '全部'], ['active', '启用'], ['inactive', '停用']] as const).map(([value, label]) => <button key={value} className={productStatusFilter === value ? 'active' : ''} onClick={() => setProductStatusFilter(value)}>{label}</button>)}</div>
        <details className="management-bulk-popover"><summary>批量导入品类</summary><div><textarea className="form-input" value={bulkCategoryText} onChange={event => setBulkCategoryText(event.target.value)} placeholder="每行一个品类名称" /><button className="btn btn-secondary" disabled={bulkCategorySaving || !bulkCategoryText.trim()} onClick={() => void saveBulkCategories()}>{bulkCategorySaving ? '创建中…' : '逐行创建'}</button></div></details>
      </div>
      {filteredProducts.length > 0 ? <div className="management-product-grid">{filteredProducts.map(product => {
        const owner = accounts.find(account => account.id === product.owner_user_id)?.display_name || accounts.find(account => account.id === product.owner_user_id)?.username || personNameById.get(product.owner_id ?? 0)
        return <article className="management-product-card" key={product.id}>
          <div className="management-product-card-top"><div className="management-product-mark">{product.name.slice(0, 1).toUpperCase()}</div><div className="management-product-title"><strong>{product.name}</strong><span>{product.code || '未设置编码'}</span></div><span className={`management-status-dot ${product.is_active === false ? 'inactive' : ''}`}>{product.is_active === false ? '停用' : '启用'}</span></div>
          <div className="management-product-tags"><span>{productLineNameById.get(product.product_line_id ?? 0) || '未关联产品线'}</span>{product.category && <span>{product.category}</span>}</div>
          <p>{product.description || '暂无产品描述，编辑后可补充业务定位。'}</p>
          <div className="management-product-stats"><div><strong>{product.patent_count ?? 0}</strong><span>关联专利</span></div><div><strong>{owner || '—'}</strong><span>负责人</span></div></div>
          <div className="management-product-actions"><button className="btn btn-secondary" onClick={() => navigate(`/patents?product=${product.id}`)}>查看关联专利</button><RowActions onEdit={() => { setEditingProductId(product.id); setProductForm({ name: product.name, code: product.code || '', product_line_id: product.product_line_id ? String(product.product_line_id) : '', owner_id: product.owner_id ? String(product.owner_id) : '', owner_user_id: product.owner_user_id ? String(product.owner_user_id) : '', category: product.category || '', description: product.description || '', is_active: product.is_active !== false }); setShowProductForm(true) }} onDelete={() => void remove(`产品“${product.name}”`, () => productApi.delete(product.id), () => setProducts(current => current.filter(item => item.id !== product.id)))} /></div>
        </article>
      })}</div> : <EmptyState text={products.length ? '没有符合筛选条件的产品' : '暂无产品'} />}
    </>
  )

  const renderProjects = () => (
    <>
      <ManagementHeader title="项目管理" description="维护项目资料、所属产品线和业务阶段；打开项目可查看 Wiki、关联附件及变更记录。" onCreate={() => { beginCreate(); setShowProjectForm(true) }} createLabel="新增项目" />
      {(showProjectForm || editingProjectId !== null) && <div className="management-form">
        <div className="management-form-grid">
          <FormField label="项目名称"><input className="form-input" style={inputStyle} value={projectForm.name} onChange={e => setProjectForm({ ...projectForm, name: e.target.value })} /></FormField>
          <FormField label="项目号"><input className="form-input" style={inputStyle} value={projectForm.project_no} onChange={e => setProjectForm({ ...projectForm, project_no: e.target.value })} /></FormField>
          <FormField label="产品分类"><select className="form-input" style={inputStyle} value={projectForm.product_category} onChange={e => setProjectForm({ ...projectForm, product_category: e.target.value })}><option value="">未设置</option>{productCategories.map(category => <option key={category} value={category}>{category}</option>)}</select></FormField>
          <FormField label="项目等级"><select className="form-input" style={inputStyle} value={projectForm.project_level} onChange={e => setProjectForm({ ...projectForm, project_level: e.target.value })}><option value="">未设置</option><option value="NEW">NEW</option><option value="RESKIN">RESKIN</option></select></FormField>
          <FormField label="项目类型"><select className="form-input" style={inputStyle} value={projectForm.project_type} onChange={e => setProjectForm({ ...projectForm, project_type: e.target.value })}><option value="">未设置</option><option value="OBM">OBM</option><option value="OEM">OEM</option><option value="ODM">ODM</option></select></FormField>
          <FormField label="当前项目阶段"><select className="form-input" style={inputStyle} value={projectForm.current_stage} onChange={e => setProjectForm({ ...projectForm, current_stage: e.target.value })}><option value="">未设置</option><option value="pre_research">预研</option>{['TR1', 'TR2', 'TR3', 'TR4', 'TR5'].map(stage => <option key={stage} value={stage}>{stage}</option>)}</select></FormField>
          <FormField label="状态"><select className="form-input" style={inputStyle} value={projectForm.status} onChange={e => setProjectForm({ ...projectForm, status: e.target.value })}><option value="in_progress">进行中</option><option value="paused">暂停</option><option value="shipped">已出货</option></select></FormField>
          <FormField label="项目管理"><input className="form-input" style={inputStyle} value={projectForm.project_manager} onChange={e => setProjectForm({ ...projectForm, project_manager: e.target.value })} /></FormField>
          <FormField label="研发"><input className="form-input" style={inputStyle} value={projectForm.research_owner} onChange={e => setProjectForm({ ...projectForm, research_owner: e.target.value })} /></FormField>
          <FormField label="出货地区"><input className="form-input" style={inputStyle} value={projectForm.shipping_regions} onChange={e => setProjectForm({ ...projectForm, shipping_regions: e.target.value })} /></FormField>
          <FormField label="产品型号"><input className="form-input" style={inputStyle} value={projectForm.product_model} onChange={e => setProjectForm({ ...projectForm, product_model: e.target.value })} /></FormField>
          <FormField label="开始日期"><input className="form-input" style={inputStyle} type="date" value={projectForm.start_date} onChange={e => setProjectForm({ ...projectForm, start_date: e.target.value })} /></FormField>
          <FormField label="结束日期"><input className="form-input" style={inputStyle} type="date" value={projectForm.end_date} onChange={e => setProjectForm({ ...projectForm, end_date: e.target.value })} /></FormField>
        </div>
        <FormField label="所属产品线"><MultiSelect options={productLines.map(line => ({ value: String(line.id), label: line.name }))} selected={projectForm.product_line_ids} onChange={values => setProjectForm({ ...projectForm, product_line_ids: values })} placeholder="选择产品线" /></FormField>
        <FormField label="所涉品牌"><MultiSelect options={BRAND_PRESETS.map(brand => ({ value: brand, label: brand }))} selected={projectForm.brands.split(',').map(value => value.trim()).filter(value => BRAND_PRESETS.includes(value))} onChange={presets => { const customBrands = projectForm.brands.split(',').map(value => value.trim()).filter(value => value && !BRAND_PRESETS.includes(value)); setProjectForm({ ...projectForm, brands: [...presets, ...customBrands].join(', ') }) }} placeholder="选择品牌" /><input className="form-input" style={{ ...inputStyle, marginTop: 8 }} placeholder="自定义品牌，可用逗号分隔" value={projectForm.brands.split(',').map(value => value.trim()).filter(value => value && !BRAND_PRESETS.includes(value)).join(', ')} onChange={event => { const presets = projectForm.brands.split(',').map(value => value.trim()).filter(value => BRAND_PRESETS.includes(value)); setProjectForm({ ...projectForm, brands: [...presets, ...event.target.value.split(',').map(value => value.trim()).filter(Boolean)].join(', ') }) }} /></FormField>
        <div style={{ marginTop: 12 }}><FormField label="项目描述"><textarea className="form-input" style={{ ...inputStyle, minHeight: 64 }} value={projectForm.description} onChange={e => setProjectForm({ ...projectForm, description: e.target.value })} /></FormField></div>
        <div className="management-form-actions"><button className="btn btn-primary" disabled={saving} onClick={() => void saveProject()}>{saving ? '保存中...' : editingProjectId ? '保存修改' : '创建项目'}</button><button className="btn btn-secondary" onClick={() => { setEditingProjectId(null); setProjectForm(emptyProject); setShowProjectForm(false) }}>取消</button></div>
      </div>}
      <TableShell><TableHead><Th>项目</Th><Th>项目分类</Th><Th>等级 / 类型</Th><Th>产品线</Th><Th>阶段 / 状态</Th><Th>专利数</Th><Th>操作</Th></TableHead><tbody>{projects.map(project => {
        const legacyStatus = project.status === 'active' || project.status === 'planned' ? 'in_progress' : project.status === 'completed' ? 'shipped' : project.status === 'archived' ? 'paused' : project.status
        const productLinesForProject = productLines.filter(line => (project.product_line_ids || []).includes(line.id)).map(line => line.name).join('、')
        return <tr key={project.id}><Td><button type="button" onClick={() => navigate(`/projects/${project.id}`)} style={{ border: 0, background: 'transparent', color: '#1d4ed8', padding: 0, cursor: 'pointer', fontWeight: 600, textAlign: 'left' }}>{project.name}</button>{(project.project_no || project.code) && <div style={{ color: '#94a3b8', marginTop: 3 }}>{project.project_no || project.code}</div>}</Td><Td>{project.product_category || productNameById.get(project.product_id ?? 0) || '-'}</Td><Td>{[project.project_level, project.project_type].filter(Boolean).join(' / ') || '-'}</Td><Td>{productLinesForProject || '-'}</Td><Td>{project.current_stage || '-'} · {legacyStatus === 'paused' ? '暂停' : legacyStatus === 'shipped' ? '已出货' : '进行中'}</Td><Td>{project.patent_count ?? 0}</Td><Td><RowActions onEdit={() => { setEditingProjectId(project.id); setProjectForm({ ...emptyProject, name: project.name, project_no: project.project_no || project.code || '', product_id: project.product_id ? String(project.product_id) : '', product_category: project.product_category || '', product_line_ids: (project.product_line_ids || []).map(String), project_level: project.project_level || '', project_type: project.project_type || '', brands: (project.brands || []).join(', '), project_manager: project.project_manager || '', research_owner: project.research_owner || '', shipping_regions: project.shipping_regions || '', current_stage: project.current_stage || '', product_model: project.product_model || '', module: project.module || '', status: legacyStatus || 'in_progress', start_date: project.start_date || '', end_date: project.end_date || '', description: project.description || '' }) }} onDelete={() => void remove(`项目“${project.name}”`, () => projectApi.delete(project.id), () => setProjects(current => current.filter(item => item.id !== project.id)))} /></Td></tr>
      })}</tbody></TableShell>{projects.length === 0 && <EmptyState text="暂无项目" />}
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
        {tabs.map(item => <button key={item.key} className={`management-tab ${tab === item.key ? 'active' : ''}`} onClick={() => { setTab(item.key); setError('') }}><span>{item.label}</span><small>{item.key === 'products' ? products.length : item.key === 'projects' ? projects.length : item.key === 'tags' ? tags.length : item.key === 'organization' ? people.length : productLines.length}</small></button>)}
      </div>
      {error && <div className="management-error">{error}</div>}
      {tab === 'products' && renderProducts()}
      {tab === 'projects' && renderProjects()}
      {tab === 'tags' && renderTags()}
      {tab === 'organization' && renderOrganization()}
      {tab === 'product-lines' && renderProductLines()}
    </div>
  )
}
