import { useRef, useState } from 'react'
import { formulaApi } from '../../api'
import type { CustomField, FormulaConfig, FormulaReturnType } from '../../types'
import { getErrorMessage } from '../../lib/errors'

interface FormulaEditorProps {
  value?: FormulaConfig
  fieldKey?: string
  availableFields: CustomField[]
  onChange: (value: FormulaConfig) => void
}

const SYSTEM_FIELDS = [
  ['title', '标题'], ['application_number', '申请号'], ['applicant', '申请人'],
  ['inventor', '发明人'], ['filing_date', '申请日'], ['grant_date', '授权日'],
  ['legal_status', '法律状态'], ['risk_level', '风险等级'], ['category', '技术分类'],
]

const FUNCTION_NAMES = ['IF', 'CONCAT', 'DATEDIFF', 'TODAY', 'NUMBER', 'TEXT', 'IS_EMPTY', 'COALESCE', 'SUM', 'AVG']

export default function FormulaEditor({ value, fieldKey, availableFields, onChange }: FormulaEditorProps) {
  const textareaRef = useRef<HTMLTextAreaElement>(null)
  const [validation, setValidation] = useState<{ valid: boolean; message: string } | null>(null)
  const expression = value?.expression || ''
  const returnType: FormulaReturnType = value?.return_type || 'text'

  const update = (patch: Partial<FormulaConfig>) => {
    onChange({ expression, return_type: returnType, ...patch })
    setValidation(null)
  }

  const insert = (text: string) => {
    const textarea = textareaRef.current
    if (!textarea) {
      update({ expression: `${expression}${text}` })
      return
    }
    const start = textarea.selectionStart
    const end = textarea.selectionEnd
    const next = `${expression.slice(0, start)}${text}${expression.slice(end)}`
    update({ expression: next })
    requestAnimationFrame(() => {
      textarea.focus()
      const cursor = start + text.length
      textarea.setSelectionRange(cursor, cursor)
    })
  }

  const validate = async () => {
    if (!expression.trim()) {
      setValidation({ valid: false, message: '公式不能为空' })
      return
    }
    try {
      const result = await formulaApi.validate(expression, fieldKey)
      setValidation({ valid: result.valid, message: result.valid ? `引用字段：${result.dependencies.join('、') || '无'}` : (result.error || '公式无效') })
    } catch (error: unknown) {
      setValidation({ valid: false, message: getErrorMessage(error, '公式校验失败') })
    }
  }

  return (
    <div style={{ gridColumn: '1 / -1', padding: 12, background: '#f8fafc', border: '1px solid #bfdbfe', borderRadius: 6 }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 8 }}>
        <strong style={{ fontSize: 12, color: '#1e3a8a' }}>公式配置</strong>
        <button type="button" className="btn btn-xs btn-secondary" onClick={() => void validate()}>校验公式</button>
      </div>
      <textarea
        ref={textareaRef}
        className="form-input"
        value={expression}
        onChange={event => update({ expression: event.target.value })}
        placeholder={'例如：IF(legal_status == "granted", "已授权", "未授权")'}
        style={{ minHeight: 82, fontFamily: 'monospace', fontSize: 12, resize: 'vertical' }}
      />
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 8, marginTop: 8 }}>
        <label style={{ fontSize: 12, color: '#64748b' }}>
          返回类型
          <select className="form-input" style={{ marginTop: 4 }} value={returnType} onChange={event => update({ return_type: event.target.value as FormulaReturnType })}>
            <option value="text">文本</option>
            <option value="number">数字</option>
            <option value="date">日期</option>
            <option value="boolean">是/否</option>
          </select>
        </label>
        <label style={{ fontSize: 12, color: '#64748b' }}>
          插入字段
          <select className="form-input" style={{ marginTop: 4 }} value="" onChange={event => { if (event.target.value) insert(event.target.value) }}>
            <option value="">选择字段...</option>
            {SYSTEM_FIELDS.map(([key, name]) => <option key={key} value={key}>{name} ({key})</option>)}
            {availableFields.filter(field => field.field_type !== 'formula' && field.key !== fieldKey).map(field => <option key={field.key} value={field.key}>{field.name} ({field.key})</option>)}
          </select>
        </label>
      </div>
      <div style={{ display: 'flex', flexWrap: 'wrap', gap: 4, marginTop: 8 }}>
        {FUNCTION_NAMES.map(name => <button type="button" key={name} className="btn btn-xs btn-secondary" onClick={() => insert(`${name}(`)}>{name}</button>)}
      </div>
      {validation && <div style={{ marginTop: 8, fontSize: 12, color: validation.valid ? '#15803d' : '#b91c1c' }}>{validation.valid ? '✓ ' : '× '}{validation.message}</div>}
    </div>
  )
}
