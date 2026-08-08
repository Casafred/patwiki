import { useState } from 'react'
import type { ConditionalFormatRule, FieldMeta, PatentView } from '../../types'

interface ConditionalFormatPanelProps {
  open: boolean
  view: PatentView
  fields: FieldMeta[]
  onClose: () => void
  onSave: (rules: ConditionalFormatRule[]) => Promise<void>
}

const operators = [
  ['==', '等于'], ['!=', '不等于'], ['contains', '包含'],
  ['starts_with', '开头是'], ['ends_with', '结尾是'], ['>', '大于'],
  ['<', '小于'], ['>=', '大于等于'], ['<=', '小于等于'],
  ['is_empty', '为空'], ['is_not_empty', '不为空'],
  ['date_within', '未来 N 天'], ['date_before', '早于日期'], ['date_after', '晚于日期'],
] as const

const noValueOperators = new Set(['is_empty', 'is_not_empty'])

export default function ConditionalFormatPanel({ open, view, fields, onClose, onSave }: ConditionalFormatPanelProps) {
  const [rules, setRules] = useState<ConditionalFormatRule[]>(() => view.conditional_formatting || [])
  const [field, setField] = useState(fields[0]?.key || '')
  const [operator, setOperator] = useState('==')
  const [value, setValue] = useState('')
  const [bgColor, setBgColor] = useState('#fff3cd')
  const [color, setColor] = useState('#7c4a03')
  const [saving, setSaving] = useState(false)

  if (!open) return null

  const addRule = () => {
    if (!field) return
    const condition = {
      op: operator,
      ...(noValueOperators.has(operator) ? {} : { value }),
      ...(operator === 'date_within' ? { unit: 'day' as const } : {}),
      style: { bgColor, color, fontWeight: '600' },
    }
    setRules([...rules, { id: `cf_${Date.now()}`, field, conditions: [condition] }])
    setValue('')
  }

  const save = async () => {
    setSaving(true)
    try {
      await onSave(rules)
      onClose()
    } catch {
      alert('条件格式保存失败')
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="modal-overlay">
      <div className="modal" style={{ maxWidth: 760 }}>
        <div className="modal-header">
          <div className="modal-title">条件格式</div>
          <button className="modal-close" type="button" onClick={onClose} aria-label="关闭">×</button>
        </div>
        <div className="modal-body">
          <div style={{ fontSize: 12, color: '#6b7280', marginBottom: 12 }}>
            条件按顺序匹配，单元格使用第一条命中的样式。
          </div>
          <div style={{ display: 'grid', gridTemplateColumns: '1.1fr 1fr 1fr 54px 54px auto', gap: 6, alignItems: 'center', marginBottom: 16 }}>
            <select className="form-select" value={field} onChange={event => setField(event.target.value)}>
              {fields.map(item => <option key={item.key} value={item.key}>{item.name}</option>)}
            </select>
            <select className="form-select" value={operator} onChange={event => setOperator(event.target.value)}>
              {operators.map(([key, label]) => <option key={key} value={key}>{label}</option>)}
            </select>
            <input className="form-input" value={value} onChange={event => setValue(event.target.value)} disabled={noValueOperators.has(operator)} placeholder={operator === 'date_within' ? '天数' : '匹配值'} />
            <input type="color" value={bgColor} onChange={event => setBgColor(event.target.value)} title="背景颜色" />
            <input type="color" value={color} onChange={event => setColor(event.target.value)} title="文字颜色" />
            <button className="btn btn-sm btn-secondary" type="button" onClick={addRule}>添加</button>
          </div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
            {rules.length === 0 && <div style={{ padding: 24, textAlign: 'center', border: '1px dashed #d1d5db', color: '#9ca3af' }}>暂无规则</div>}
            {rules.map(rule => {
              const condition = rule.conditions[0]
              const fieldName = fields.find(item => item.key === rule.field)?.name || rule.field
              const operatorName = operators.find(item => item[0] === condition?.op)?.[1] || condition?.op
              return (
                <div key={rule.id} style={{ display: 'flex', alignItems: 'center', gap: 10, padding: '8px 10px', border: '1px solid #e5e7eb', borderRadius: 5 }}>
                  <span style={{ width: 90, fontWeight: 500 }}>{fieldName}</span>
                  <span style={{ color: '#6b7280' }}>{operatorName}</span>
                  <span style={{ flex: 1 }}>{String(condition?.value ?? '')}</span>
                  <span style={{ width: 42, height: 22, background: condition?.style?.bgColor, border: '1px solid #d1d5db' }} title="背景预览" />
                  <button className="btn btn-xs btn-ghost" type="button" onClick={() => setRules(rules.filter(item => item.id !== rule.id))} title="删除规则">×</button>
                </div>
              )
            })}
          </div>
        </div>
        <div className="modal-footer">
          <button className="btn btn-secondary" type="button" onClick={onClose}>取消</button>
          <button className="btn btn-primary" type="button" onClick={() => void save()} disabled={saving}>{saving ? '保存中...' : '保存设置'}</button>
        </div>
      </div>
    </div>
  )
}
