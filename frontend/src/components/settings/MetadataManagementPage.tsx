import { useState, useEffect, useCallback } from 'react'
import {
  productApi, projectApi, tagApi, tagGroupApi,
  departmentApi, personApi,
} from '../../api'
import { useAppStore } from '../../store'
import type {
  Product, Project, Tag, TagGroup, Department, Person,
} from '../../types'

type Tab = 'products' | 'projects' | 'tags' | 'depts'

export default function MetadataManagementPage() {
  const [tab, setTab] = useState<Tab>('products')
  const {
    setProducts, setTags, setProjects,
  } = useAppStore()

  const tabs: { key: Tab; label: string }[] = [
    { key: 'products', label: '产品' },
    { key: 'projects', label: '项目' },
    { key: 'tags', label: '标签 / 标签组' },
    { key: 'depts', label: '部门 / 人员' },
  ]

  return (
    <div style={{ padding: 24, color: '#e2e8f0' }}>
      <div style={{ marginBottom: 16 }}>
        <h2 style={{ margin: 0, color: '#f1f5f9' }}>元数据管理</h2>
        <p style={{ margin: '4px 0 0', color: '#94a3b8', fontSize: 13 }}>
          管理产品、项目、标签、部门与人员等基础元数据。可在导入/编辑专利时引用。
        </p>
      </div>

      <div style={{ display: 'flex', gap: 4, borderBottom: '1px solid #334155', marginBottom: 16 }}>
        {tabs.map(t => (
          <button
            key={t.key}
            onClick={() => setTab(t.key)}
            style={{
              padding: '8px 14px', border: 'none', background: 'transparent',
              cursor: 'pointer', fontSize: 13,
              fontWeight: tab === t.key ? 600 : 400,
              color: tab === t.key ? '#3b82f6' : '#94a3b8',
              borderBottom: tab === t.key ? '2px solid #3b82f6' : '2px solid transparent',
              marginBottom: '-1px',
            }}
          >
            {t.label}
          </button>
        ))}
      </div>

      <div>
        {tab === 'products' && <ProductsTab onChange={setProducts} />}
        {tab === 'projects' && <ProjectsTab onChange={setProjects} />}
        {tab === 'tags' && <TagsTab onChange={setTags} />}
        {tab === 'depts' && <DeptsTab />}
      </div>
    </div>
  )
}

// ============================================================
// 通用 CRUD 工具
// ============================================================
function useCrud<T extends { id: number }>(loadFn: () => Promise<T[]>) {
  const [items, setItems] = useState<T[]>([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const reload = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const data = await loadFn()
      setItems(data)
    } catch (e: any) {
      setError(e?.message || '加载失败')
    } finally {
      setLoading(false)
    }
  }, [loadFn])

  useEffect(() => { reload() }, [reload])

  return { items, setItems, loading, error, reload }
}

function Toolbar({ title, count, onAdd }: { title: string; count: number; onAdd: () => void }) {
  return (
    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 12 }}>
      <div style={{ fontSize: 13, color: '#94a3b8' }}>{title} · 共 {count} 条</div>
      <button className="btn btn-primary" onClick={onAdd} style={{ fontSize: 12, padding: '4px 10px' }}>
        + 新建
      </button>
    </div>
  )
}

function EmptyRow({ colSpan, text }: { colSpan: number; text: string }) {
  return (
    <tr>
      <td colSpan={colSpan} style={{ padding: 16, textAlign: 'center', color: '#64748b', fontSize: 12 }}>
        {text}
      </td>
    </tr>
  )
}

const inputStyle: React.CSSProperties = {
  fontSize: 12, padding: '4px 8px', background: '#1e293b',
  border: '1px solid #334155', color: '#e2e8f0', width: '100%',
}

const cellStyle: React.CSSProperties = { padding: '8px 10px', fontSize: 12, color: '#e2e8f0' }
const headerCellStyle: React.CSSProperties = { padding: '8px 10px', fontSize: 11, color: '#cbd5e1', textAlign: 'left' as const }

