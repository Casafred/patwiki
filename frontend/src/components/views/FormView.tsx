import { useCallback, useEffect, useState } from 'react'
import { formApi, viewApi } from '../../api'
import type { FormDefinition, FormFieldMeta, JsonObject, JsonValue, PatentView } from '../../types'
import { getErrorMessage } from '../../lib/errors'

interface FormFieldsProps {
  definition: FormDefinition
  onSubmit: (values: JsonObject) => Promise<void>
  submitting?: boolean
  successMessage?: string | null
}

function isEmpty(value: JsonValue | undefined): boolean {
  return value === undefined || value === null || value === '' || (Array.isArray(value) && value.length === 0)
}

function conditionMatches(condition: JsonObject | undefined, values: Record<string, JsonValue>): boolean {
  if (!condition) return true
  const field = typeof condition.field === 'string' ? condition.field : ''
  const actual = values[field]
  const expected = condition.value
  switch (condition.op) {
    case 'is_empty': return isEmpty(actual)
    case 'is_not_empty': return !isEmpty(actual)
    case 'contains': return String(actual ?? '').toLowerCase().includes(String(expected ?? '').toLowerCase())
    case 'starts_with': return String(actual ?? '').toLowerCase().startsWith(String(expected ?? '').toLowerCase())
    case 'ends_with': return String(actual ?? '').toLowerCase().endsWith(String(expected ?? '').toLowerCase())
    case '!=': return String(actual ?? '').toLowerCase() !== String(expected ?? '').toLowerCase()
    case '==': return String(actual ?? '').toLowerCase() === String(expected ?? '').toLowerCase()
    default: return true
  }
}

function fieldValue(patentField: FormFieldMeta | undefined, value: JsonValue | undefined): string {
  if (value === undefined || value === null) return ''
  if (patentField?.field_type === 'date') return String(value).slice(0, 10)
  return Array.isArray(value) ? value.join(',') : String(value)
}

function FormFieldInput({
  field,
  value,
  onChange,
}: {
  field: FormDefinition['fields'][number]
  value: JsonValue | undefined
  onChange: (value: JsonValue) => void
}) {
  const fieldType = field.field_type
  const textValue = fieldValue(field, value)
  if (fieldType === 'textarea' || fieldType === 'longtext') {
    return <textarea className="form-input form-view-textarea" value={textValue} onChange={event => onChange(event.target.value)} />
  }
  if (fieldType === 'select') {
    return (
      <select className="form-input" value={textValue} onChange={event => onChange(event.target.value)}>
        <option value="">请选择</option>
        {(field.options || []).map(option => <option key={option} value={option}>{option}</option>)}
      </select>
    )
  }
  if (fieldType === 'multi_select' || fieldType === 'multiselect') {
    const selected = Array.isArray(value) ? value.map(String) : []
    return (
      <select className="form-input form-view-multi-select" multiple value={selected} onChange={event => onChange(Array.from(event.target.selectedOptions, option => option.value))}>
        {(field.options || []).map(option => <option key={option} value={option}>{option}</option>)}
      </select>
    )
  }
  if (fieldType === 'boolean') {
    return <label className="form-view-checkbox"><input type="checkbox" checked={Boolean(value)} onChange={event => onChange(event.target.checked)} />是</label>
  }
  if (fieldType === 'date') {
    return <input className="form-input" type="date" value={textValue} onChange={event => onChange(event.target.value)} />
  }
  if (fieldType === 'number' || fieldType === 'rating') {
    return <input className="form-input" type="number" value={textValue} onChange={event => onChange(event.target.value === '' ? null : Number(event.target.value))} />
  }
  return <input className="form-input" type={fieldType === 'url' ? 'url' : 'text'} value={textValue} onChange={event => onChange(event.target.value)} />
}

export function FormFields({ definition, onSubmit, submitting = false, successMessage }: FormFieldsProps) {
  const [values, setValues] = useState<Record<string, JsonValue>>(() => {
    const defaults: Record<string, JsonValue> = {}
    definition.config.sections.forEach(section => section.fields.forEach(field => {
      if (field.default !== undefined) defaults[field.key] = field.default
    }))
    return defaults
  })

  const fieldMap = new Map(definition.fields.map(field => [field.key, field]))
  const updateValue = (key: string, value: JsonValue) => setValues(current => ({ ...current, [key]: value }))

  return (
    <form className={`form-view-form form-view-${definition.config.layout}`} onSubmit={event => { event.preventDefault(); void onSubmit(values) }}>
      {definition.config.sections.map(section => {
        if (!conditionMatches(section.visible_when, values)) return null
        return (
          <section className="form-view-section" key={section.title}>
            <h3>{section.title}</h3>
            <div className="form-view-fields">
              {section.fields.map(config => {
                const field = fieldMap.get(config.key)
                if (!field || !conditionMatches(config.visible_when, values)) return null
                return (
                  <label className={`form-view-field ${config.col_span === 2 ? 'form-view-field-wide' : ''}`} key={config.key}>
                    <span>{field.name}{config.required && <em> *</em>}</span>
                    <FormFieldInput
                      field={field}
                      value={values[config.key]}
                      onChange={value => updateValue(config.key, value)}
                    />
                    {field.description && <small>{field.description}</small>}
                  </label>
                )
              })}
            </div>
          </section>
        )
      })}
      {successMessage && <div className="form-view-success">{successMessage}</div>}
      <div className="form-view-actions">
        <button className="btn btn-primary" type="submit" disabled={submitting}>{submitting ? '提交中...' : definition.config.submit_label}</button>
        <button className="btn btn-secondary" type="button" onClick={() => window.location.reload()} disabled={submitting}>重置</button>
      </div>
    </form>
  )
}

