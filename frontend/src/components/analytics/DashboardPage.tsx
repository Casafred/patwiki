import { useCallback, useEffect, useMemo, useState } from 'react'
import { dashboardApi, fieldApi } from '../../api'
import { useAppStore } from '../../store'
import type { Dashboard, DashboardCard, DashboardCardType, DashboardData, FieldMeta, JsonObject, JsonValue } from '../../types'
import { getErrorMessage } from '../../lib/errors'

const CARD_TYPES: Array<{ value: DashboardCardType; label: string }> = [
  { value: 'metric', label: '指标' },
  { value: 'bar', label: '柱状分布' },
  { value: 'pie', label: '分类占比' },
  { value: 'line', label: '趋势' },
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

export default function DashboardPage() {
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
    if (cardType === 'bar' || cardType === 'pie' || cardType === 'table') config.group_by = groupField
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
    <div className="page-container dashboard-page">
      <div className="page-header dashboard-header">
        <div><h2 className="page-title">可配置仪表盘</h2><p className="page-subtitle">用指标、分布和趋势快速掌握当前专利库。</p></div>
        <div className="dashboard-header-actions">
          <select className="form-input" value={scope} onChange={event => setScope(event.target.value as 'all' | 'view')}><option value="all">当前库全部记录</option><option value="view" disabled={!currentViewId}>当前视图记录</option></select>
          <button className="btn btn-primary" disabled={!currentDatabaseId} onClick={() => void createDashboard()}>新建仪表盘</button>
        </div>
      </div>
      {error && <div className="error-message">{error}</div>}
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
          {(cardType === 'bar' || cardType === 'pie' || cardType === 'table') && <label>分组字段<select className="form-input" value={groupField} onChange={event => setGroupField(event.target.value)}>{fields.map(field => <option key={field.key} value={field.key}>{field.name}</option>)}</select></label>}
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
