import { useState } from 'react'
import { exportApi } from '../../api'
import type { FieldMeta, JsonObject, JsonValue } from '../../types'
import { getErrorMessage } from '../../lib/errors'

interface ExportDialogProps {
  fields: FieldMeta[]
  databaseId?: number | null
  viewId?: number | null
  search?: string
  filters?: JsonObject
  onClose: () => void
}

type ExportFormat = 'excel' | 'csv'

export default function ExportDialog({ fields, databaseId, viewId, search, filters, onClose }: ExportDialogProps) {
  const [format, setFormat] = useState<ExportFormat>('excel')
  const [scope, setScope] = useState<'view' | 'database'>(viewId ? 'view' : 'database')
  const [selectedKeys, setSelectedKeys] = useState<string[]>(() => fields.filter(field => field.visible !== false).map(field => field.key))
  const [groupBy, setGroupBy] = useState('')
  const [saving, setSaving] = useState(false)

  const toggleField = (key: string) => {
    setSelectedKeys(current => current.includes(key) ? current.filter(item => item !== key) : [...current, key])
  }

  const download = (blob: Blob, extension: string) => {
    const url = window.URL.createObjectURL(blob)
    const anchor = document.createElement('a')
    anchor.href = url
    anchor.download = `patwiki_export_${new Date().toISOString().slice(0, 10)}.${extension}`
    anchor.click()
    window.URL.revokeObjectURL(url)
  }

  const handleExport = async () => {
    if (selectedKeys.length === 0) {
      alert('请至少选择一个字段')
      return
    }
    setSaving(true)
    try {
      const payload: JsonObject = {
        database_id: databaseId ?? null,
        view_id: scope === 'view' ? (viewId ?? null) : null,
        field_keys: selectedKeys,
        filters: (filters || {}) as unknown as JsonValue,
        search: search || null,
        group_by: format === 'excel' && groupBy ? groupBy : null,
      }
      const blob = format === 'excel' ? await exportApi.excel(payload) : await exportApi.csv(payload)
      download(blob, format === 'excel' ? 'xlsx' : 'csv')
      onClose()
    } catch (error: unknown) {
      alert(getErrorMessage(error, '导出失败'))
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal modal-lg" onClick={event => event.stopPropagation()}>
        <div className="modal-header">
          <h3>导出数据</h3>
          <button type="button" className="modal-close" onClick={onClose} aria-label="关闭">×</button>
        </div>
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12, marginBottom: 16 }}>
          <label className="form-label">格式
            <select className="form-input" value={format} onChange={event => setFormat(event.target.value as ExportFormat)}>
              <option value="excel">Excel (.xlsx)</option>
              <option value="csv">CSV (.csv)</option>
            </select>
          </label>
          <label className="form-label">范围
            <select className="form-input" value={scope} onChange={event => setScope(event.target.value as 'view' | 'database')}>
              <option value="view" disabled={!viewId}>当前视图（含视图筛选）</option>
              <option value="database">当前库</option>
            </select>
          </label>
        </div>
        {format === 'excel' && (
          <label className="form-label" style={{ marginBottom: 16 }}>按字段拆分工作表
            <select className="form-input" value={groupBy} onChange={event => setGroupBy(event.target.value)}>
              <option value="">不拆分</option>
              {fields.filter(field => selectedKeys.includes(field.key) && ['text', 'select', 'boolean', 'formula'].includes(field.field_type)).map(field => (
                <option key={field.key} value={field.key}>{field.name}</option>
              ))}
            </select>
          </label>
        )}
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 8 }}>
          <strong style={{ fontSize: 13 }}>导出字段</strong>
          <div style={{ display: 'flex', gap: 6 }}>
            <button type="button" className="btn btn-xs btn-secondary" onClick={() => setSelectedKeys(fields.map(field => field.key))}>全选</button>
            <button type="button" className="btn btn-xs btn-secondary" onClick={() => setSelectedKeys([])}>清空</button>
          </div>
        </div>
        <div style={{ maxHeight: 300, overflowY: 'auto', display: 'grid', gridTemplateColumns: 'repeat(3, minmax(0, 1fr))', gap: 8, padding: 10, border: '1px solid #e2e8f0', borderRadius: 6 }}>
          {fields.map(field => (
            <label key={field.key} style={{ display: 'flex', gap: 6, alignItems: 'center', fontSize: 12, color: '#475569' }}>
              <input type="checkbox" checked={selectedKeys.includes(field.key)} onChange={() => toggleField(field.key)} />
              <span title={field.key}>{field.name}</span>
            </label>
          ))}
        </div>
        <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 8, marginTop: 18 }}>
          <button type="button" className="btn btn-secondary" onClick={onClose}>取消</button>
          <button type="button" className="btn btn-primary" onClick={() => void handleExport()} disabled={saving}>{saving ? '导出中...' : '开始导出'}</button>
        </div>
      </div>
    </div>
  )
}