// ============================================================
// 产品 Tab
// ============================================================
function ProductsTab({ onChange }: { onChange: (items: Product[]) => void }) {
  const { items, setItems, loading, error } = useCrud<Product>(() => productApi.list())
  const [editing, setEditing] = useState<{ id: number | null; form: Partial<Product> } | null>(null)

  useEffect(() => { onChange(items) }, [items, onChange])

  const startAdd = () => setEditing({ id: null, form: { name: '', code: '', category: '', description: '', is_active: true } })
  const startEdit = (p: Product) => setEditing({ id: p.id, form: { ...p } })

  const save = async () => {
    if (!editing || !editing.form.name?.trim()) return
    try {
      if (editing.id == null) {
        const created = await productApi.create(editing.form)
        setItems([...items, created])
      } else {
        const updated = await productApi.update(editing.id, editing.form)
        setItems(items.map(p => p.id === updated.id ? updated : p))
      }
      setEditing(null)
    } catch (e: any) {
      alert(e?.response?.data?.detail || '保存失败')
    }
  }

  const remove = async (p: Product) => {
    if (!confirm(`确定删除产品"${p.name}"？`)) return
    try {
      await productApi.delete(p.id)
      setItems(items.filter(x => x.id !== p.id))
    } catch (e: any) {
      alert(e?.response?.data?.detail || '删除失败')
    }
  }

  if (loading && items.length === 0) return <div style={{ color: '#94a3b8' }}>加载中...</div>
  if (error) return <div style={{ color: '#f87171' }}>{error}</div>

  return (
    <div>
      <Toolbar title="产品" count={items.length} onAdd={startAdd} />

      {editing && (
        <div style={{
          padding: 12, background: '#0f172a', borderRadius: 6, marginBottom: 12,
          display: 'grid', gridTemplateColumns: '1fr 1fr 1fr 1fr', gap: 8,
        }}>
          <div>
            <label style={{ fontSize: 11, color: '#cbd5e1' }}>名称 *</label>
            <input style={inputStyle} value={editing.form.name || ''} onChange={e => setEditing({ ...editing, form: { ...editing.form, name: e.target.value } })} />
          </div>
          <div>
            <label style={{ fontSize: 11, color: '#cbd5e1' }}>代码</label>
            <input style={inputStyle} value={editing.form.code || ''} onChange={e => setEditing({ ...editing, form: { ...editing.form, code: e.target.value } })} />
          </div>
          <div>
            <label style={{ fontSize: 11, color: '#cbd5e1' }}>类别</label>
            <input style={inputStyle} value={editing.form.category || ''} onChange={e => setEditing({ ...editing, form: { ...editing.form, category: e.target.value } })} />
          </div>
          <div>
            <label style={{ fontSize: 11, color: '#cbd5e1' }}>活跃</label>
            <select style={inputStyle} value={editing.form.is_active === false ? 'false' : 'true'} onChange={e => setEditing({ ...editing, form: { ...editing.form, is_active: e.target.value === 'true' } })}>
              <option value="true">是</option>
              <option value="false">否</option>
            </select>
          </div>
          <div style={{ gridColumn: '1 / -1' }}>
            <label style={{ fontSize: 11, color: '#cbd5e1' }}>描述</label>
            <input style={inputStyle} value={editing.form.description || ''} onChange={e => setEditing({ ...editing, form: { ...editing.form, description: e.target.value } })} />
          </div>
          <div style={{ gridColumn: '1 / -1', display: 'flex', gap: 8, justifyContent: 'flex-end' }}>
            <button className="btn btn-secondary" onClick={() => setEditing(null)}>取消</button>
            <button className="btn btn-primary" onClick={save}>保存</button>
          </div>
        </div>
      )}

      <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 12 }}>
        <thead>
          <tr style={{ background: '#1e293b' }}>
            <th style={headerCellStyle}>名称</th>
            <th style={headerCellStyle}>代码</th>
            <th style={headerCellStyle}>类别</th>
            <th style={headerCellStyle}>专利数</th>
            <th style={headerCellStyle}>状态</th>
            <th style={headerCellStyle}>操作</th>
          </tr>
        </thead>
        <tbody>
          {items.length === 0 ? (
            <EmptyRow colSpan={6} text="暂无产品。点击右上角 + 新建。" />
          ) : items.map(p => (
            <tr key={p.id} style={{ borderBottom: '1px solid #1e293b' }}>
              <td style={cellStyle}>
                {p.name}
                {p.description && <div style={{ fontSize: 10, color: '#64748b' }}>{p.description}</div>}
              </td>
              <td style={cellStyle}>{p.code || '—'}</td>
              <td style={cellStyle}>{p.category || '—'}</td>
              <td style={cellStyle}>{p.patent_count ?? 0}</td>
              <td style={cellStyle}>
                {p.is_active === false
                  ? <span style={{ color: '#fbbf24' }}>停用</span>
                  : <span style={{ color: '#10b981' }}>活跃</span>}
              </td>
              <td style={cellStyle}>
                <button className="btn btn-secondary" style={{ fontSize: 10, padding: '2px 6px', marginRight: 4 }} onClick={() => startEdit(p)}>编辑</button>
                <button className="btn btn-secondary" style={{ fontSize: 10, padding: '2px 6px', color: '#f87171' }} onClick={() => remove(p)}>删除</button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

// ============================================================
// 项目 Tab
// ============================================================
function ProjectsTab({ onChange }: { onChange: (items: Project[]) => void }) {
  const { items, setItems, loading, error } = useCrud<Project>(() => projectApi.list())
  const [editing, setEditing] = useState<{ id: number | null; form: Partial<Project> } | null>(null)
  const [products, setProducts] = useState<Product[]>([])

  useEffect(() => { onChange(items) }, [items, onChange])
  useEffect(() => { productApi.list().then(setProducts).catch(() => {}) }, [])

  const startAdd = () => setEditing({ id: null, form: { name: '', code: '', status: 'active', description: '' } })
  const startEdit = (p: Project) => setEditing({ id: p.id, form: { ...p } })

  const save = async () => {
    if (!editing || !editing.form.name?.trim()) return
    try {
      if (editing.id == null) {
        const created = await projectApi.create(editing.form)
        setItems([...items, created])
      } else {
        const updated = await projectApi.update(editing.id, editing.form)
        setItems(items.map(p => p.id === updated.id ? updated : p))
      }
      setEditing(null)
    } catch (e: any) {
      alert(e?.response?.data?.detail || '保存失败')
    }
  }

  const remove = async (p: Project) => {
    if (!confirm(`确定删除项目"${p.name}"？`)) return
    try {
      await projectApi.delete(p.id)
      setItems(items.filter(x => x.id !== p.id))
    } catch (e: any) {
      alert(e?.response?.data?.detail || '删除失败')
    }
  }

  if (loading && items.length === 0) return <div style={{ color: '#94a3b8' }}>加载中...</div>
  if (error) return <div style={{ color: '#f87171' }}>{error}</div>

  return (
    <div>
      <Toolbar title="项目" count={items.length} onAdd={startAdd} />

      {editing && (
        <div style={{
          padding: 12, background: '#0f172a', borderRadius: 6, marginBottom: 12,
          display: 'grid', gridTemplateColumns: '1fr 1fr 1fr 1fr', gap: 8,
        }}>
          <div>
            <label style={{ fontSize: 11, color: '#cbd5e1' }}>名称 *</label>
            <input style={inputStyle} value={editing.form.name || ''} onChange={e => setEditing({ ...editing, form: { ...editing.form, name: e.target.value } })} />
          </div>
          <div>
            <label style={{ fontSize: 11, color: '#cbd5e1' }}>代码</label>
            <input style={inputStyle} value={editing.form.code || ''} onChange={e => setEditing({ ...editing, form: { ...editing.form, code: e.target.value } })} />
          </div>
          <div>
            <label style={{ fontSize: 11, color: '#cbd5e1' }}>所属产品</label>
            <select style={inputStyle} value={editing.form.product_id ?? ''} onChange={e => setEditing({ ...editing, form: { ...editing.form, product_id: e.target.value ? Number(e.target.value) : undefined } })}>
              <option value="">（无）</option>
              {products.map(p => <option key={p.id} value={p.id}>{p.name}</option>)}
            </select>
          </div>
          <div>
            <label style={{ fontSize: 11, color: '#cbd5e1' }}>状态</label>
            <select style={inputStyle} value={editing.form.status || 'active'} onChange={e => setEditing({ ...editing, form: { ...editing.form, status: e.target.value } })}>
              <option value="active">进行中</option>
              <option value="paused">暂停</option>
              <option value="completed">已完成</option>
              <option value="cancelled">已取消</option>
            </select>
          </div>
          <div style={{ gridColumn: '1 / -1' }}>
            <label style={{ fontSize: 11, color: '#cbd5e1' }}>描述</label>
            <input style={inputStyle} value={editing.form.description || ''} onChange={e => setEditing({ ...editing, form: { ...editing.form, description: e.target.value } })} />
          </div>
          <div style={{ gridColumn: '1 / -1', display: 'flex', gap: 8, justifyContent: 'flex-end' }}>
            <button className="btn btn-secondary" onClick={() => setEditing(null)}>取消</button>
            <button className="btn btn-primary" onClick={save}>保存</button>
          </div>
        </div>
      )}

      <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 12 }}>
        <thead>
          <tr style={{ background: '#1e293b' }}>
            <th style={headerCellStyle}>名称</th>
            <th style={headerCellStyle}>代码</th>
            <th style={headerCellStyle}>所属产品</th>
            <th style={headerCellStyle}>模块</th>
            <th style={headerCellStyle}>状态</th>
            <th style={headerCellStyle}>专利数</th>
            <th style={headerCellStyle}>操作</th>
          </tr>
        </thead>
        <tbody>
          {items.length === 0 ? (
            <EmptyRow colSpan={7} text="暂无项目。点击右上角 + 新建。" />
          ) : items.map(p => (
            <tr key={p.id} style={{ borderBottom: '1px solid #1e293b' }}>
              <td style={cellStyle}>
                {p.name}
                {p.description && <div style={{ fontSize: 10, color: '#64748b' }}>{p.description}</div>}
              </td>
              <td style={cellStyle}>{p.code || '—'}</td>
              <td style={cellStyle}>{products.find(x => x.id === p.product_id)?.name || '—'}</td>
              <td style={cellStyle}>{p.module || '—'}</td>
              <td style={cellStyle}>{p.status || '—'}</td>
              <td style={cellStyle}>{p.patent_count ?? 0}</td>
              <td style={cellStyle}>
                <button className="btn btn-secondary" style={{ fontSize: 10, padding: '2px 6px', marginRight: 4 }} onClick={() => startEdit(p)}>编辑</button>
                <button className="btn btn-secondary" style={{ fontSize: 10, padding: '2px 6px', color: '#f87171' }} onClick={() => remove(p)}>删除</button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

// ============================================================
// 标签 / 标签组 Tab
// ============================================================
function TagsTab({ onChange }: { onChange: (items: Tag[]) => void }) {
  const { items: tags, setItems: setTags, loading: tagsLoading } = useCrud<Tag>(() => tagApi.list())
  const { items: groups, setItems: setGroups } = useCrud<TagGroup>(() => tagGroupApi.list())
  const [editingTag, setEditingTag] = useState<{ id: number | null; form: Partial<Tag> } | null>(null)
  const [editingGroup, setEditingGroup] = useState<{ id: number | null; form: Partial<TagGroup> } | null>(null)

  useEffect(() => { onChange(tags) }, [tags, onChange])

  const saveTag = async () => {
    if (!editingTag || !editingTag.form.name?.trim()) return
    try {
      if (editingTag.id == null) {
        const created = await tagApi.create(editingTag.form)
        setTags([...tags, created])
      } else {
        const updated = await tagApi.update(editingTag.id, editingTag.form)
        setTags(tags.map(t => t.id === updated.id ? updated : t))
      }
      setEditingTag(null)
    } catch (e: any) {
      alert(e?.response?.data?.detail || '保存失败')
    }
  }

  const removeTag = async (t: Tag) => {
    if (!confirm(`确定删除标签"${t.name}"？`)) return
    try {
      await tagApi.delete(t.id)
      setTags(tags.filter(x => x.id !== t.id))
    } catch (e: any) {
      alert(e?.response?.data?.detail || '删除失败')
    }
  }

  const saveGroup = async () => {
    if (!editingGroup || !editingGroup.form.name?.trim()) return
    try {
      if (editingGroup.id == null) {
        const created = await tagGroupApi.create(editingGroup.form)
        setGroups([...groups, created])
      } else {
        const updated = await tagGroupApi.update(editingGroup.id, editingGroup.form)
        setGroups(groups.map(g => g.id === updated.id ? updated : g))
      }
      setEditingGroup(null)
    } catch (e: any) {
      alert(e?.response?.data?.detail || '保存失败')
    }
  }

  const removeGroup = async (g: TagGroup) => {
    if (!confirm(`确定删除标签组"${g.name}"？组内标签会解除关联（不会被删除）。`)) return
    try {
      await tagGroupApi.delete(g.id)
      setGroups(groups.filter(x => x.id !== g.id))
      // 刷新 tags（group_id 被后端置空）
      const fresh = await tagApi.list()
      setTags(fresh)
    } catch (e: any) {
      alert(e?.response?.data?.detail || '删除失败')
    }
  }

  if (tagsLoading) return <div style={{ color: '#94a3b8' }}>加载中...</div>

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 24 }}>
      {/* 标签组 */}
      <div>
        <Toolbar title="标签组" count={groups.length} onAdd={() => setEditingGroup({ id: null, form: { name: '', description: '', color: '#3b82f6' } })} />

        {editingGroup && (
          <div style={{
            padding: 12, background: '#0f172a', borderRadius: 6, marginBottom: 12,
            display: 'grid', gridTemplateColumns: '2fr 3fr 1fr auto', gap: 8, alignItems: 'end',
          }}>
            <div>
              <label style={{ fontSize: 11, color: '#cbd5e1' }}>名称 *</label>
              <input style={inputStyle} value={editingGroup.form.name || ''} onChange={e => setEditingGroup({ ...editingGroup, form: { ...editingGroup.form, name: e.target.value } })} />
            </div>
            <div>
              <label style={{ fontSize: 11, color: '#cbd5e1' }}>描述</label>
              <input style={inputStyle} value={editingGroup.form.description || ''} onChange={e => setEditingGroup({ ...editingGroup, form: { ...editingGroup.form, description: e.target.value } })} />
            </div>
            <div>
              <label style={{ fontSize: 11, color: '#cbd5e1' }}>颜色</label>
              <input type="color" style={{ ...inputStyle, padding: 0, height: 28 }} value={editingGroup.form.color || '#3b82f6'} onChange={e => setEditingGroup({ ...editingGroup, form: { ...editingGroup.form, color: e.target.value } })} />
            </div>
            <div style={{ display: 'flex', gap: 4 }}>
              <button className="btn btn-secondary" onClick={() => setEditingGroup(null)}>取消</button>
              <button className="btn btn-primary" onClick={saveGroup}>保存</button>
            </div>
          </div>
        )}

        <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 12 }}>
          <thead>
            <tr style={{ background: '#1e293b' }}>
              <th style={headerCellStyle}>名称</th>
              <th style={headerCellStyle}>描述</th>
              <th style={headerCellStyle}>颜色</th>
              <th style={headerCellStyle}>标签数</th>
              <th style={headerCellStyle}>操作</th>
            </tr>
          </thead>
          <tbody>
            {groups.length === 0 ? (
              <EmptyRow colSpan={5} text="暂无标签组。" />
            ) : groups.map(g => (
              <tr key={g.id} style={{ borderBottom: '1px solid #1e293b' }}>
                <td style={cellStyle}>
                  <span style={{ display: 'inline-block', width: 8, height: 8, borderRadius: '50%', background: g.color || '#3b82f6', marginRight: 6 }} />
                  {g.name}
                </td>
                <td style={cellStyle}>{g.description || '—'}</td>
                <td style={cellStyle}><code style={{ fontSize: 10 }}>{g.color || '—'}</code></td>
                <td style={cellStyle}>{g.tags?.length ?? tags.filter(t => t.group_id === g.id).length}</td>
                <td style={cellStyle}>
                  <button className="btn btn-secondary" style={{ fontSize: 10, padding: '2px 6px', marginRight: 4 }} onClick={() => setEditingGroup({ id: g.id, form: { ...g } })}>编辑</button>
                  <button className="btn btn-secondary" style={{ fontSize: 10, padding: '2px 6px', color: '#f87171' }} onClick={() => removeGroup(g)}>删除</button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* 标签 */}
      <div>
        <Toolbar title="标签" count={tags.length} onAdd={() => setEditingTag({ id: null, form: { name: '', color: '#3b82f6', group_id: undefined } })} />

        {editingTag && (
          <div style={{
            padding: 12, background: '#0f172a', borderRadius: 6, marginBottom: 12,
            display: 'grid', gridTemplateColumns: '2fr 2fr 1fr auto', gap: 8, alignItems: 'end',
          }}>
            <div>
              <label style={{ fontSize: 11, color: '#cbd5e1' }}>名称 *</label>
              <input style={inputStyle} value={editingTag.form.name || ''} onChange={e => setEditingTag({ ...editingTag, form: { ...editingTag.form, name: e.target.value } })} />
            </div>
            <div>
              <label style={{ fontSize: 11, color: '#cbd5e1' }}>所属标签组</label>
              <select style={inputStyle} value={editingTag.form.group_id ?? ''} onChange={e => setEditingTag({ ...editingTag, form: { ...editingTag.form, group_id: e.target.value ? Number(e.target.value) : undefined } })}>
                <option value="">（无）</option>
                {groups.map(g => <option key={g.id} value={g.id}>{g.name}</option>)}
              </select>
            </div>
            <div>
              <label style={{ fontSize: 11, color: '#cbd5e1' }}>颜色</label>
              <input type="color" style={{ ...inputStyle, padding: 0, height: 28 }} value={editingTag.form.color || '#3b82f6'} onChange={e => setEditingTag({ ...editingTag, form: { ...editingTag.form, color: e.target.value } })} />
            </div>
            <div style={{ display: 'flex', gap: 4 }}>
              <button className="btn btn-secondary" onClick={() => setEditingTag(null)}>取消</button>
              <button className="btn btn-primary" onClick={saveTag}>保存</button>
            </div>
          </div>
        )}

        <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 12 }}>
          <thead>
            <tr style={{ background: '#1e293b' }}>
              <th style={headerCellStyle}>名称</th>
              <th style={headerCellStyle}>所属标签组</th>
              <th style={headerCellStyle}>颜色</th>
              <th style={headerCellStyle}>描述</th>
              <th style={headerCellStyle}>操作</th>
            </tr>
          </thead>
          <tbody>
            {tags.length === 0 ? (
              <EmptyRow colSpan={5} text="暂无标签。" />
            ) : tags.map(t => (
              <tr key={t.id} style={{ borderBottom: '1px solid #1e293b' }}>
                <td style={cellStyle}>
                  <span style={{ display: 'inline-block', width: 8, height: 8, borderRadius: '50%', background: t.color || '#3b82f6', marginRight: 6 }} />
                  {t.name}
                </td>
                <td style={cellStyle}>{groups.find(g => g.id === t.group_id)?.name || '—'}</td>
                <td style={cellStyle}><code style={{ fontSize: 10 }}>{t.color || '—'}</code></td>
                <td style={cellStyle}>{t.description || '—'}</td>
                <td style={cellStyle}>
                  <button className="btn btn-secondary" style={{ fontSize: 10, padding: '2px 6px', marginRight: 4 }} onClick={() => setEditingTag({ id: t.id, form: { ...t } })}>编辑</button>
                  <button className="btn btn-secondary" style={{ fontSize: 10, padding: '2px 6px', color: '#f87171' }} onClick={() => removeTag(t)}>删除</button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}

// ============================================================
// 部门 / 人员 Tab
// ============================================================
function DeptsTab() {
  const { items: depts, setItems: setDepts } = useCrud<Department>(() => departmentApi.list())
  const { items: people, setItems: setPeople } = useCrud<Person>(() => personApi.list())
  const [editingDept, setEditingDept] = useState<{ id: number | null; form: Partial<Department> } | null>(null)
  const [editingPerson, setEditingPerson] = useState<{ id: number | null; form: Partial<Person> } | null>(null)

  const saveDept = async () => {
    if (!editingDept || !editingDept.form.name?.trim()) return
    try {
      if (editingDept.id == null) {
        const created = await departmentApi.create(editingDept.form)
        setDepts([...depts, created])
      } else {
        const updated = await departmentApi.update(editingDept.id, editingDept.form)
        setDepts(depts.map(d => d.id === updated.id ? updated : d))
      }
      setEditingDept(null)
    } catch (e: any) {
      alert(e?.response?.data?.detail || '保存失败')
    }
  }

  const removeDept = async (d: Department) => {
    if (!confirm(`确定删除部门"${d.name}"？部门下人员会解除关联（不会被删除）。`)) return
    try {
      await departmentApi.delete(d.id)
      setDepts(depts.filter(x => x.id !== d.id))
      const fresh = await personApi.list()
      setPeople(fresh)
    } catch (e: any) {
      alert(e?.response?.data?.detail || '删除失败')
    }
  }

  const savePerson = async () => {
    if (!editingPerson || !editingPerson.form.name?.trim()) return
    try {
      if (editingPerson.id == null) {
        const created = await personApi.create(editingPerson.form)
        setPeople([...people, created])
      } else {
        const updated = await personApi.update(editingPerson.id, editingPerson.form)
        setPeople(people.map(p => p.id === updated.id ? updated : p))
      }
      setEditingPerson(null)
    } catch (e: any) {
      alert(e?.response?.data?.detail || '保存失败')
    }
  }

  const removePerson = async (p: Person) => {
    if (!confirm(`确定删除人员"${p.name}"？`)) return
    try {
      await personApi.delete(p.id)
      setPeople(people.filter(x => x.id !== p.id))
    } catch (e: any) {
      alert(e?.response?.data?.detail || '删除失败')
    }
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 24 }}>
      {/* 部门 */}
      <div>
        <Toolbar title="部门" count={depts.length} onAdd={() => setEditingDept({ id: null, form: { name: '', description: '' } })} />

        {editingDept && (
          <div style={{
            padding: 12, background: '#0f172a', borderRadius: 6, marginBottom: 12,
            display: 'grid', gridTemplateColumns: '2fr 3fr auto', gap: 8, alignItems: 'end',
          }}>
            <div>
              <label style={{ fontSize: 11, color: '#cbd5e1' }}>名称 *</label>
              <input style={inputStyle} value={editingDept.form.name || ''} onChange={e => setEditingDept({ ...editingDept, form: { ...editingDept.form, name: e.target.value } })} />
            </div>
            <div>
              <label style={{ fontSize: 11, color: '#cbd5e1' }}>描述</label>
              <input style={inputStyle} value={editingDept.form.description || ''} onChange={e => setEditingDept({ ...editingDept, form: { ...editingDept.form, description: e.target.value } })} />
            </div>
            <div style={{ display: 'flex', gap: 4 }}>
              <button className="btn btn-secondary" onClick={() => setEditingDept(null)}>取消</button>
              <button className="btn btn-primary" onClick={saveDept}>保存</button>
            </div>
          </div>
        )}

        <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 12 }}>
          <thead>
            <tr style={{ background: '#1e293b' }}>
              <th style={headerCellStyle}>名称</th>
              <th style={headerCellStyle}>描述</th>
              <th style={headerCellStyle}>成员数</th>
              <th style={headerCellStyle}>操作</th>
            </tr>
          </thead>
          <tbody>
            {depts.length === 0 ? (
              <EmptyRow colSpan={4} text="暂无部门。" />
            ) : depts.map(d => (
              <tr key={d.id} style={{ borderBottom: '1px solid #1e293b' }}>
                <td style={cellStyle}>{d.name}</td>
                <td style={cellStyle}>{d.description || '—'}</td>
                <td style={cellStyle}>{d.members?.length ?? people.filter(p => p.department_id === d.id).length}</td>
                <td style={cellStyle}>
                  <button className="btn btn-secondary" style={{ fontSize: 10, padding: '2px 6px', marginRight: 4 }} onClick={() => setEditingDept({ id: d.id, form: { ...d } })}>编辑</button>
                  <button className="btn btn-secondary" style={{ fontSize: 10, padding: '2px 6px', color: '#f87171' }} onClick={() => removeDept(d)}>删除</button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* 人员 */}
      <div>
        <Toolbar title="人员" count={people.length} onAdd={() => setEditingPerson({ id: null, form: { name: '', email: '', role: '', is_active: true } })} />

        {editingPerson && (
          <div style={{
            padding: 12, background: '#0f172a', borderRadius: 6, marginBottom: 12,
            display: 'grid', gridTemplateColumns: '2fr 2fr 2fr 2fr auto', gap: 8, alignItems: 'end',
          }}>
            <div>
              <label style={{ fontSize: 11, color: '#cbd5e1' }}>姓名 *</label>
              <input style={inputStyle} value={editingPerson.form.name || ''} onChange={e => setEditingPerson({ ...editingPerson, form: { ...editingPerson.form, name: e.target.value } })} />
            </div>
            <div>
              <label style={{ fontSize: 11, color: '#cbd5e1' }}>邮箱</label>
              <input style={inputStyle} value={editingPerson.form.email || ''} onChange={e => setEditingPerson({ ...editingPerson, form: { ...editingPerson.form, email: e.target.value } })} />
            </div>
            <div>
              <label style={{ fontSize: 11, color: '#cbd5e1' }}>部门</label>
              <select style={inputStyle} value={editingPerson.form.department_id ?? ''} onChange={e => setEditingPerson({ ...editingPerson, form: { ...editingPerson.form, department_id: e.target.value ? Number(e.target.value) : undefined } })}>
                <option value="">（无）</option>
                {depts.map(d => <option key={d.id} value={d.id}>{d.name}</option>)}
              </select>
            </div>
            <div>
              <label style={{ fontSize: 11, color: '#cbd5e1' }}>角色</label>
              <input style={inputStyle} value={editingPerson.form.role || ''} onChange={e => setEditingPerson({ ...editingPerson, form: { ...editingPerson.form, role: e.target.value } })} />
            </div>
            <div style={{ display: 'flex', gap: 4 }}>
              <button className="btn btn-secondary" onClick={() => setEditingPerson(null)}>取消</button>
              <button className="btn btn-primary" onClick={savePerson}>保存</button>
            </div>
          </div>
        )}

        <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 12 }}>
          <thead>
            <tr style={{ background: '#1e293b' }}>
              <th style={headerCellStyle}>姓名</th>
              <th style={headerCellStyle}>邮箱</th>
              <th style={headerCellStyle}>部门</th>
              <th style={headerCellStyle}>角色</th>
              <th style={headerCellStyle}>状态</th>
              <th style={headerCellStyle}>操作</th>
            </tr>
          </thead>
          <tbody>
            {people.length === 0 ? (
              <EmptyRow colSpan={6} text="暂无人员。" />
            ) : people.map(p => (
              <tr key={p.id} style={{ borderBottom: '1px solid #1e293b' }}>
                <td style={cellStyle}>{p.name}</td>
                <td style={cellStyle}>{p.email || '—'}</td>
                <td style={cellStyle}>{depts.find(d => d.id === p.department_id)?.name || '—'}</td>
                <td style={cellStyle}>{p.role || '—'}</td>
                <td style={cellStyle}>
                  {p.is_active === false
                    ? <span style={{ color: '#fbbf24' }}>停用</span>
                    : <span style={{ color: '#10b981' }}>活跃</span>}
                </td>
                <td style={cellStyle}>
                  <button className="btn btn-secondary" style={{ fontSize: 10, padding: '2px 6px', marginRight: 4 }} onClick={() => setEditingPerson({ id: p.id, form: { ...p } })}>编辑</button>
                  <button className="btn btn-secondary" style={{ fontSize: 10, padding: '2px 6px', color: '#f87171' }} onClick={() => removePerson(p)}>删除</button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}
