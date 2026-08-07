import { useState } from 'react'
import type { FieldMeta, PatentView, ViewGroupField } from '../../types'

interface GroupConfigPanelProps {
  open: boolean
  view: PatentView
  fields: FieldMeta[]
  onClose: () => void
  onSave: (fields: ViewGroupField[]) => Promise<void>
}

function readFields(view: PatentView): ViewGroupField[] {
  const config = view.group_by_config
  if (Array.isArray(config)) return config as ViewGroupField[]
  return (config as { fields?: ViewGroupField[] } | undefined)?.fields || []
}

export default function GroupConfigPanel({ open, view, fields, onClose, onSave }: GroupConfigPanelProps) {
  const [draft, setDraft] = useState<ViewGroupField[]>(() => readFields(view))
  const [saving, setSaving] = useState(false)

  if (!open) return null

  const availableFields = fields.filter(field => !draft.some(item => item.field === field.key))

  const addField = () => {
    const field = availableFields[0]
    if (!field || draft.length >= 3) return
    setDraft([...draft, { field: field.key, direction: 'asc', collapsed: false }])
  }

  const save = async () => {
    setSaving(true)
    try {
      await onSave(draft)
      onClose()
    } catch {
      alert('分组设置保存失败')
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="modal-overlay">
      <div className="modal" style={{ maxWidth: 620 }}>
        <div className="modal-header">
          <div className="modal-title">分组设置</div>
          <button className="modal-close" type="button" onClick={onClose} aria-label="关闭">×</button>
        </div>
        <div className="modal-body">
          <div style={{ fontSize: 12, color: '#6b7280', marginBottom: 12 }}>
            最多按三个字段嵌套分组，数据筛选和排序仍沿用当前视图。
          </div>
          {draft.length === 0 && (
            <div style={{ padding: 24, textAlign: 'center', border: '1px dashed #d1d5db', color: '#9ca3af' }}>
              当前未启用分组
            </div>
          )}
          <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
            {draft.map((item, index) => (
              <div key={`${item.field}-${index}`} style={{ display: 'grid', gridTemplateColumns: '1fr 110px auto auto', gap: 8, alignItems: 'center' }}>
                <select
                  className="form-select"
                  value={item.field}
                  onChange={event => setDraft(draft.map((current, currentIndex) => currentIndex === index ? { ...current, field: event.target.value } : current))}
                >
                  {fields.map(field => <option key={field.key} value={field.key}>{field.name}</option>)}
                </select>
                <select
                  className="form-select"
                  value={item.direction || 'asc'}
                  onChange={event => setDraft(draft.map((current, currentIndex) => currentIndex === index ? { ...current, direction: event.target.value as 'asc' | 'desc' } : current))}
                >
                  <option value="asc">升序</option>
                  <option value="desc">降序</option>
                </select>
                <label style={{ display: 'flex', alignItems: 'center', gap: 4, fontSize: 11, whiteSpace: 'nowrap' }}>
                  <input
                    type="checkbox"
                    checked={item.collapsed === true}
                    onChange={event => setDraft(draft.map((current, currentIndex) => currentIndex === index ? { ...current, collapsed: event.target.checked } : current))}
                  />
                  默认折叠
                </label>
                <button className="btn btn-xs btn-ghost" type="button" onClick={() => setDraft(draft.filter((_, currentIndex) => currentIndex !== index))} title="移除分组">×</button>
              </div>
            ))}
          </div>
          <button className="btn btn-sm btn-secondary" type="button" onClick={addField} disabled={draft.length >= 3 || availableFields.length === 0} style={{ marginTop: 12 }}>
            + 添加分组字段
          </button>
        </div>
        <div className="modal-footer">
          <button className="btn btn-secondary" type="button" onClick={onClose}>取消</button>
          <button className="btn btn-primary" type="button" onClick={() => void save()} disabled={saving}>{saving ? '保存中...' : '保存设置'}</button>
        </div>
      </div>
    </div>
  )
}
