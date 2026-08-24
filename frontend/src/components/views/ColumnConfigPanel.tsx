import { useMemo, useState } from 'react'
import type { FieldMeta } from '../../types'
import Icon from '../common/Icon'

interface ColumnConfigPanelProps {
  open: boolean
  fields: FieldMeta[]
  frozenFields: Set<string>
  onClose: () => void
  onToggleVisible: (key: string) => void
  onToggleFreeze: (key: string) => void
  onRemove: (key: string) => void
  onReorder: (keys: string[]) => void
}

export default function ColumnConfigPanel({ open, fields, frozenFields, onClose, onToggleVisible, onToggleFreeze, onRemove, onReorder }: ColumnConfigPanelProps) {
  const [search, setSearch] = useState('')
  const [draggedKey, setDraggedKey] = useState<string | null>(null)
  const query = search.trim().toLowerCase()
  const filtered = useMemo(() => fields.filter(field => !query || field.name.toLowerCase().includes(query) || field.key.toLowerCase().includes(query)), [fields, query])
  if (!open) return null

  const move = (targetKey: string, targetVisible: boolean) => {
    if (!draggedKey || draggedKey === targetKey) return
    const sourceIndex = fields.findIndex(field => field.key === draggedKey)
    const targetIndex = fields.findIndex(field => field.key === targetKey)
    if (sourceIndex < 0 || targetIndex < 0) return
    const next = fields.map(field => field.key)
    next.splice(sourceIndex, 1)
    next.splice(next.indexOf(targetKey), 0, draggedKey)
    onReorder(next)
    if (fields.find(field => field.key === draggedKey)?.visible !== targetVisible) onToggleVisible(draggedKey)
    setDraggedKey(null)
  }

  const moveToEnd = (targetVisible: boolean) => {
    if (!draggedKey) return
    const next = fields.map(field => field.key).filter(key => key !== draggedKey)
    next.push(draggedKey)
    onReorder(next)
    if (fields.find(field => field.key === draggedKey)?.visible !== targetVisible) onToggleVisible(draggedKey)
    setDraggedKey(null)
  }

  const renderField = (field: FieldMeta, visible: boolean) => (
    <div
      key={field.key}
      draggable
      onDragStart={() => setDraggedKey(field.key)}
      onDragEnd={() => setDraggedKey(null)}
      onDragOver={event => event.preventDefault()}
      onDrop={event => { event.stopPropagation(); move(field.key, visible) }}
      style={{ display: 'grid', gridTemplateColumns: '26px minmax(0, 1fr) auto auto', gap: 8, alignItems: 'center', padding: '8px 10px', borderBottom: '1px solid #f1f5f9', background: visible ? '#fff' : '#f8fafc', opacity: visible ? 1 : 0.7, cursor: 'grab' }}
    >
      <input type="checkbox" checked={visible} onChange={() => onToggleVisible(field.key)} aria-label={`显示${field.name}`} />
      <div style={{ minWidth: 0 }}><div style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', fontSize: 13, color: '#1f2937' }}>{field.name}</div><div style={{ fontSize: 10, color: '#94a3b8' }}>{field.field_type}</div></div>
      <button type="button" className="btn btn-xs btn-ghost" onClick={() => onToggleFreeze(field.key)} title={frozenFields.has(field.key) ? '取消冻结' : '冻结此列'}><Icon name={frozenFields.has(field.key) ? 'lock' : 'unlock'} size={14} /></button>
      {visible && <button type="button" className="btn btn-xs btn-ghost" onClick={() => onRemove(field.key)} title="从当前表格移除" style={{ color: '#dc2626' }}><Icon name="trash" size={14} /></button>}
    </div>
  )

  const visible = filtered.filter(field => field.visible !== false)
  const hidden = filtered.filter(field => field.visible === false)
  return <div className="modal-overlay" onClick={onClose}><div className="modal" style={{ maxWidth: 760 }} onClick={event => event.stopPropagation()}>
    <div className="modal-header"><div><div className="modal-title">列管理</div><div style={{ fontSize: 12, color: '#64748b', marginTop: 3 }}>拖拽字段条调整顺序，拖到另一栏即可显示或隐藏</div></div><button className="modal-close" type="button" onClick={onClose} aria-label="关闭"><Icon name="x" /></button></div>
    <div className="modal-body"><div style={{ display: 'flex', gap: 8, marginBottom: 10 }}><input className="form-input" value={search} onChange={event => setSearch(event.target.value)} placeholder="搜索字段名称或 key" style={{ flex: 1 }} /></div><div style={{ fontSize: 12, color: '#64748b', marginBottom: 10 }}>共 {fields.length} 列 · 当前显示 {fields.filter(field => field.visible !== false).length} 列</div><div style={{ display: 'grid', gap: 10, maxHeight: 520, overflowY: 'auto' }}><section style={{ border: '1px solid #c7e3dd', borderRadius: 6, overflow: 'hidden' }} onDragOver={event => event.preventDefault()} onDrop={() => moveToEnd(true)}><div style={{ padding: '8px 10px', background: '#eefaf7', color: '#226d65', fontSize: 12, fontWeight: 700 }}>显示字段 ({visible.length})</div>{visible.map(field => renderField(field, true))}{visible.length === 0 && <div style={{ padding: 20, color: '#94a3b8', fontSize: 12, textAlign: 'center' }}>拖到此处显示字段</div>}</section><section style={{ border: '1px solid #e2e8f0', borderRadius: 6, overflow: 'hidden' }} onDragOver={event => event.preventDefault()} onDrop={() => moveToEnd(false)}><div style={{ padding: '8px 10px', background: '#f8fafc', color: '#64748b', fontSize: 12, fontWeight: 700 }}>隐藏字段 ({hidden.length})</div>{hidden.map(field => renderField(field, false))}{hidden.length === 0 && <div style={{ padding: 20, color: '#94a3b8', fontSize: 12, textAlign: 'center' }}>拖到此处隐藏字段</div>}</section></div></div><div className="modal-footer"><button className="btn btn-primary" type="button" onClick={onClose}>完成</button></div>
  </div></div>
}
