import { useCallback, useEffect, useMemo, useState } from 'react'
import { dashboardService as dashboardApi, fieldService as fieldApi } from '../../services'
import { useAppStore } from '../../store'
import type { Dashboard, DashboardCard, DashboardCardType, DashboardData, FieldMeta, JsonObject, JsonValue } from '../../types'
import { getErrorMessage } from '../../lib/errors'

const CARD_TYPES: Array<{ value: DashboardCardType; label: string }> = [
  { value: 'metric', label: '指标' },
  { value: 'bar', label: '柱状分布' },
  { value: 'pie', label: '分类占比' },
  { value: 'donut', label: '环形占比' },
  { value: 'line', label: '趋势' },
  { value: 'stacked', label: '堆叠对比' },
  { value: 'heatmap', label: '交叉热力图' },
  { value: 'progress', label: '目标进度' },
  { value: 'table', label: '明细排行' },
]

const AGGREGATIONS = [
  { value: 'count', label: '计数' },
  { value: 'sum', label: '求和' },
  { value: 'avg', label: '平均值' },
  { value: 'min', label: '最小值' },
  { value: 'max', label: '最大值' },
]

const ANALYSIS_PRESETS: Array<{ key: string; name: string; description: string; cards: Array<{ type: DashboardCardType; title: string; config: JsonObject }> }> = [
  { key: 'portfolio', name: '专利组合总览', description: '总量、法律状态、类型和申请趋势', cards: [
    { type: 'metric', title: '专利总量', config: { field: 'id', aggregation: 'count' } },
    { type: 'donut', title: '法律状态占比', config: { field: 'id', group_by: 'legal_status', aggregation: 'count' } },
    { type: 'bar', title: '专利类型分布', config: { field: 'id', group_by: 'patent_type', aggregation: 'count' } },
    { type: 'line', title: '申请趋势', config: { field: 'id', date_field: 'filing_date', interval: 'year', aggregation: 'count' } },
  ] },
  { key: 'technology', name: '技术布局分析', description: 'IPC、业务分类与技术类型的交叉关系', cards: [
    { type: 'bar', title: 'IPC 主分类排行', config: { field: 'id', group_by: 'ipc_main', aggregation: 'count' } },
    { type: 'heatmap', title: '法律状态 × 专利类型', config: { row_field: 'legal_status', col_field: 'patent_type', aggregation: 'count' } },
    { type: 'stacked', title: '分类 × 专利类型', config: { group_by: 'category', subgroup_by: 'patent_type', aggregation: 'count' } },
  ] },
  { key: 'competition', name: '申请人竞争分析', description: '申请人排行、国别和年度申请变化', cards: [
    { type: 'bar', title: '申请人排行', config: { field: 'id', group_by: 'applicant', aggregation: 'count' } },
    { type: 'donut', title: '国家/地区分布', config: { field: 'id', group_by: 'country', aggregation: 'count' } },
    { type: 'line', title: '申请人年度趋势', config: { field: 'id', date_field: 'filing_date', interval: 'year', aggregation: 'count' } },
  ] },
]

function asObject(value: JsonValue | undefined): JsonObject {
  return typeof value === 'object' && value !== null && !Array.isArray(value) ? value as JsonObject : {}
}

function asString(value: JsonValue | undefined, fallback = ''): string {
  return typeof value === 'string' || typeof value === 'number' || typeof value === 'boolean' ? String(value) : fallback
}

function asNumber(value: JsonValue | undefined, fallback = 0): number {
  return typeof value === 'number' ? value : Number(value) || fallback
}

function itemsFrom(card: DashboardCard): Array<{ label: string; value: number }> {
  const raw = card.data?.items
  if (!Array.isArray(raw)) return []
  return raw.map(item => {
    const record = asObject(item)
    return { label: asString(record.label, '未设置'), value: asNumber(record.value) }
  })
}

