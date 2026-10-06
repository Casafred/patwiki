import { useMemo, useState } from 'react'
import { EXTERNAL_UPDATE_PRESETS_STORAGE_KEY, HIMMPAT_UPDATE_FIELD_GROUPS, type ExternalUpdateField, type ExternalUpdateFieldGroup } from '../../lib/externalSync'
import Icon from '../common/Icon'

interface FieldPreset {
  id: string
  name: string
  fields: string[]
}

export default function McpFieldSelection({ fields, selectedFields, onChange, disabled = false }: {
  fields: readonly ExternalUpdateField[]
  selectedFields: string[]
  onChange: (fields: string[]) => void
  disabled?: boolean
}) {
  const [presets, setPresets] = useState<FieldPreset[]>(() => {
    try {
      const stored = JSON.parse(localStorage.getItem(EXTERNAL_UPDATE_PRESETS_STORAGE_KEY) || '[]') as unknown
      return Array.isArray(stored)
        ? stored.filter((item): item is FieldPreset => Boolean(item && typeof item.id === 'string' && typeof item.name === 'string' && Array.isArray(item.fields)))
        : []
    } catch {
      return []
    }
  })
  const [presetId, setPresetId] = useState('')
  const [presetName, setPresetName] = useState('')
  const [activeGroup, setActiveGroup] = useState(0)

  const groups = useMemo(() => {
    const allowed = new Map(fields.map(field => [field.key, field]))
    const result: ExternalUpdateFieldGroup[] = HIMMPAT_UPDATE_FIELD_GROUPS.map(group => ({
      label: group.label,
      fields: group.fields.map(field => allowed.get(field.key)).filter((field): field is ExternalUpdateField => Boolean(field)),
    })).filter(group => group.fields.length)
    const groupedKeys = new Set(result.flatMap(group => group.fields.map(field => field.key)))
    const extras = fields.filter(field => !groupedKeys.has(field.key))
    if (extras.length) result.push({ label: '其他字段', fields: extras })
    return result
  }, [fields])

  const currentGroup = groups[Math.min(activeGroup, Math.max(0, groups.length - 1))]
  const persist = (next: FieldPreset[]) => {
    setPresets(next)
    localStorage.setItem(EXTERNAL_UPDATE_PRESETS_STORAGE_KEY, JSON.stringify(next))
  }
  const toggleField = (key: string) => onChange(selectedFields.includes(key)
    ? selectedFields.filter(field => field !== key)
    : [...selectedFields, key])
  const applyPreset = (id: string) => {
    setPresetId(id)
    const preset = presets.find(item => item.id === id)
    if (preset) onChange(preset.fields.filter(key => fields.some(field => field.key === key)))
  }
  const savePreset = () => {
    const name = presetName.trim()
    if (!name || selectedFields.length === 0) return
    const existing = presets.find(item => item.name.toLocaleLowerCase() === name.toLocaleLowerCase())
    const nextPreset = { id: existing?.id || `field-preset-${Date.now()}`, name, fields: [...new Set(selectedFields)] }
    persist(existing ? presets.map(item => item.id === existing.id ? nextPreset : item) : [...presets, nextPreset])
    setPresetId(nextPreset.id)
    setPresetName('')
  }
  const deletePreset = () => {
    if (!presetId) return
    persist(presets.filter(item => item.id !== presetId))
    setPresetId('')
  }

  return <div className="mcp-field-selection">
    <div className="mcp-field-selection-toolbar">
      <div className="mcp-field-selection-actions">
        <button type="button" className="btn btn-secondary btn-sm" disabled={disabled} onClick={() => onChange(fields.map(field => field.key))}>全部勾选</button>
        <button type="button" className="btn btn-secondary btn-sm" disabled={disabled || selectedFields.length === 0} onClick={() => onChange([])}>取消全部</button>
        <span>{selectedFields.filter(key => fields.some(field => field.key === key)).length} / {fields.length}</span>
      </div>
      <div className="mcp-field-preset-controls">
        <select className="form-input" aria-label="已保存的字段配置" value={presetId} disabled={disabled || presets.length === 0} onChange={event => applyPreset(event.target.value)}>
          <option value="">选择字段配置</option>
          {presets.map(preset => <option key={preset.id} value={preset.id}>{preset.name}</option>)}
        </select>
        <input className="form-input" aria-label="字段配置名称" value={presetName} disabled={disabled} onChange={event => setPresetName(event.target.value)} onKeyDown={event => { if (event.key === 'Enter') { event.preventDefault(); savePreset() } }} placeholder="配置名称" />
        <button type="button" className="btn btn-secondary btn-sm" disabled={disabled || !presetName.trim() || selectedFields.length === 0} onClick={savePreset}>保存配置</button>
        <button type="button" className="btn btn-ghost btn-sm mcp-preset-delete" disabled={disabled || !presetId} onClick={deletePreset} title="删除所选配置" aria-label="删除所选配置"><Icon name="trash" size={14} /></button>
      </div>
    </div>
    <div className="mcp-field-group-tabs" role="tablist" aria-label="字段分组">
      {groups.map((group, index) => <button key={group.label} type="button" role="tab" aria-selected={index === activeGroup} className={index === activeGroup ? 'active' : ''} onClick={() => setActiveGroup(index)}>
        {group.label}<span>{group.fields.filter(field => selectedFields.includes(field.key)).length}/{group.fields.length}</span>
      </button>)}
    </div>
    {currentGroup && <div className="mcp-field-group-window" key={currentGroup.label}>
      <div className="mcp-field-group-window-head">
        <strong>{currentGroup.label}</strong>
        <button type="button" className="mcp-link-button" disabled={disabled} onClick={() => {
          const groupKeys = currentGroup.fields.map(field => field.key)
          const allChecked = groupKeys.every(key => selectedFields.includes(key))
          onChange(allChecked ? selectedFields.filter(key => !groupKeys.includes(key)) : [...new Set([...selectedFields, ...groupKeys])])
        }}>{currentGroup.fields.every(field => selectedFields.includes(field.key)) ? '取消本组' : '勾选本组'}</button>
      </div>
      <div className="mcp-target-fields-grid">
        {currentGroup.fields.map(field => <label key={field.key} title={field.key}>
          <input type="checkbox" disabled={disabled} checked={selectedFields.includes(field.key)} onChange={() => toggleField(field.key)} />
          {field.label}<small>{field.key}</small>
        </label>)}
      </div>
    </div>}
  </div>
}
