import { useCallback, useEffect, useMemo, useState, type CSSProperties, type MouseEvent as ReactMouseEvent } from 'react'
import { viewApi } from '../../api'
import type { FieldMeta, GanttConfig, GanttItem, GanttResponse, PatentView } from '../../types'
import { getErrorMessage } from '../../lib/errors'

interface GanttViewProps {
  view: PatentView
  fields: FieldMeta[]
  onPatentClick: (id: number) => void
  onViewChange: (view: PatentView) => void
  onTotalChange: (total: number) => void
}

const SCALE_WIDTH: Record<GanttConfig['time_scale'], number> = { day: 18, week: 7, month: 3, quarter: 1.5, year: 0.7 }

function toDate(value: string): Date {
  return new Date(`${value.slice(0, 10)}T00:00:00`)
}

function addDays(value: Date, days: number): Date {
  const next = new Date(value)
  next.setDate(next.getDate() + days)
  return next
}

function isoDate(value: Date): string {
  return `${value.getFullYear()}-${String(value.getMonth() + 1).padStart(2, '0')}-${String(value.getDate()).padStart(2, '0')}`
}

function daysBetween(start: Date, end: Date): number {
  return Math.max(1, Math.round((end.getTime() - start.getTime()) / 86400000))
}

function getInitialConfig(view: PatentView): GanttConfig {
  const configured = (view.gantt_config || {}) as Partial<GanttConfig>
  return {
    start_field: configured.start_field || 'filing_date',
    end_field: configured.end_field || 'grant_date',
    title_field: configured.title_field || 'title',
    group_by_field: configured.group_by_field || '',
    time_scale: configured.time_scale || 'month',
    bar_color_field: configured.bar_color_field || 'risk_level',
    bar_color_map: configured.bar_color_map || {},
  }
}

function Timeline({ data, config, onMove }: { data: GanttResponse; config: GanttConfig; onMove: (item: GanttItem, deltaDays: number) => Promise<void> }) {
  const rangeStart = useMemo(
    () => data.time_range.start ? addDays(toDate(data.time_range.start), -14) : new Date(),
    [data.time_range.start],
  )
  const rangeEnd = useMemo(
    () => data.time_range.end ? addDays(toDate(data.time_range.end), 14) : addDays(rangeStart, 30),
    [data.time_range.end, rangeStart],
  )
  const totalDays = daysBetween(rangeStart, rangeEnd)
  const pixelsPerDay = SCALE_WIDTH[config.time_scale]
  const timelineWidth = Math.max(900, totalDays * pixelsPerDay)
  const [dragging, setDragging] = useState<{ item: GanttItem; startX: number; deltaDays: number } | null>(null)

  const ticks = useMemo(() => {
    const result: Date[] = []
    const step = config.time_scale === 'day' ? 1 : config.time_scale === 'week' ? 7 : config.time_scale === 'quarter' ? 90 : config.time_scale === 'year' ? 365 : 30
    for (let current = rangeStart; current <= rangeEnd && result.length < 120; current = addDays(current, step)) result.push(current)
    return result
  }, [config.time_scale, rangeEnd, rangeStart])

  const beginDrag = (event: ReactMouseEvent, item: GanttItem) => {
    event.preventDefault()
    const startX = event.clientX
    const handleMove = (moveEvent: globalThis.MouseEvent) => {
      setDragging({ item, startX, deltaDays: Math.round((moveEvent.clientX - startX) / pixelsPerDay) })
    }
    const handleUp = () => {
      window.removeEventListener('mousemove', handleMove)
      window.removeEventListener('mouseup', handleUp)
      setDragging(current => {
        if (current && current.deltaDays !== 0) void onMove(current.item, current.deltaDays)
        return null
      })
    }
    window.addEventListener('mousemove', handleMove)
    window.addEventListener('mouseup', handleUp)
    setDragging({ item, startX, deltaDays: 0 })
  }

  const left = (value: string) => (daysBetween(rangeStart, toDate(value)) / totalDays) * 100
  const width = (item: GanttItem) => Math.max(1.2, (daysBetween(toDate(item.start), toDate(item.end)) / totalDays) * 100)

  return (
    <div className="gantt-scroll" style={{ '--gantt-width': `${timelineWidth}px` } as CSSProperties}>
      <div className="gantt-header-row">
        <div className="gantt-label-cell">任务</div>
        <div className="gantt-timeline-header" style={{ width: timelineWidth }}>
          {ticks.map(tick => <span key={tick.toISOString()} style={{ left: `${(daysBetween(rangeStart, tick) / totalDays) * 100}%` }}>{tick.toLocaleDateString('zh-CN', { month: 'short', day: 'numeric' })}</span>)}
        </div>
      </div>
      {data.groups.map(group => (
        <section className="gantt-group" key={String(group.key)}>
          <header>{group.label}<span>{group.items.length}</span></header>
          {group.items.map(item => {
            const activeDrag = dragging?.item.id === item.id ? dragging : null
            const offset = activeDrag?.deltaDays ? (activeDrag.deltaDays / totalDays) * 100 : 0
            return (
              <div className="gantt-row" key={item.id}>
                <button type="button" className="gantt-label-cell" onClick={() => onMove(item, 0).catch(() => undefined)}>{item.title}</button>
                <div className="gantt-timeline" style={{ width: timelineWidth }}>
                  <div className="gantt-bar" style={{ left: `${left(item.start) + offset}%`, width: `${width(item)}%`, background: item.color }} onMouseDown={event => beginDrag(event, item)} title={`${item.start} - ${item.end}`}>
                    {activeDrag?.deltaDays ? `${activeDrag.deltaDays > 0 ? '+' : ''}${activeDrag.deltaDays} 天` : item.title}
                  </div>
                </div>
              </div>
            )
          })}
        </section>
      ))}
    </div>
  )
}

