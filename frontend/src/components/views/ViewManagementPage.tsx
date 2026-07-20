import { useState, useEffect, useCallback } from 'react'
import { viewApi, fieldApi, databaseApi } from '../../api'
import { useAppStore } from '../../store'
import type {
  PatentView, ViewLocalField, ViewFilterRule, ViewColumnConfig,
  ViewSortConfig, FieldMetaWithView,
} from '../../types'

type EditTab = 'basic' | 'filter' | 'column' | 'sort' | 'localFields'

export default function ViewManagementPage() {
  const {
    currentDatabaseId, views, setViews, currentViewId, setCurrentViewId,
  } = useAppStore()
  const [includeArchived, setIncludeArchived] = useState(false)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  // P0-18：新建视图表单
  const [showCreate, setShowCreate] = useState(false)
  const [createForm, setCreateForm] = useState({
    name: '',
    description: '',
    view_type: 'personal' as 'personal' | 'shared',
  })
  const [creating, setCreating] = useState(false)

  // P0-18：编辑视图弹层
  const [editingView, setEditingView] = useState<PatentView | null>(null)
  const [editTab, setEditTab] = useState<EditTab>('basic')

  const reload = useCallback(async () => {
    if (currentDatabaseId == null) {
      setViews([])
      return
    }
    setLoading(true)
    setError(null)
    try {
      const list = await viewApi.list({
        database_id: currentDatabaseId,
        include_archived: includeArchived,
      })
      setViews(list)
    } catch (e: any) {
      setError(e?.message || '加载视图列表失败')
    } finally {
      setLoading(false)
    }
  }, [currentDatabaseId, includeArchived, setViews])

  useEffect(() => {
    reload()
  }, [reload])

  const handleArchive = async (v: PatentView) => {
    if (!confirm(`确定归档视图"${v.name}"？归档后不再在侧边栏显示，但数据保留。`)) return
    try {
      await viewApi.archive(v.id)
      await reload()
    } catch (e: any) {
      alert(e?.response?.data?.detail || '归档失败')
    }
  }

  const handleDelete = async (v: PatentView) => {
    if (!confirm(`确定删除视图"${v.name}"？此操作不可恢复。`)) return
    try {
      await viewApi.delete(v.id)
      if (currentViewId === v.id) setCurrentViewId(null)
      await reload()
    } catch (e: any) {
      alert(e?.response?.data?.detail || '删除失败')
    }
  }

  const handleSwitch = (v: PatentView) => {
    setCurrentViewId(v.id)
  }

  // P0-18：部门总表入口（若不存在则后端自动创建）
  const handleEnsureMaster = async () => {
    if (currentDatabaseId == null) return
    try {
      const master = await databaseApi.getOrCreateMasterView(currentDatabaseId)
      if (!views.some(v => v.id === master.id)) {
        setViews([...views, master])
      }
      setCurrentViewId(master.id)
      await reload()
    } catch (e: any) {
      alert(e?.response?.data?.detail || '获取/创建部门总表失败')
    }
  }

  // P0-18：新建视图
  const handleCreate = async () => {
    if (!createForm.name.trim() || currentDatabaseId == null) return
    setCreating(true)
    try {
      const created = await viewApi.create({
        name: createForm.name.trim(),
        database_id: currentDatabaseId,
        description: createForm.description.trim() || undefined,
        view_type: createForm.view_type,
        filter_config: {},
        column_config: [],
        sort_config: {},
      })
      setViews([...views, created])
      setShowCreate(false)
      setCreateForm({ name: '', description: '', view_type: 'personal' })
      // 直接打开编辑器
      setEditingView(created)
      setEditTab('basic')
    } catch (e: any) {
      alert(e?.response?.data?.detail || '创建失败')
    } finally {
      setCreating(false)
    }
  }

  // 编辑器关闭后同步回列表
  const handleEditorClose = async () => {
    if (editingView) {
      // 拉取最新视图对象，同步到列表
      try {
        const fresh = await viewApi.get(editingView.id)
        setViews(views.map(v => (v.id === fresh.id ? fresh : v)))
      } catch {}
    }
    setEditingView(null)
  }

  if (currentDatabaseId == null) {
    return <div style={{ padding: 24, color: '#cbd5e1' }}>请先在侧边栏选择一个库。</div>
  }

  return (
    <div style={{ padding: 24, color: '#e2e8f0' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16, flexWrap: 'wrap', gap: 8 }}>
        <div>
          <h2 style={{ margin: 0, color: '#f1f5f9' }}>视图管理</h2>
          <p style={{ margin: '4px 0 0', color: '#94a3b8', fontSize: 13 }}>
            管理当前库下的小表/部门总表：新建/编辑/归档/删除、配置筛选·列·排序、维护视图本地字段、字段提升。
          </p>
        </div>
        <div style={{ display: 'flex', gap: 12, alignItems: 'center' }}>
          <button
            className="btn btn-secondary"
            onClick={handleEnsureMaster}
            style={{ fontSize: 12, padding: '4px 10px' }}
            title="获取或创建部门级综合全属性总表"
          >
            ★ 部门总表
          </button>
          <button
            className="btn btn-primary"
            onClick={() => setShowCreate(true)}
            style={{ fontSize: 12, padding: '4px 10px' }}
          >
            + 新建视图
          </button>
          <label style={{ fontSize: 12, color: '#cbd5e1', display: 'flex', alignItems: 'center', gap: 6 }}>
            <input
              type="checkbox"
              checked={includeArchived}
              onChange={(e) => setIncludeArchived(e.target.checked)}
            />
            包含已归档
          </label>
        </div>
      </div>

      {error && (
        <div style={{ padding: 12, background: '#7f1d1d', color: '#fee2e2', borderRadius: 6, marginBottom: 12 }}>
          {error}
        </div>
      )}

      {loading ? (
        <div style={{ color: '#94a3b8' }}>加载中...</div>
      ) : views.length === 0 ? (
        <div style={{ color: '#94a3b8' }}>当前库暂无视图。可点击"+ 新建视图"创建。</div>
      ) : (
        <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13 }}>
          <thead>
            <tr style={{ background: '#1e293b', color: '#cbd5e1', textAlign: 'left' }}>
              <th style={{ padding: '8px 12px' }}>名称</th>
              <th style={{ padding: '8px 12px' }}>类型</th>
              <th style={{ padding: '8px 12px' }}>筛选规则</th>
              <th style={{ padding: '8px 12px' }}>列配置</th>
              <th style={{ padding: '8px 12px' }}>本地字段</th>
              <th style={{ padding: '8px 12px' }}>状态</th>
              <th style={{ padding: '8px 12px' }}>更新时间</th>
              <th style={{ padding: '8px 12px' }}>操作</th>
            </tr>
          </thead>
          <tbody>
            {views.map(v => {
              const filterCount = v.filter_config ? Object.keys(v.filter_config).length : 0
              const colCount = v.column_config?.length ?? 0
              const lfCount = v.local_fields?.length ?? 0
              return (
                <tr key={v.id} style={{ borderBottom: '1px solid #1e293b' }}>
                  <td style={{ padding: '8px 12px' }}>
                    {v.is_department_master && <span style={{ color: '#fbbf24', marginRight: 6 }}>★</span>}
                    {v.name}
                    {currentViewId === v.id && (
                      <span style={{ marginLeft: 8, fontSize: 11, color: '#3b82f6' }}>当前</span>
                    )}
                    {v.description && (
                      <div style={{ fontSize: 11, color: '#64748b', marginTop: 2 }}>{v.description}</div>
                    )}
                  </td>
                  <td style={{ padding: '8px 12px', color: '#94a3b8' }}>
                    {v.is_department_master ? '部门总表' :
                     v.view_type === 'shared' ? '共享' : '个人'}
                  </td>
                  <td style={{ padding: '8px 12px', color: '#94a3b8' }}>
                    {v.is_department_master ? '—' : `${filterCount} 条`}
                  </td>
                  <td style={{ padding: '8px 12px', color: '#94a3b8' }}>
                    {v.is_department_master ? '全部字段' : (colCount === 0 ? '全部字段' : `${colCount} 列`)}
                  </td>
                  <td style={{ padding: '8px 12px', color: '#94a3b8' }}>
                    {lfCount > 0 ? `${lfCount} 个` : '—'}
                  </td>
                  <td style={{ padding: '8px 12px' }}>
                    {v.is_archived ? (
                      <span style={{ color: '#fbbf24' }}>已归档</span>
                    ) : (
                      <span style={{ color: '#10b981' }}>活跃</span>
                    )}
                  </td>
                  <td style={{ padding: '8px 12px', color: '#94a3b8' }}>
                    {v.updated_at ? new Date(v.updated_at).toLocaleString('zh-CN') : '-'}
                  </td>
                  <td style={{ padding: '8px 12px', whiteSpace: 'nowrap' }}>
                    <button
                      className="btn btn-secondary"
                      style={{ fontSize: 11, padding: '3px 8px', marginRight: 4 }}
                      onClick={() => handleSwitch(v)}
                      disabled={currentViewId === v.id}
                    >
                      切换
                    </button>
                    <button
                      className="btn btn-secondary"
                      style={{ fontSize: 11, padding: '3px 8px', marginRight: 4 }}
                      onClick={() => { setEditingView(v); setEditTab('basic') }}
                    >
                      编辑
                    </button>
                    {!v.is_department_master && !v.is_archived && (
                      <button
                        className="btn btn-secondary"
                        style={{ fontSize: 11, padding: '3px 8px', marginRight: 4 }}
                        onClick={() => handleArchive(v)}
                      >
                        归档
                      </button>
                    )}
                    {!v.is_department_master && (
                      <button
                        className="btn btn-secondary"
                        style={{ fontSize: 11, padding: '3px 8px', color: '#f87171' }}
                        onClick={() => handleDelete(v)}
                      >
                        删除
                      </button>
                    )}
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
      )}

      {/* 新建视图弹层 */}
      {showCreate && (
        <Modal title="新建视图" onClose={() => setShowCreate(false)}>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
            <LabeledInput
              label="视图名称 *"
              value={createForm.name}
              onChange={v => setCreateForm({ ...createForm, name: v })}
              placeholder="如：电钻风险排查"
              autoFocus
            />
            <LabeledInput
              label="描述（可选）"
              value={createForm.description}
              onChange={v => setCreateForm({ ...createForm, description: v })}
              placeholder="简短说明此视图用途"
            />
            <div>
              <label style={{ fontSize: 12, color: '#cbd5e1', marginBottom: 4, display: 'block' }}>类型</label>
              <select
                className="form-input"
                style={{ width: '100%', fontSize: 13, padding: '6px 8px', background: '#1e293b', border: '1px solid #334155', color: '#e2e8f0' }}
                value={createForm.view_type}
                onChange={e => setCreateForm({ ...createForm, view_type: e.target.value as 'personal' | 'shared' })}
              >
                <option value="personal">个人小表（仅自己可见）</option>
                <option value="shared">共享视图（库内成员可见）</option>
              </select>
            </div>
            <div style={{ display: 'flex', gap: 8, justifyContent: 'flex-end', marginTop: 8 }}>
              <button className="btn btn-secondary" onClick={() => setShowCreate(false)}>取消</button>
              <button
                className="btn btn-primary"
                onClick={handleCreate}
                disabled={creating || !createForm.name.trim()}
              >
                {creating ? '创建中...' : '创建并编辑'}
              </button>
            </div>
          </div>
        </Modal>
      )}

      {/* 编辑视图弹层 */}
      {editingView && (
        <ViewEditModal
          view={editingView}
          initialTab={editTab}
          onClose={handleEditorClose}
          onUpdate={updated => {
            setEditingView(updated)
            setViews(views.map(v => (v.id === updated.id ? updated : v)))
          }}
        />
      )}
    </div>
  )
}

// ============================================================
// 视图编辑弹层
// ============================================================
function ViewEditModal({
  view, initialTab, onClose, onUpdate,
}: {
  view: PatentView
  initialTab: EditTab
  onClose: () => void
  onUpdate: (updated: PatentView) => void
}) {
  const [tab, setTab] = useState<EditTab>(initialTab)
  const [working, setWorking] = useState(false)

  // 基本
  const [name, setName] = useState(view.name)
  const [description, setDescription] = useState(view.description || '')

  // 筛选
  const [filterConfig, setFilterConfig] = useState<Record<string, ViewFilterRule>>(view.filter_config || {})

  // 列
  const [columnConfig, setColumnConfig] = useState<ViewColumnConfig[]>(view.column_config || [])
  const [fields, setFields] = useState<FieldMetaWithView[]>([])

  // 排序
  const [sortBy, setSortBy] = useState<string>(view.sort_config?.sort_by || '')
  const [sortOrder, setSortOrder] = useState<'asc' | 'desc'>(view.sort_config?.sort_order || 'desc')

  // 本地字段
  const [localFields, setLocalFields] = useState<ViewLocalField[]>(view.local_fields || [])

  const isMaster = !!view.is_department_master

  // 加载字段列表（用于筛选/列/排序下拉）
  useEffect(() => {
    fieldApi.list(view.id).then(setFields).catch(e => {
      console.error('Failed to load fields:', e)
    })
  }, [view.id])

  // 加载本地字段
  const reloadLocalFields = useCallback(async () => {
    try {
      const lf = await viewApi.listLocalFields(view.id)
      setLocalFields(lf)
    } catch (e) {
      console.error('Failed to load local fields:', e)
    }
  }, [view.id])

  useEffect(() => {
    if (tab === 'localFields') {
      reloadLocalFields()
    }
  }, [tab, reloadLocalFields])

  const persistBasic = async () => {
    setWorking(true)
    try {
      const updated = await viewApi.update(view.id, {
        name: name.trim(),
        description: description.trim() || undefined,
      })
      onUpdate(updated)
      alert('基本资料已保存')
    } catch (e: any) {
      alert(e?.response?.data?.detail || '保存失败')
    } finally {
      setWorking(false)
    }
  }

  const persistFilter = async () => {
    setWorking(true)
    try {
      const updated = await viewApi.update(view.id, { filter_config: filterConfig })
      onUpdate(updated)
      alert('筛选规则已保存')
    } catch (e: any) {
      alert(e?.response?.data?.detail || '保存失败')
    } finally {
      setWorking(false)
    }
  }

  const persistColumn = async () => {
    setWorking(true)
    try {
      const updated = await viewApi.update(view.id, { column_config: columnConfig })
      onUpdate(updated)
      alert('列配置已保存')
    } catch (e: any) {
      alert(e?.response?.data?.detail || '保存失败')
    } finally {
      setWorking(false)
    }
  }

  const persistSort = async () => {
    setWorking(true)
    try {
      const cfg: ViewSortConfig = sortBy ? { sort_by: sortBy, sort_order: sortOrder } : {}
      const updated = await viewApi.update(view.id, { sort_config: cfg })
      onUpdate(updated)
      alert('排序配置已保存')
    } catch (e: any) {
      alert(e?.response?.data?.detail || '保存失败')
    } finally {
      setWorking(false)
    }
  }

  const tabs: { key: EditTab; label: string }[] = [
    { key: 'basic', label: '基本' },
    { key: 'filter', label: `筛选 (${Object.keys(filterConfig).length})` },
    { key: 'column', label: `列 (${columnConfig.length})` },
    { key: 'sort', label: '排序' },
    { key: 'localFields', label: `本地字段 (${localFields.length})` },
  ]

  return (
    <Modal
      title={`编辑视图：${view.name}${isMaster ? '（部门总表 — 筛选/列/排序只读）' : ''}`}
      onClose={onClose}
      width={900}
    >
      {/* Tab 导航 */}
      <div style={{ display: 'flex', gap: 4, borderBottom: '1px solid #334155', marginBottom: 16 }}>
        {tabs.map(t => (
          <button
            key={t.key}
            onClick={() => setTab(t.key)}
            style={{
              padding: '8px 14px',
              border: 'none',
              background: 'transparent',
              cursor: 'pointer',
              fontSize: 13,
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

      {/* Tab 内容 */}
      <div style={{ maxHeight: '60vh', overflowY: 'auto', paddingRight: 4 }}>
        {tab === 'basic' && (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
            <LabeledInput label="视图名称 *" value={name} onChange={setName} disabled={isMaster} />
            <LabeledInput
              label="描述"
              value={description}
              onChange={setDescription}
              placeholder="简短说明此视图用途"
            />
            <div style={{ fontSize: 12, color: '#64748b' }}>
              类型：{view.is_department_master ? '部门总表' : view.view_type === 'shared' ? '共享' : '个人'} ·
              库 ID：{view.database_id} · 视图 ID：{view.id}
            </div>
            <div style={{ display: 'flex', justifyContent: 'flex-end', marginTop: 8 }}>
              <button className="btn btn-primary" onClick={persistBasic} disabled={working || isMaster || !name.trim()}>
                {working ? '保存中...' : '保存'}
              </button>
            </div>
          </div>
        )}

        {tab === 'filter' && (
          <FilterEditor
            filterConfig={filterConfig}
            setFilterConfig={setFilterConfig}
            fields={fields}
            disabled={isMaster}
            onSave={persistFilter}
            working={working}
          />
        )}

        {tab === 'column' && (
          <ColumnEditor
            columnConfig={columnConfig}
            setColumnConfig={setColumnConfig}
            fields={fields}
            disabled={isMaster}
            onSave={persistColumn}
            working={working}
          />
        )}

        {tab === 'sort' && (
          <SortEditor
            sortBy={sortBy}
            setSortBy={setSortBy}
            sortOrder={sortOrder}
            setSortOrder={setSortOrder}
            fields={fields}
            disabled={isMaster}
            onSave={persistSort}
            working={working}
          />
        )}

        {tab === 'localFields' && (
          <LocalFieldsEditor
            view={view}
            localFields={localFields}
            reload={reloadLocalFields}
          />
        )}
      </div>
    </Modal>
  )
}

// ============================================================
// 筛选编辑器
// ============================================================
function FilterEditor({
  filterConfig, setFilterConfig, fields, disabled, onSave, working,
}: {
  filterConfig: Record<string, ViewFilterRule>
  setFilterConfig: (cfg: Record<string, ViewFilterRule>) => void
  fields: FieldMetaWithView[]
  disabled: boolean
  onSave: () => void
  working: boolean
}) {
  const [newFieldKey, setNewFieldKey] = useState('')
  const [newOperator, setNewOperator] = useState<'contains' | 'eq' | 'in' | 'gte' | 'lte'>('contains')
  const [newValue, setNewValue] = useState('')

  const entries = Object.entries(filterConfig)

  const addRule = () => {
    if (!newFieldKey || !newValue) return
    const rule: ViewFilterRule = { [newOperator]: newOperator === 'in' ? newValue.split(',').map(s => s.trim()).filter(Boolean) : newValue }
    setFilterConfig({ ...filterConfig, [newFieldKey]: rule })
    setNewFieldKey('')
    setNewValue('')
  }

  const removeRule = (key: string) => {
    const copy = { ...filterConfig }
    delete copy[key]
    setFilterConfig(copy)
  }

  return (
    <div>
      <div style={{ fontSize: 12, color: '#94a3b8', marginBottom: 8 }}>
        筛选规则定义视图显示哪些专利。每条规则 = 字段 + 操作符 + 值。多规则之间为 AND 关系。
      </div>

      {/* 已有规则 */}
      {entries.length === 0 ? (
        <div style={{ padding: 12, background: '#1e293b', borderRadius: 6, color: '#64748b', fontSize: 12, marginBottom: 12 }}>
          暂无筛选规则。此视图将显示库中全部专利。
        </div>
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 6, marginBottom: 12 }}>
          {entries.map(([key, rule]) => {
            const field = fields.find(f => f.key === key)
            const op = rule.contains ? 'contains' : rule.eq ? 'eq' : rule.in ? 'in' : rule.gte ? 'gte' : rule.lte ? 'lte' : '?'
            const val = rule.contains ?? rule.eq ?? (rule.in ? rule.in.join(',') : rule.gte ?? rule.lte ?? '')
            return (
              <div key={key} style={{
                display: 'flex', gap: 8, alignItems: 'center', padding: '6px 10px',
                background: '#1e293b', borderRadius: 6, fontSize: 12,
              }}>
                <span style={{ flex: 1, color: '#e2e8f0' }}>
                  {field?.name || key}
                  <span style={{ marginLeft: 6, color: '#64748b', fontFamily: 'monospace', fontSize: 10 }}>{key}</span>
                </span>
                <span style={{ padding: '1px 6px', background: '#0f172a', color: '#94a3b8', borderRadius: 4, fontSize: 10 }}>{op}</span>
                <span style={{ flex: 1, color: '#cbd5e1', fontFamily: 'monospace' }}>{String(val)}</span>
                <button
                  className="btn btn-secondary"
                  style={{ fontSize: 10, padding: '2px 6px', color: '#f87171' }}
                  onClick={() => removeRule(key)}
                  disabled={disabled}
                >
                  删除
                </button>
              </div>
            )
          })}
        </div>
      )}

      {/* 新增规则 */}
      {!disabled && (
        <div style={{
          display: 'grid', gridTemplateColumns: '2fr 1fr 2fr auto', gap: 8,
          padding: 12, background: '#0f172a', borderRadius: 6, marginBottom: 12,
        }}>
          <select
            className="form-input"
            style={{ fontSize: 12, padding: '4px 8px', background: '#1e293b', border: '1px solid #334155', color: '#e2e8f0' }}
            value={newFieldKey}
            onChange={e => setNewFieldKey(e.target.value)}
          >
            <option value="">选择字段...</option>
            {fields.map(f => (
              <option key={f.key} value={f.key}>{f.name} ({f.key})</option>
            ))}
          </select>
          <select
            className="form-input"
            style={{ fontSize: 12, padding: '4px 8px', background: '#1e293b', border: '1px solid #334155', color: '#e2e8f0' }}
            value={newOperator}
            onChange={e => setNewOperator(e.target.value as any)}
          >
            <option value="contains">contains</option>
            <option value="eq">eq (=)</option>
            <option value="in">in (逗号分隔)</option>
            <option value="gte">gte (≥)</option>
            <option value="lte">lte (≤)</option>
          </select>
          <input
            className="form-input"
            style={{ fontSize: 12, padding: '4px 8px', background: '#1e293b', border: '1px solid #334155', color: '#e2e8f0' }}
            placeholder="值（in 操作符用逗号分隔）"
            value={newValue}
            onChange={e => setNewValue(e.target.value)}
          />
          <button
            className="btn btn-primary"
            style={{ fontSize: 11, padding: '4px 10px' }}
            onClick={addRule}
            disabled={!newFieldKey || !newValue}
          >
            添加
          </button>
        </div>
      )}

      <div style={{ display: 'flex', justifyContent: 'flex-end' }}>
        <button className="btn btn-primary" onClick={onSave} disabled={working || disabled}>
          {working ? '保存中...' : '保存筛选规则'}
        </button>
      </div>
    </div>
  )
}

// ============================================================
// 列编辑器
// ============================================================
function ColumnEditor({
  columnConfig, setColumnConfig, fields, disabled, onSave, working,
}: {
  columnConfig: ViewColumnConfig[]
  setColumnConfig: (cfg: ViewColumnConfig[]) => void
  fields: FieldMetaWithView[]
  disabled: boolean
  onSave: () => void
  working: boolean
}) {
  // 当前列配置 map
  const cfgMap = new Map(columnConfig.map(c => [c.key, c]))

  // 列出所有字段，对每个字段显示当前配置
  const rows = fields.map(f => {
    const cfg = cfgMap.get(f.key) || { key: f.key }
    return { field: f, cfg }
  })

  const updateCfg = (key: string, patch: Partial<ViewColumnConfig>) => {
    const existing = cfgMap.get(key) || { key }
    const next = { ...existing, ...patch }
    const others = columnConfig.filter(c => c.key !== key)
    setColumnConfig([...others, next])
  }

  const removeFromCfg = (key: string) => {
    setColumnConfig(columnConfig.filter(c => c.key !== key))
  }

  // 提示：column_config=[] 表示显示全部字段；非空表示白名单
  const isEmpty = columnConfig.length === 0

  return (
    <div>
      <div style={{ fontSize: 12, color: '#94a3b8', marginBottom: 8 }}>
        列配置：列表为空时显示全部字段；非空时作为白名单 + 顺序 + 宽度 + 冻结。
        部门总表强制为空（显示全部字段）。
      </div>

      {disabled && (
        <div style={{ padding: 10, background: '#422006', color: '#fde68a', borderRadius: 6, marginBottom: 12, fontSize: 12 }}>
          部门总表视图的列配置强制为空（显示全部字段），不可编辑。
        </div>
      )}

      <div style={{ display: 'flex', gap: 8, marginBottom: 12 }}>
        <button
          className="btn btn-secondary"
          style={{ fontSize: 11, padding: '4px 8px' }}
          onClick={() => setColumnConfig([])}
          disabled={disabled}
          title="清空 column_config，视图将显示全部字段"
        >
          显示全部字段（清空配置）
        </button>
        <button
          className="btn btn-secondary"
          style={{ fontSize: 11, padding: '4px 8px' }}
          onClick={() => {
            // 把所有可见字段写入 column_config，默认 visible=true
            setColumnConfig(fields.map((f, i) => ({ key: f.key, visible: true, order: i, width: f.width || 150 })))
          }}
          disabled={disabled}
          title="把所有字段加入 column_config 作为起点"
        >
          全选并按默认顺序排列
        </button>
      </div>

      {isEmpty && !disabled && (
        <div style={{ padding: 10, background: '#0f172a', color: '#94a3b8', borderRadius: 6, fontSize: 12, marginBottom: 12 }}>
          当前为"显示全部字段"模式。可点击"全选并按默认顺序排列"开始自定义白名单。
        </div>
      )}

      <div style={{ maxHeight: 360, overflowY: 'auto', border: '1px solid #1e293b', borderRadius: 6 }}>
        <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 12 }}>
          <thead style={{ position: 'sticky', top: 0 }}>
            <tr style={{ background: '#1e293b', color: '#cbd5e1', textAlign: 'left' }}>
              <th style={{ padding: '6px 10px' }}>字段</th>
              <th style={{ padding: '6px 10px' }}>可见</th>
              <th style={{ padding: '6px 10px' }}>宽度</th>
              <th style={{ padding: '6px 10px' }}>顺序</th>
              <th style={{ padding: '6px 10px' }}>冻结</th>
              <th style={{ padding: '6px 10px' }}></th>
            </tr>
          </thead>
          <tbody>
            {rows.map(({ field, cfg }) => (
              <tr key={field.key} style={{ borderBottom: '1px solid #1e293b' }}>
                <td style={{ padding: '6px 10px', color: '#e2e8f0' }}>
                  {field.name}
                  <div style={{ fontSize: 10, color: '#64748b', fontFamily: 'monospace' }}>{field.key}</div>
                </td>
                <td style={{ padding: '6px 10px' }}>
                  <input
                    type="checkbox"
                    checked={cfg.visible !== false}
                    onChange={e => updateCfg(field.key, { visible: e.target.checked })}
                    disabled={disabled}
                  />
                </td>
                <td style={{ padding: '6px 10px' }}>
                  <input
                    type="number"
                    style={{ width: 70, fontSize: 11, padding: '2px 4px', background: '#1e293b', border: '1px solid #334155', color: '#e2e8f0' }}
                    value={cfg.width ?? field.width ?? 150}
                    onChange={e => updateCfg(field.key, { width: Number(e.target.value) })}
                    disabled={disabled}
                  />
                </td>
                <td style={{ padding: '6px 10px' }}>
                  <input
                    type="number"
                    style={{ width: 60, fontSize: 11, padding: '2px 4px', background: '#1e293b', border: '1px solid #334155', color: '#e2e8f0' }}
                    value={cfg.order ?? 9999}
                    onChange={e => updateCfg(field.key, { order: Number(e.target.value) })}
                    disabled={disabled}
                  />
                </td>
                <td style={{ padding: '6px 10px' }}>
                  <input
                    type="checkbox"
                    checked={!!cfg.frozen}
                    onChange={e => updateCfg(field.key, { frozen: e.target.checked })}
                    disabled={disabled}
                  />
                </td>
                <td style={{ padding: '6px 10px' }}>
                  <button
                    className="btn btn-secondary"
                    style={{ fontSize: 10, padding: '1px 6px', color: '#f87171' }}
                    onClick={() => removeFromCfg(field.key)}
                    disabled={disabled}
                  >
                    清除
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div style={{ display: 'flex', justifyContent: 'flex-end', marginTop: 12 }}>
        <button className="btn btn-primary" onClick={onSave} disabled={working || disabled}>
          {working ? '保存中...' : '保存列配置'}
        </button>
      </div>
    </div>
  )
}

// ============================================================
// 排序编辑器
// ============================================================
function SortEditor({
  sortBy, setSortBy, sortOrder, setSortOrder, fields, disabled, onSave, working,
}: {
  sortBy: string
  setSortBy: (v: string) => void
  sortOrder: 'asc' | 'desc'
  setSortOrder: (v: 'asc' | 'desc') => void
  fields: FieldMetaWithView[]
  disabled: boolean
  onSave: () => void
  working: boolean
}) {
  const sortableFields = fields.filter(f => f.sortable !== false)
  return (
    <div>
      <div style={{ fontSize: 12, color: '#94a3b8', marginBottom: 8 }}>
        视图默认排序：进入此视图时，专利列表按此字段排序。
      </div>
      <div style={{ display: 'flex', gap: 12, alignItems: 'center', marginBottom: 12 }}>
        <div>
          <label style={{ fontSize: 12, color: '#cbd5e1', marginBottom: 4, display: 'block' }}>排序字段</label>
          <select
            className="form-input"
            style={{ fontSize: 13, padding: '6px 8px', background: '#1e293b', border: '1px solid #334155', color: '#e2e8f0', minWidth: 260 }}
            value={sortBy}
            onChange={e => setSortBy(e.target.value)}
            disabled={disabled}
          >
            <option value="">（无排序 — 使用列表默认）</option>
            {sortableFields.map(f => (
              <option key={f.key} value={f.key}>{f.name} ({f.key})</option>
            ))}
          </select>
        </div>
        <div>
          <label style={{ fontSize: 12, color: '#cbd5e1', marginBottom: 4, display: 'block' }}>方向</label>
          <select
            className="form-input"
            style={{ fontSize: 13, padding: '6px 8px', background: '#1e293b', border: '1px solid #334155', color: '#e2e8f0' }}
            value={sortOrder}
            onChange={e => setSortOrder(e.target.value as 'asc' | 'desc')}
            disabled={disabled || !sortBy}
          >
            <option value="desc">降序</option>
            <option value="asc">升序</option>
          </select>
        </div>
      </div>
      <div style={{ display: 'flex', justifyContent: 'flex-end' }}>
        <button className="btn btn-primary" onClick={onSave} disabled={working || disabled}>
          {working ? '保存中...' : '保存排序配置'}
        </button>
      </div>
    </div>
  )
}

// ============================================================
// 本地字段编辑器
// ============================================================
function LocalFieldsEditor({
  view, localFields, reload,
}: {
  view: PatentView
  localFields: ViewLocalField[]
  reload: () => void
}) {
  const [showCreate, setShowCreate] = useState(false)
  const [newField, setNewField] = useState({
    name: '',
    field_type: 'text',
    options: '',
    description: '',
    default_value: '',
    is_required: false,
  })
  const [creating, setCreating] = useState(false)
  const [promoting, setPromoting] = useState<number | null>(null)

  const handleCreate = async () => {
    if (!newField.name.trim()) return
    setCreating(true)
    try {
      await viewApi.createLocalField(view.id, {
        key: 'vlf_' + Date.now().toString(36),
        name: newField.name.trim(),
        field_type: newField.field_type,
        options: newField.options ? newField.options.split(',').map(s => s.trim()).filter(Boolean) : undefined,
        description: newField.description.trim() || undefined,
        default_value: newField.default_value.trim() || undefined,
        is_required: newField.is_required,
      })
      setNewField({ name: '', field_type: 'text', options: '', description: '', default_value: '', is_required: false })
      setShowCreate(false)
      await reload()
    } catch (e: any) {
      alert(e?.response?.data?.detail || '创建失败')
    } finally {
      setCreating(false)
    }
  }

  const handleDelete = async (lf: ViewLocalField) => {
    if (!confirm(`确定删除本地字段"${lf.name}"？此操作不可恢复。`)) return
    try {
      await viewApi.deleteLocalField(view.id, lf.id)
      await reload()
    } catch (e: any) {
      alert(e?.response?.data?.detail || '删除失败')
    }
  }

  const handlePromote = async (lf: ViewLocalField) => {
    const globalName = prompt(`将本地字段"${lf.name}"提升为全局自定义字段。\n请输入全局字段名（默认使用当前名）:`, lf.name)
    if (!globalName) return
    setPromoting(lf.id)
    try {
      const result = await viewApi.promoteLocalField(view.id, lf.id, { global_name: globalName })
      alert(`提升成功！\n全局字段 key: ${result.global_field_key}\n全局字段名: ${result.global_field_name}\n源视图: ${result.source_view_name}`)
      await reload()
    } catch (e: any) {
      alert(e?.response?.data?.detail || '提升失败')
    } finally {
      setPromoting(null)
    }
  }

  return (
    <div>
      <div style={{ fontSize: 12, color: '#94a3b8', marginBottom: 8 }}>
        视图本地字段（vlf_ 前缀）仅存在于当前视图，不污染全局字段表。
        可将常用本地字段"提升"为全局自定义字段，所有视图共享。
      </div>

      <div style={{ marginBottom: 12 }}>
        <button className="btn btn-primary" onClick={() => setShowCreate(true)} style={{ fontSize: 12, padding: '4px 10px' }}>
          + 新建本地字段
        </button>
      </div>

      {showCreate && (
        <div style={{
          padding: 12, background: '#0f172a', borderRadius: 6, marginBottom: 12,
          display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 8, fontSize: 12,
        }}>
          <LabeledInput label="字段名 *" value={newField.name} onChange={v => setNewField({ ...newField, name: v })} />
          <div>
            <label style={{ fontSize: 12, color: '#cbd5e1', marginBottom: 4, display: 'block' }}>类型</label>
            <select
              className="form-input"
              style={{ width: '100%', fontSize: 12, padding: '4px 8px', background: '#1e293b', border: '1px solid #334155', color: '#e2e8f0' }}
              value={newField.field_type}
              onChange={e => setNewField({ ...newField, field_type: e.target.value })}
            >
              <option value="text">文本</option>
              <option value="longtext">长文本</option>
              <option value="number">数字</option>
              <option value="date">日期</option>
              <option value="select">单选</option>
              <option value="boolean">布尔</option>
            </select>
          </div>
          <LabeledInput label="选项（select 类型，逗号分隔）" value={newField.options} onChange={v => setNewField({ ...newField, options: v })} />
          <LabeledInput label="描述" value={newField.description} onChange={v => setNewField({ ...newField, description: v })} />
          <LabeledInput label="默认值" value={newField.default_value} onChange={v => setNewField({ ...newField, default_value: v })} />
          <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
            <input
              type="checkbox"
              checked={newField.is_required}
              onChange={e => setNewField({ ...newField, is_required: e.target.checked })}
            />
            <label style={{ fontSize: 12, color: '#cbd5e1' }}>必填</label>
          </div>
          <div style={{ gridColumn: '1 / -1', display: 'flex', gap: 8, justifyContent: 'flex-end' }}>
            <button className="btn btn-secondary" onClick={() => setShowCreate(false)}>取消</button>
            <button className="btn btn-primary" onClick={handleCreate} disabled={creating || !newField.name.trim()}>
              {creating ? '创建中...' : '创建'}
            </button>
          </div>
        </div>
      )}

      {localFields.length === 0 ? (
        <div style={{ padding: 12, background: '#1e293b', borderRadius: 6, color: '#64748b', fontSize: 12 }}>
          暂无本地字段。可在导入此视图时让未知列自动创建为 vlf_，或点击"+ 新建本地字段"手动添加。
        </div>
      ) : (
        <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 12 }}>
          <thead>
            <tr style={{ background: '#1e293b', color: '#cbd5e1', textAlign: 'left' }}>
              <th style={{ padding: '6px 10px' }}>字段名</th>
              <th style={{ padding: '6px 10px' }}>Key</th>
              <th style={{ padding: '6px 10px' }}>类型</th>
              <th style={{ padding: '6px 10px' }}>必填</th>
              <th style={{ padding: '6px 10px' }}>状态</th>
              <th style={{ padding: '6px 10px' }}>操作</th>
            </tr>
          </thead>
          <tbody>
            {localFields.map(lf => (
              <tr key={lf.id} style={{ borderBottom: '1px solid #1e293b' }}>
                <td style={{ padding: '6px 10px', color: '#e2e8f0' }}>
                  {lf.name}
                  {lf.description && <div style={{ fontSize: 10, color: '#64748b' }}>{lf.description}</div>}
                </td>
                <td style={{ padding: '6px 10px', color: '#64748b', fontFamily: 'monospace', fontSize: 10 }}>{lf.key}</td>
                <td style={{ padding: '6px 10px', color: '#cbd5e1' }}>{lf.field_type}</td>
                <td style={{ padding: '6px 10px' }}>
                  {lf.is_required ? <span style={{ color: '#fbbf24' }}>是</span> : <span style={{ color: '#64748b' }}>否</span>}
                </td>
                <td style={{ padding: '6px 10px' }}>
                  {lf.is_promoted ? (
                    <span style={{ color: '#10b981' }}>
                      已提升
                      {lf.promoted_field_key && (
                        <span style={{ marginLeft: 6, fontFamily: 'monospace', fontSize: 10, color: '#64748b' }}>
                          → {lf.promoted_field_key}
                        </span>
                      )}
                    </span>
                  ) : (
                    <span style={{ color: '#94a3b8' }}>本地</span>
                  )}
                </td>
                <td style={{ padding: '6px 10px', whiteSpace: 'nowrap' }}>
                  {!lf.is_promoted && (
                    <button
                      className="btn btn-secondary"
                      style={{ fontSize: 10, padding: '2px 6px', marginRight: 4, color: '#a78bfa' }}
                      onClick={() => handlePromote(lf)}
                      disabled={promoting === lf.id}
                    >
                      {promoting === lf.id ? '提升中...' : '↑ 提升'}
                    </button>
                  )}
                  <button
                    className="btn btn-secondary"
                    style={{ fontSize: 10, padding: '2px 6px', color: '#f87171' }}
                    onClick={() => handleDelete(lf)}
                  >
                    删除
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  )
}

// ============================================================
// 通用组件
// ============================================================
function Modal({ title, children, onClose, width = 600 }: {
  title: string
  children: React.ReactNode
  onClose: () => void
  width?: number
}) {
  return (
    <div
      style={{
        position: 'fixed', top: 0, left: 0, right: 0, bottom: 0,
        background: 'rgba(0, 0, 0, 0.7)', display: 'flex',
        alignItems: 'center', justifyContent: 'center', zIndex: 1000,
      }}
      onClick={onClose}
    >
      <div
        style={{
          background: '#0f172a', border: '1px solid #334155', borderRadius: 8,
          padding: 20, width, maxWidth: '90vw', maxHeight: '85vh', overflow: 'hidden',
          display: 'flex', flexDirection: 'column',
        }}
        onClick={e => e.stopPropagation()}
      >
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 12 }}>
          <h3 style={{ margin: 0, fontSize: 16, color: '#f1f5f9' }}>{title}</h3>
          <button
            onClick={onClose}
            style={{
              background: 'transparent', border: 'none', color: '#94a3b8',
              cursor: 'pointer', fontSize: 18, padding: '0 4px',
            }}
          >
            ×
          </button>
        </div>
        {children}
      </div>
    </div>
  )
}

function LabeledInput({
  label, value, onChange, placeholder, autoFocus, disabled,
}: {
  label: string
  value: string
  onChange: (v: string) => void
  placeholder?: string
  autoFocus?: boolean
  disabled?: boolean
}) {
  return (
    <div>
      <label style={{ fontSize: 12, color: '#cbd5e1', marginBottom: 4, display: 'block' }}>{label}</label>
      <input
        className="form-input"
        style={{
          width: '100%', fontSize: 13, padding: '6px 8px',
          background: '#1e293b', border: '1px solid #334155', color: '#e2e8f0',
          opacity: disabled ? 0.5 : 1,
        }}
        value={value}
        onChange={e => onChange(e.target.value)}
        placeholder={placeholder}
        autoFocus={autoFocus}
        disabled={disabled}
      />
    </div>
  )
}