function CardDataView({ card }: { card: DashboardCard }) {
  const data = card.data || {}
  if (card.type === 'metric') {
    return <div className="dashboard-metric-value">{asString(data.value, '0')}</div>
  }
  if (card.type === 'progress') {
    const percentage = Math.max(0, Math.min(100, asNumber(data.percentage)))
    return (
      <div>
        <div className="dashboard-progress-label">{asString(data.current, '0')} / {asString(data.total, '0')} <strong>{percentage}%</strong></div>
        <div className="dashboard-progress-track"><div className="dashboard-progress-fill" style={{ width: `${percentage}%` }} /></div>
      </div>
    )
  }
  if (card.type === 'line') {
    const labels = Array.isArray(data.labels) ? data.labels : []
    const values = Array.isArray(data.values) ? data.values : []
    const max = Math.max(1, ...values.map(value => asNumber(value)))
    return (
      <div className="dashboard-line-chart">
        {labels.map((label, index) => (
          <div className="dashboard-line-row" key={`${String(label)}-${index}`}>
            <span>{String(label)}</span><div className="dashboard-bar-track"><div className="dashboard-bar-fill" style={{ width: `${asNumber(values[index]) / max * 100}%` }} /></div><b>{asString(values[index], '0')}</b>
          </div>
        ))}
        {labels.length === 0 && <span className="dashboard-empty">暂无趋势数据</span>}
      </div>
    )
  }
  if (card.type === 'donut') {
    const items = itemsFrom(card)
    const total = items.reduce((sum, item) => sum + item.value, 0) || 1
    const colors = ['#0f766e', '#2563eb', '#d97706', '#9333ea', '#dc2626', '#0891b2']
    const gradient = items.reduce<{ stops: string[]; offset: number }>((acc, item, index) => {
      const end = acc.offset + (item.value / total) * 100
      return {
        stops: [...acc.stops, `${colors[index % colors.length]} ${acc.offset}% ${end}%`],
        offset: end,
      }
    }, { stops: [], offset: 0 }).stops.join(', ')
    return <div className="dashboard-donut-layout"><div className="dashboard-donut" style={{ background: `conic-gradient(${gradient || '#e2e8f0 0 100%'})` }}><div>{items.reduce((sum, item) => sum + item.value, 0)}</div></div><div className="dashboard-donut-legend">{items.map((item, index) => <div key={item.label}><span style={{ background: colors[index % colors.length] }} /> <span title={item.label}>{item.label}</span><b>{item.value}</b></div>)}</div></div>
  }
  if (card.type === 'heatmap') {
    const columns = Array.isArray(data.columns) ? data.columns.map(String) : []
    const rows = Array.isArray(data.rows) ? data.rows.map(item => asObject(item)) : []
    const max = Math.max(1, ...rows.flatMap(row => Array.isArray(row.values) ? row.values.map(value => asNumber(value)) : []))
    return <div className="dashboard-heatmap-wrap"><table className="dashboard-heatmap"><thead><tr><th>维度</th>{columns.map(column => <th key={column}>{column}</th>)}</tr></thead><tbody>{rows.map(row => <tr key={asString(row.label)}><th>{asString(row.label)}</th>{(Array.isArray(row.values) ? row.values : []).map((value, index) => <td key={index} style={{ background: `rgba(15, 118, 110, ${Math.max(.08, asNumber(value) / max * .82)})` }}>{asNumber(value)}</td>)}</tr>)}</tbody></table></div>
  }
  if (card.type === 'stacked') {
    const rows = Array.isArray(data.items) ? data.items.map(item => asObject(item)) : []
    const segmentLabels = Array.from(new Set(rows.flatMap(row => Array.isArray(row.segments) ? row.segments.map(segment => asString(asObject(segment).label)) : [])))
    const colors = ['#0f766e', '#2563eb', '#d97706', '#9333ea', '#dc2626', '#0891b2']
    return <div className="dashboard-stacked-list">{rows.map(row => { const segments = Array.isArray(row.segments) ? row.segments.map(segment => asObject(segment)) : []; const total = segments.reduce((sum, segment) => sum + asNumber(segment.value), 0) || 1; return <div className="dashboard-stacked-row" key={asString(row.label)}><span title={asString(row.label)}>{asString(row.label)}</span><div className="dashboard-stacked-track">{segments.map(segment => <i key={asString(segment.label)} title={`${asString(segment.label)} ${asNumber(segment.value)}`} style={{ width: `${asNumber(segment.value) / total * 100}%`, background: colors[Math.max(0, segmentLabels.indexOf(asString(segment.label))) % colors.length] }} />)}</div><b>{total}</b></div>})}</div>
  }
  const items = itemsFrom(card)
  if (card.type === 'table') {
    return (
      <table className="dashboard-mini-table"><tbody>
        {items.map(item => <tr key={item.label}><td>{item.label}</td><td>{item.value}</td></tr>)}
      </tbody></table>
    )
  }
  const max = Math.max(1, ...items.map(item => item.value))
  return (
    <div className="dashboard-bars">
      {items.map(item => (
        <div className="dashboard-bar-row" key={item.label}>
          <span title={item.label}>{item.label}</span><div className="dashboard-bar-track"><div className="dashboard-bar-fill" style={{ width: `${item.value / max * 100}%` }} /></div><b>{item.value}</b>
        </div>
      ))}
      {items.length === 0 && <span className="dashboard-empty">暂无分布数据</span>}
    </div>
  )
}