export default function GanttView({ view, fields, onPatentClick, onViewChange, onTotalChange }: GanttViewProps) {
  const [config, setConfig] = useState<GanttConfig>(() => getInitialConfig(view))
  const [data, setData] = useState<GanttResponse | null>(null)
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const result = await viewApi.gantt(view.id, { page_size: 500 })
      setData(result)
      setConfig(result.config)
      onTotalChange(result.total)
      setError(null)
    } catch (requestError: unknown) {
      setError(getErrorMessage(requestError, '甘特数据加载失败'))
    } finally {
      setLoading(false)
    }
  }, [onTotalChange, view.id])

  useEffect(() => {
    // Load the selected gantt view when its id changes.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    void load()
  }, [load])

  const updateConfig = async (patch: Partial<GanttConfig>) => {
    const next = { ...config, ...patch }
    setSaving(true)
    try {
      const updated = await viewApi.update(view.id, { gantt_config: next })
      setConfig(next)
      onViewChange(updated)
      await load()
    } catch (requestError: unknown) {
      setError(getErrorMessage(requestError, '甘特配置保存失败'))
    } finally {
      setSaving(false)
    }
  }

  const moveItem = async (item: GanttItem, deltaDays: number) => {
    if (deltaDays === 0) {
      onPatentClick(item.id)
      return
    }
    setSaving(true)
    try {
      await viewApi.updateGanttDates(view.id, {
        patent_id: item.id,
        new_start: isoDate(addDays(toDate(item.start), deltaDays)),
        new_end: isoDate(addDays(toDate(item.end), deltaDays)),
      })
      await load()
    } catch (requestError: unknown) {
      setError(getErrorMessage(requestError, '日期更新失败'))
    } finally {
      setSaving(false)
    }
  }

  const dateFields = fields.filter(field => field.field_type === 'date' && field.editable !== false)
  const titleFields = fields.filter(field => field.editable !== false)
  return (
    <div className="gantt-view">
      <div className="gantt-toolbar">
        <label>开始 <select className="form-input" value={config.start_field} onChange={event => void updateConfig({ start_field: event.target.value })} disabled={saving}>{dateFields.map(field => <option key={field.key} value={field.key}>{field.name}</option>)}</select></label>
        <label>结束 <select className="form-input" value={config.end_field} onChange={event => void updateConfig({ end_field: event.target.value })} disabled={saving}>{dateFields.map(field => <option key={field.key} value={field.key}>{field.name}</option>)}</select></label>
        <label>标题 <select className="form-input" value={config.title_field} onChange={event => void updateConfig({ title_field: event.target.value })} disabled={saving}>{titleFields.map(field => <option key={field.key} value={field.key}>{field.name}</option>)}</select></label>
        <label>缩放 <select className="form-input" value={config.time_scale} onChange={event => void updateConfig({ time_scale: event.target.value as GanttConfig['time_scale'] })} disabled={saving}><option value="day">日</option><option value="week">周</option><option value="month">月</option><option value="quarter">季</option><option value="year">年</option></select></label>
        {saving && <span className="gantt-saving">保存中...</span>}
      </div>
      {error && <div className="kanban-error">{error}</div>}
      {loading ? <div className="loading-state"><div className="spinner" />加载甘特视图...</div> : !data || data.returned === 0 ? <div className="empty-state"><div className="empty-state-title">暂无时间线数据</div><div>需要同时填写开始和结束日期</div></div> : <Timeline data={data} config={config} onMove={moveItem} />}
    </div>
  )
}