interface FormViewProps {
  view: PatentView
  onViewChange: (view: PatentView) => void
}

export default function FormView({ view }: FormViewProps) {
  const [definition, setDefinition] = useState<FormDefinition | null>(null)
  const [loading, setLoading] = useState(true)
  const [submitting, setSubmitting] = useState(false)
  const [message, setMessage] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [shareMessage, setShareMessage] = useState<string | null>(null)

  const load = useCallback(async () => {
    setLoading(true)
    try {
      setDefinition(await viewApi.form(view.id))
      setError(null)
    } catch (requestError: unknown) {
      setError(getErrorMessage(requestError, '表单配置加载失败'))
    } finally {
      setLoading(false)
    }
  }, [view.id])

  useEffect(() => {
    // Load the selected form definition when its id changes.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    void load()
  }, [load])

  if (loading && !definition) {
    return <div className="loading-state"><div className="spinner" />加载表单...</div>
  }
  if (error || !definition) return <div className="form-view-error">{error || '表单配置不可用'}</div>

  const submit = async (values: JsonObject) => {
    setSubmitting(true)
    setMessage(null)
    try {
      await viewApi.submitForm(view.id, values)
      setMessage('专利已提交')
    } catch (requestError: unknown) {
      setError(getErrorMessage(requestError, '提交失败'))
    } finally {
      setSubmitting(false)
    }
  }

  const createShare = async () => {
    try {
      const link = await viewApi.createFormShare(view.id)
      const path = `${window.location.origin}/shared-form/${link.token}`
      await navigator.clipboard?.writeText(path)
      setShareMessage('分享链接已复制')
    } catch (requestError: unknown) {
      setShareMessage(getErrorMessage(requestError, '分享链接创建失败'))
    }
  }

  return (
    <div className="form-view">
      <div className="form-view-toolbar">
        <div><strong>{view.name}</strong><span>逐条录入专利数据</span></div>
        <div className="form-view-toolbar-actions">
          <button className="btn btn-secondary btn-sm" type="button" onClick={() => void createShare()}>分享表单</button>
          <button className="btn btn-ghost btn-sm" type="button" onClick={() => void load()}>刷新配置</button>
        </div>
      </div>
      {shareMessage && <div className="form-view-notice">{shareMessage}</div>}
      {error && <div className="form-view-error">{error}</div>}
      <FormFields key={definition.view_id} definition={definition} onSubmit={submit} submitting={submitting} successMessage={message} />
    </div>
  )
}

export function SharedFormView({ token }: { token: string }) {
  const [definition, setDefinition] = useState<FormDefinition | null>(null)
  const [loading, setLoading] = useState(true)
  const [submitting, setSubmitting] = useState(false)
  const [message, setMessage] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)

  const load = useCallback(async () => {
    try {
      setDefinition(await formApi.getShared(token))
    } catch (requestError: unknown) {
      setError(getErrorMessage(requestError, '公开表单不可用'))
    } finally {
      setLoading(false)
    }
  }, [token])

  useEffect(() => {
    // Load a public form definition when the token changes.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    void load()
  }, [load])

  if (loading && !definition) {
    return <div className="shared-form-page"><div className="loading-state"><div className="spinner" />加载表单...</div></div>
  }
  if (error || !definition) return <div className="shared-form-page"><div className="form-view-error">{error || '公开表单不可用'}</div></div>

  const submit = async (values: JsonObject) => {
    setSubmitting(true)
    try {
      await formApi.submitShared(token, values)
      setMessage('提交成功，感谢你的填写')
    } catch (requestError: unknown) {
      setError(getErrorMessage(requestError, '提交失败'))
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <main className="shared-form-page">
      <div className="shared-form-header"><span>PatWiki</span><h1>{definition.view_name}</h1></div>
      {error && <div className="form-view-error">{error}</div>}
      <FormFields definition={definition} onSubmit={submit} submitting={submitting} successMessage={message} />
    </main>
  )
}