export default function DashboardPage({ embedded = false }: { embedded?: boolean }) {
  const { currentDatabaseId, currentViewId } = useAppStore()
  const [dashboards, setDashboards] = useState<Dashboard[]>([])
  const [selectedId, setSelectedId] = useState<number | null>(null)
  const [data, setData] = useState<DashboardData | null>(null)
  const [fields, setFields] = useState<FieldMeta[]>([])
  const [scope, setScope] = useState<'all' | 'view'>('all')
  const [showCardForm, setShowCardForm] = useState(false)
  const [newName, setNewName] = useState('专利总览')
  const [cardType, setCardType] = useState<DashboardCardType>('metric')
  const [cardTitle, setCardTitle] = useState('专利数量')
  const [cardField, setCardField] = useState('id')
  const [groupField, setGroupField] = useState('legal_status')
  const [subgroupField, setSubgroupField] = useState('patent_type')
  const [heatmapRowField, setHeatmapRowField] = useState('legal_status')
  const [heatmapColField, setHeatmapColField] = useState('patent_type')
  const [dateField, setDateField] = useState('filing_date')
  const [aggregation, setAggregation] = useState('count')
  const [interval, setInterval] = useState('year')
  const [targetValue, setTargetValue] = useState('granted')
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)

  const selectedDashboard = useMemo(() => dashboards.find(item => item.id === selectedId) || null, [dashboards, selectedId])
  const loadDashboards = useCallback(async () => {
    if (currentDatabaseId === null) return
    setLoading(true)
    setError('')
    try {
      const [loaded, loadedFields] = await Promise.all([dashboardApi.list(currentDatabaseId), fieldApi.list()])
      setDashboards(loaded)
      setFields(loadedFields)
      setSelectedId(current => current && loaded.some(item => item.id === current) ? current : loaded[0]?.id ?? null)
    } catch (loadError: unknown) {
      setError(getErrorMessage(loadError, '仪表盘加载失败'))
    } finally {
      setLoading(false)
    }
  }, [currentDatabaseId])

  // Synchronize the workspace with the selected database.
  // eslint-disable-next-line react-hooks/set-state-in-effect
  useEffect(() => { void loadDashboards() }, [loadDashboards])

  const loadData = useCallback(async () => {
    if (!selectedId) { setData(null); return }
    try {
      setData(await dashboardApi.data(selectedId, scope === 'view' ? currentViewId : null))
    } catch (loadError: unknown) {
      setError(getErrorMessage(loadError, '仪表盘数据加载失败'))
    }
  }, [currentViewId, scope, selectedId])

  // Card data follows the active dashboard and view scope.
  // eslint-disable-next-line react-hooks/set-state-in-effect
  useEffect(() => { void loadData() }, [loadData])

  const createDashboard = async () => {
    if (!currentDatabaseId || !newName.trim()) return
    try {
      const created = await dashboardApi.create({ database_id: currentDatabaseId, name: newName.trim(), layout: [] })
      await loadDashboards()
      setSelectedId(created.id)
    } catch (createError: unknown) {
      setError(getErrorMessage(createError, '创建仪表盘失败'))
    }
  }

  const addCard = async () => {
    if (!selectedDashboard) return
    const config: JsonObject = { field: cardField, aggregation }
    if (cardType === 'bar' || cardType === 'pie' || cardType === 'donut' || cardType === 'table') config.group_by = groupField
    if (cardType === 'stacked') { config.group_by = groupField; config.subgroup_by = subgroupField }
    if (cardType === 'heatmap') { config.row_field = heatmapRowField; config.col_field = heatmapColField }
    if (cardType === 'line') { config.date_field = dateField; config.interval = interval }
    if (cardType === 'progress') { config.field = cardField; config.value = targetValue }
    try {
      await dashboardApi.addCard(selectedDashboard.id, {
        type: cardType,
        title: cardTitle.trim() || '未命名卡片',
        config,
        position: { x: 0, y: 0, w: 4, h: 2 },
      })
      setShowCardForm(false)
      await loadDashboards()
      await loadData()
    } catch (createError: unknown) {
      setError(getErrorMessage(createError, '添加卡片失败'))
    }
  }

  const createPreset = async (preset: typeof ANALYSIS_PRESETS[number]) => {
    if (!currentDatabaseId) return
    setLoading(true)
    try {
      const created = await dashboardApi.create({
        database_id: currentDatabaseId,
        name: preset.name,
        description: preset.description,
        layout: preset.cards.map((card, index) => ({ id: `preset_${preset.key}_${index}`, ...card, position: { x: 0, y: index * 2, w: 4, h: 2 } })),
      })
      await loadDashboards()
      setSelectedId(created.id)
    } catch (createError: unknown) {
      setError(getErrorMessage(createError, '创建分析模板失败'))
    } finally {
      setLoading(false)
    }
  }

  const removeCard = async (cardId: string) => {
    if (!selectedDashboard || !window.confirm('确定移除这个卡片吗？')) return
    try {
      await dashboardApi.removeCard(selectedDashboard.id, cardId)
      await loadDashboards()
      await loadData()
    } catch (removeError: unknown) {
      setError(getErrorMessage(removeError, '移除卡片失败'))
    }
  }

  const removeDashboard = async () => {
    if (!selectedDashboard || !window.confirm(`确定删除仪表盘“${selectedDashboard.name}”吗？`)) return
    try {
      await dashboardApi.remove(selectedDashboard.id)
      await loadDashboards()
      setData(null)
    } catch (removeError: unknown) {
      setError(getErrorMessage(removeError, '删除仪表盘失败'))
    }
  }

  return (
    <div className={embedded ? 'dashboard-page dashboard-page-embedded' : 'page-container dashboard-page'}>
      {!embedded && <div className="page-header dashboard-header">
        <div><h2 className="page-title">可配置仪表盘</h2><p className="page-subtitle">用指标、分布和趋势快速掌握当前专利库。</p></div>
        <div className="dashboard-header-actions">
          <select className="form-input" value={scope} onChange={event => setScope(event.target.value as 'all' | 'view')}><option value="all">当前库全部记录</option><option value="view" disabled={!currentViewId}>当前视图记录</option></select>
          <button className="btn btn-primary" disabled={!currentDatabaseId} onClick={() => void createDashboard()}>新建仪表盘</button>
        </div>
      </div>}
      {embedded && <div className="dashboard-embedded-scope">
        <select className="form-input" value={scope} onChange={event => setScope(event.target.value as 'all' | 'view')}>
          <option value="all">当前库全部记录</option><option value="view" disabled={!currentViewId}>当前视图记录</option>
        </select>
        <button className="btn btn-primary" disabled={!currentDatabaseId} onClick={() => void createDashboard()}>新建分析方案</button>
      </div>}
      {error && <div className="error-message">{error}</div>}
      <section className="analysis-template-panel">
        <div><h3>从常见分析开始</h3><p>模板已经选好图表和专利字段，你只需要切换到当前库或当前视图即可查看。</p></div>
        <div className="analysis-template-grid">{ANALYSIS_PRESETS.map(preset => <button type="button" key={preset.key} className="analysis-template-card" onClick={() => void createPreset(preset)}><strong>{preset.name}</strong><span>{preset.description}</span><small>{preset.cards.length} 张图表</small></button>)}</div>
      </section>
      <div className="dashboard-toolbar">
        <select className="form-input" value={selectedId ?? ''} onChange={event => setSelectedId(Number(event.target.value) || null)}>
          <option value="">选择仪表盘</option>{dashboards.map(item => <option key={item.id} value={item.id}>{item.name}</option>)}
        </select>
        <input className="form-input" value={newName} onChange={event => setNewName(event.target.value)} placeholder="新仪表盘名称" />
        {selectedDashboard && <><button className="btn btn-secondary" onClick={() => setShowCardForm(value => !value)}>{showCardForm ? '收起配置' : '添加卡片'}</button><button className="btn btn-danger" onClick={() => void removeDashboard()}>删除仪表盘</button></>}
        {loading && <span className="muted-text">加载中...</span>}
      </div>
      {showCardForm && selectedDashboard && (
        <div className="dashboard-card-form">
          <label>卡片类型<select className="form-input" value={cardType} onChange={event => setCardType(event.target.value as DashboardCardType)}>{CARD_TYPES.map(item => <option key={item.value} value={item.value}>{item.label}</option>)}</select></label>
          <label>标题<input className="form-input" value={cardTitle} onChange={event => setCardTitle(event.target.value)} /></label>
          <label>统计字段<select className="form-input" value={cardField} onChange={event => setCardField(event.target.value)}><option value="id">记录 ID</option>{fields.filter(field => field.field_type !== 'formula').map(field => <option key={field.key} value={field.key}>{field.name}</option>)}</select></label>
          {(cardType === 'bar' || cardType === 'pie' || cardType === 'donut' || cardType === 'table' || cardType === 'stacked') && <label>分组字段<select className="form-input" value={groupField} onChange={event => setGroupField(event.target.value)}>{fields.map(field => <option key={field.key} value={field.key}>{field.name}</option>)}</select></label>}
          {cardType === 'stacked' && <label>对比分组<select className="form-input" value={subgroupField} onChange={event => setSubgroupField(event.target.value)}>{fields.map(field => <option key={field.key} value={field.key}>{field.name}</option>)}</select></label>}
          {cardType === 'heatmap' && <><label>行维度<select className="form-input" value={heatmapRowField} onChange={event => setHeatmapRowField(event.target.value)}>{fields.map(field => <option key={field.key} value={field.key}>{field.name}</option>)}</select></label><label>列维度<select className="form-input" value={heatmapColField} onChange={event => setHeatmapColField(event.target.value)}>{fields.map(field => <option key={field.key} value={field.key}>{field.name}</option>)}</select></label></>}
          {cardType === 'line' && <><label>日期字段<select className="form-input" value={dateField} onChange={event => setDateField(event.target.value)}>{fields.filter(field => field.field_type === 'date').map(field => <option key={field.key} value={field.key}>{field.name}</option>)}</select></label><label>粒度<select className="form-input" value={interval} onChange={event => setInterval(event.target.value)}><option value="year">年</option><option value="month">月</option></select></label></>}
          {cardType === 'progress' && <label>目标值<input className="form-input" value={targetValue} onChange={event => setTargetValue(event.target.value)} placeholder="例如 granted" /></label>}
          {(cardType === 'metric' || cardType === 'progress') && <label>聚合<select className="form-input" value={aggregation} onChange={event => setAggregation(event.target.value)}>{AGGREGATIONS.map(item => <option key={item.value} value={item.value}>{item.label}</option>)}</select></label>}
          <button className="btn btn-primary" onClick={() => void addCard()}>保存卡片</button>
        </div>
      )}
      {!selectedDashboard && <div className="empty-state">当前库还没有仪表盘，输入名称后点击“新建仪表盘”。</div>}
      {selectedDashboard && data && <>
        <div className="dashboard-summary"><strong>{data.total}</strong><span>条记录参与统计</span></div>
        <div className="dashboard-grid">
          {data.cards.map(card => <section className="dashboard-card" key={card.id}><div className="dashboard-card-header"><h3>{card.title}</h3><button className="dashboard-remove" title="移除卡片" onClick={() => void removeCard(card.id)}>×</button></div><CardDataView card={card} /></section>)}
          {data.cards.length === 0 && <div className="empty-state dashboard-empty-grid">点击“添加卡片”开始配置。</div>}
        </div>
      </>}
    </div>
  )
}
