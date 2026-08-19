import { useMemo, useState } from 'react'
import type { FieldMeta, PatentView, ViewColumnConfig } from '../../types'
import Icon from '../common/Icon'

interface ViewColumnConfigPanelProps {
  open: boolean
  view: PatentView
  fields: FieldMeta[]
  onClose: () => void
  onSave: (columnConfig: ViewColumnConfig[]) => Promise<void>
}

function buildInitialConfig(view: PatentView, fields: FieldMeta[]): ViewColumnConfig[] {
  const configured = view.column_config || []
  const byKey = new Map(configured.map(column => [column.key, column]))
  const known = fields.map((field, index) => {
    const column = byKey.get(field.key)
    return {
      key: field.key,
      visible: column?.visible ?? (configured.length === 0 ? field.visible !== false : false),
      width: column?.width ?? field.width ?? 150,
      order: column?.order ?? (configured.length + index),
    }
  })
  const knownKeys = new Set(known.map(column => column.key))
  const unknown = configured.filter(column => !knownKeys.has(column.key))
  return [...known, ...unknown].sort((a, b) => (a.order ?? 0) - (b.order ?? 0))
}

export default function ViewColumnConfigPanel({ open, view, fields, onClose, onSave }: ViewColumnConfigPanelProps) {
  const initialConfig = useMemo(() => buildInitialConfig(view, fields), [view, fields])
  const [draft, setDraft] = useState<ViewColumnConfig[]>(initialConfig)
  const [search, setSearch] = useState('')
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')

  if (!open) return null

  const visibleCount = draft.filter(column => column.visible !== false).length
  const filtered = draft.filter(column => {
    const field = fields.find(item => item.key === column.key)
    const query = search.trim().toLowerCase()
    return !query || field?.name.toLowerCase().includes(query) || column.key.toLowerCase().includes(query)
  })

  const updateColumn = (key: string, update: Partial<ViewColumnConfig>) => {
    setDraft(current => current.map(column => column.key === key ? { ...column, ...update } : column))
  }

  const moveColumn = (key: string, direction: -1 | 1) => {
    setDraft(current => {
      const index = current.findIndex(column => column.key === key)
      const target = index + direction
      if (index < 0 || target < 0 || target >= current.length) return current
      const next = [...current]
      const [moved] = next.splice(index, 1)
      next.splice(target, 0, moved)
      return next.map((column, order) => ({ ...column, order }))
    })
  }

  const setAllVisible = (visible: boolean) => {
    setDraft(current => current.map(column => ({ ...column, visible })))
  }

  const reset = () => {
    setDraft(initialConfig)
    setError('')
  }

  const save = async () => {
    const normalized = draft.map((column, order) => ({
      key: column.key,
      visible: column.visible !== false,
      width: Math.min(1200, Math.max(40, Number(column.width) || 150)),
      order,
    }))
    setSaving(true)
    setError('')
    try {
      await onSave(normalized)
      onClose()
    } catch (reason: unknown) {
      setError(reason instanceof Error ? reason.message : '保存失败，请重试')
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal" style={{ maxWidth: 760 }} onClick={event => event.stopPropagation()}>
        <div className="modal-header">
          <div>
            <div className="modal-title">列管理</div>
            <div style={{ fontSize: 12, color: '#64748b', marginTop: 3 }}>{view.name}</div>
          </div>
          <button className="modal-close" type="button" onClick={onClose} aria-label="关闭"><Icon name="x" /></button>
        </div>
        <div className="modal-body">
          <div style={{ display: 'flex', gap: 8, alignItems: 'center', flexWrap: 'wrap', marginBottom: 10 }}>
            <input
              className="form-input"
              value={search}
              onChange={event => setSearch(event.target.value)}
              placeholder="搜索字段"
              style={{ flex: '1 1 220px', minWidth: 180 }}
            />
            <button className="btn btn-sm btn-secondary" type="button" onClick={() => setAllVisible(true)}>全部显示</button>
            <button className="btn btn-sm btn-secondary" type="button" onClick={() => setAllVisible(false)}>全部隐藏</button>
            <button className="btn btn-sm btn-secondary" type="button" onClick={reset}>恢复初始</button>
          </div>
          <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 12, color: '#64748b', marginBottom: 8 }}>
            <span>共 {draft.length} 个字段，当前显示 {visibleCount} 个</span>
            <span>新字段默认隐藏，可在这里加入当前视图</span>
          </div>
          <div style={{ maxHeight: 480, overflowY: 'auto', border: '1px solid #e2e8f0', borderRadius: 6 }}>
            {filtered.map(column => {
              const field = fields.find(item => item.key === column.key)
              const position = draft.findIndex(item => item.key === column.key)
              const visible = column.visible !== false
              return (
                <div key={column.key} style={{ display: 'grid', gridTemplateColumns: '32px minmax(180px, 1fr) 82px 86px 72px', gap: 8, alignItems: 'center', padding: '8px 10px', borderBottom: '1px solid #f1f5f9', background: visible ? '#fff' : '#f8fafc', opacity: visible ? 1 : 0.68 }}>
                  <input type="checkbox" checked={visible} onChange={event => updateColumn(column.key, { visible: event.target.checked })} aria-label={`显示${field?.name || column.key}`} />
                  <div style={{ minWidth: 0 }}>
                    <div style={{ fontSize: 13, color: '#1f2937', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{field?.name || column.key}</div>
                    <div style={{ fontSize: 10, color: '#94a3b8', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                      {field?.is_system ? '系统字段' : field ? '自定义字段' : '未注册字段'} · {field?.field_type || 'unknown'}
                    </div>
                  </div>
                  <label style={{ display: 'flex', alignItems: 'center', gap: 4, fontSize: 11, color: '#64748b' }}>
                    宽
                    <input
                      type="number"
                      min={40}
                      max={1200}
                      value={column.width ?? 150}
                      onChange={event => updateColumn(column.key, { width: Number(event.target.value) })}
                      style={{ width: 58, padding: '3px 4px', border: '1px solid #cbd5e1', borderRadius: 3 }}
                    />
                  </label>
                  <span style={{ fontSize: 11, color: '#64748b', textAlign: 'center' }}>第 {position + 1} 列</span>
                  <div style={{ display: 'flex', gap: 3, justifyContent: 'flex-end' }}>
                    <button className="btn btn-xs btn-ghost" type="button" onClick={() => moveColumn(column.key, -1)} disabled={position === 0} title="上移"><Icon name="chevron-up" size={14} /></button>
                    <button className="btn btn-xs btn-ghost" type="button" onClick={() => moveColumn(column.key, 1)} disabled={position === draft.length - 1} title="下移"><Icon name="chevron-down" size={14} /></button>
                  </div>
                </div>
              )
            })}
            {filtered.length === 0 && <div style={{ padding: 28, textAlign: 'center', color: '#94a3b8', fontSize: 12 }}>没有匹配字段</div>}
          </div>
          {error && <div style={{ marginTop: 10, color: '#b91c1c', background: '#fef2f2', border: '1px solid #fecaca', padding: '8px 10px', borderRadius: 4, fontSize: 12 }}>{error}</div>}
        </div>
        <div className="modal-footer">
          <button className="btn btn-secondary" type="button" onClick={onClose} disabled={saving}>取消</button>
          <button className="btn btn-primary" type="button" onClick={() => void save()} disabled={saving}>{saving ? '保存中...' : '保存当前视图'}</button>
        </div>
      </div>
    </div>
  )
}
