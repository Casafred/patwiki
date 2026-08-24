import { useMemo, useState } from 'react'
import type { FieldMeta, PatentView, ViewColumnConfig } from '../../types'
import Icon from '../common/Icon'

interface ViewColumnConfigPanelProps {
  open: boolean
  view: PatentView
  fields: FieldMeta[]
  onClose: () => void
  onSave: (columnConfig: ViewColumnConfig[]) => Promise<void>
  onRemove?: (fieldKey: string) => void
}

function buildInitialConfig(view: PatentView, fields: FieldMeta[]): ViewColumnConfig[] {
  const configured = view.column_config || []
  const byKey = new Map(configured.map(column => [column.key, column]))
  const known = fields.map((field, index) => {
    const column = byKey.get(field.key)
    return { key: field.key, visible: column?.visible ?? (configured.length === 0 ? field.visible !== false : false), width: column?.width ?? field.width ?? 150, order: column?.order ?? configured.length + index }
  })
  const knownKeys = new Set(known.map(column => column.key))
  return [...known, ...configured.filter(column => !knownKeys.has(column.key))].sort((a, b) => (a.order ?? 0) - (b.order ?? 0))
}

export default function ViewColumnConfigPanel({ open, view, fields, onClose, onSave, onRemove }: ViewColumnConfigPanelProps) {
  const initialConfig = useMemo(() => buildInitialConfig(view, fields), [view, fields])
  const [draft, setDraft] = useState<ViewColumnConfig[]>(initialConfig)
  const [search, setSearch] = useState('')
  const [draggedKey, setDraggedKey] = useState<string | null>(null)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')
  if (!open) return null

  const query = search.trim().toLowerCase()
  const matches = (column: ViewColumnConfig) => {
    const field = fields.find(item => item.key === column.key)
    return !query || field?.name.toLowerCase().includes(query) || column.key.toLowerCase().includes(query)
  }
  const visibleColumns = draft.filter(column => column.visible !== false && matches(column))
  const hiddenColumns = draft.filter(column => column.visible === false && matches(column))
  const visibleCount = draft.filter(column => column.visible !== false).length

  const updateColumn = (key: string, update: Partial<ViewColumnConfig>) => setDraft(current => current.map(column => column.key === key ? { ...column, ...update } : column))
  const moveColumn = (sourceKey: string, targetKey: string, targetVisible: boolean) => setDraft(current => {
    const sourceIndex = current.findIndex(column => column.key === sourceKey)
    if (sourceIndex < 0 || sourceKey === targetKey) return current
    const next = [...current]
    const [moved] = next.splice(sourceIndex, 1)
    const targetIndex = next.findIndex(column => column.key === targetKey)
    next.splice(targetIndex < 0 ? next.length : targetIndex, 0, { ...moved, visible: targetVisible })
    return next.map((column, order) => ({ ...column, order }))
  })
  const moveColumnToEnd = (sourceKey: string, targetVisible: boolean) => setDraft(current => {
    const sourceIndex = current.findIndex(column => column.key === sourceKey)
    if (sourceIndex < 0) return current
    const next = [...current]
    const [moved] = next.splice(sourceIndex, 1)
    next.push({ ...moved, visible: targetVisible })
    return next.map((column, order) => ({ ...column, order }))
  })
  const setAllVisible = (visible: boolean) => setDraft(current => current.map(column => ({ ...column, visible })))
  const reset = () => { setDraft(initialConfig); setError('') }
  const save = async () => {
    const normalized = draft.map((column, order) => ({ key: column.key, visible: column.visible !== false, width: Math.min(1200, Math.max(40, Number(column.width) || 150)), order }))
    setSaving(true)
    setError('')
    try { await onSave(normalized); onClose() } catch (reason: unknown) { setError(reason instanceof Error ? reason.message : '保存失败，请重试') } finally { setSaving(false) }
  }
  const renderColumn = (column: ViewColumnConfig, targetVisible: boolean) => {
    const field = fields.find(item => item.key === column.key)
    const position = draft.findIndex(item => item.key === column.key)
    return <div key={column.key} draggable onDragStart={() => setDraggedKey(column.key)} onDragEnd={() => setDraggedKey(null)} onDragOver={event => event.preventDefault()} onDrop={event => { event.stopPropagation(); if (draggedKey) moveColumn(draggedKey, column.key, targetVisible); setDraggedKey(null) }} style={{ display: 'grid', gridTemplateColumns: '26px minmax(180px, 1fr) 82px 74px', gap: 8, alignItems: 'center', padding: '8px 10px', borderBottom: '1px solid #f1f5f9', background: targetVisible ? '#fff' : '#f8fafc', opacity: targetVisible ? 1 : 0.72, cursor: 'grab' }}>
      <input type="checkbox" checked={targetVisible} onChange={event => updateColumn(column.key, { visible: event.target.checked })} aria-label={`显示${field?.name || column.key}`} />
      <div style={{ minWidth: 0 }}><div style={{ fontSize: 13, color: '#1f2937', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{field?.name || column.key}</div><div style={{ fontSize: 10, color: '#94a3b8' }}>{field ? `字段类型：${field.field_type}` : '未注册字段'}</div></div>
      <label style={{ display: 'flex', alignItems: 'center', gap: 4, fontSize: 11, color: '#64748b' }}>宽<input type="number" min={40} max={1200} value={column.width ?? 150} onChange={event => updateColumn(column.key, { width: Number(event.target.value) })} style={{ width: 58, padding: '3px 4px', border: '1px solid #cbd5e1', borderRadius: 3 }} /></label>
      <div style={{ display: 'flex', gap: 3, justifyContent: 'flex-end', alignItems: 'center' }}><span style={{ fontSize: 10, color: '#94a3b8' }}>#{position + 1}</span>{onRemove && targetVisible && <button className="btn btn-xs btn-ghost" type="button" onClick={() => onRemove(column.key)} title="从当前视图移除" style={{ color: '#dc2626' }}><Icon name="trash" size={14} /></button>}</div>
    </div>
  }
  return <div className="modal-overlay" onClick={onClose}><div className="modal" style={{ maxWidth: 760 }} onClick={event => event.stopPropagation()}>
    <div className="modal-header"><div><div className="modal-title">列管理</div><div style={{ fontSize: 12, color: '#64748b', marginTop: 3 }}>{view.name}</div></div><button className="modal-close" type="button" onClick={onClose} aria-label="关闭"><Icon name="x" /></button></div>
    <div className="modal-body"><div style={{ display: 'flex', gap: 8, alignItems: 'center', flexWrap: 'wrap', marginBottom: 10 }}><input className="form-input" value={search} onChange={event => setSearch(event.target.value)} placeholder="搜索字段" style={{ flex: '1 1 220px', minWidth: 180 }} /><button className="btn btn-sm btn-secondary" type="button" onClick={() => setAllVisible(true)}>全部显示</button><button className="btn btn-sm btn-secondary" type="button" onClick={() => setAllVisible(false)}>全部隐藏</button><button className="btn btn-sm btn-secondary" type="button" onClick={reset}>恢复初始</button></div><div style={{ fontSize: 12, color: '#64748b', marginBottom: 8 }}>共 {draft.length} 个字段，当前显示 {visibleCount} 个。拖动字段条即可调整顺序；拖到另一栏会同步显示状态。</div>
      <div style={{ maxHeight: 500, overflowY: 'auto', display: 'grid', gap: 10 }}><section style={{ border: '1px solid #c7e3dd', borderRadius: 6, overflow: 'hidden' }} onDragOver={event => event.preventDefault()} onDrop={() => { if (draggedKey) moveColumnToEnd(draggedKey, true); setDraggedKey(null) }}><div style={{ padding: '8px 10px', background: '#eefaf7', color: '#226d65', fontSize: 12, fontWeight: 700 }}>当前显示字段 ({visibleCount})</div>{visibleColumns.map(column => renderColumn(column, true))}{visibleColumns.length === 0 && <div style={{ padding: 20, color: '#94a3b8', fontSize: 12, textAlign: 'center' }}>拖到此处显示字段</div>}</section><section style={{ border: '1px solid #e2e8f0', borderRadius: 6, overflow: 'hidden' }} onDragOver={event => event.preventDefault()} onDrop={() => { if (draggedKey) moveColumnToEnd(draggedKey, false); setDraggedKey(null) }}><div style={{ padding: '8px 10px', background: '#f8fafc', color: '#64748b', fontSize: 12, fontWeight: 700 }}>当前隐藏字段 ({draft.length - visibleCount})</div>{hiddenColumns.map(column => renderColumn(column, false))}{hiddenColumns.length === 0 && <div style={{ padding: 20, color: '#94a3b8', fontSize: 12, textAlign: 'center' }}>拖到此处隐藏字段</div>}</section></div>
      {error && <div style={{ marginTop: 10, color: '#b91c1c', background: '#fef2f2', border: '1px solid #fecaca', padding: '8px 10px', borderRadius: 4, fontSize: 12 }}>{error}</div>}</div><div className="modal-footer"><button className="btn btn-secondary" type="button" onClick={onClose} disabled={saving}>取消</button><button className="btn btn-primary" type="button" onClick={() => void save()} disabled={saving}>{saving ? '保存中...' : '保存当前视图'}</button></div>
  </div></div>
}
