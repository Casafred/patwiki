import { useEffect, useState } from 'react'
import { fieldApi } from '../../api'
import { fieldService } from '../../services'
import type { FieldMeta } from '../../types'
import { getErrorMessage } from '../../lib/errors'

export default function FieldPolicyPanel({ onChanged }: { onChanged: () => void }) {
  const [fields, setFields] = useState<FieldMeta[]>([])
  const [key, setKey] = useState('title')
  const [edit, setEdit] = useState<FieldMeta | null>(null)
  const [busy, setBusy] = useState(false)
  const [message, setMessage] = useState('')
  const [source, setSource] = useState('')
  const [target, setTarget] = useState('')
  const [action, setAction] = useState('keep_existing')
  const [preview, setPreview] = useState<Awaited<ReturnType<typeof fieldApi.consolidate>> | null>(null)
  useEffect(() => { void fieldApi.list().then(setFields).catch(error => setMessage(getErrorMessage(error))) }, [])
  const field = edit || fields.find(item => item.key === key)
  const patch = (change: Partial<FieldMeta>) => field && setEdit({ ...field, ...change })
  const save = async () => {
    if (!field) return
    setBusy(true); setMessage('')
    try { const saved = await fieldApi.setPolicy(key, field); setFields(items => items.map(item => item.key === key ? saved : item)); setEdit(null); fieldService.invalidate(); setMessage('规则已保存') }
    catch (error) { setMessage(getErrorMessage(error)) } finally { setBusy(false) }
  }
  const consolidate = async (apply: boolean) => {
    setBusy(true); setMessage('')
    try {
      const result = await fieldApi.consolidate(source, target, action, apply); setPreview(result)
      if (result.applied) { fieldService.invalidate(); setFields(await fieldApi.list()); onChanged(); setMessage('归并完成，来源值与历史已保留'); setSource(''); setPreview(null) }
    } catch (error) { setMessage(getErrorMessage(error)) } finally { setBusy(false) }
  }
  return <section style={{ padding: '16px 0' }}>
    {message && <p role="status">{message}</p>}
    <h3>字段属性与录入规则</h3>
    <select className="form-input" value={key} onChange={event => { setKey(event.target.value); setEdit(null) }}>{fields.filter(item => item.versioned && !item.is_temporary).map(item => <option key={item.key} value={item.key}>{item.name} · {item.group_name}</option>)}</select>
    {field && <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))', gap: 12, margin: '16px 0' }}>
      <label>字段来源<select className="form-input" value={field.value_source} onChange={event => patch({ value_source: event.target.value as FieldMeta['value_source'] })}><option value="system">系统字段</option><option value="manual">人工字段</option></select></label>
      <label>变化属性<select className="form-input" value={field.value_stability} onChange={event => patch({ value_stability: event.target.value as FieldMeta['value_stability'] })}><option value="fixed">固定字段</option><option value="variable">可变字段</option></select></label>
      <label>导入冲突规则<select className="form-input" value={field.merge_policy} onChange={event => patch({ merge_policy: event.target.value as FieldMeta['merge_policy'] })}><option value="version_latest">采用新版本，保留旧值</option><option value="keep_existing">保留当前值</option><option value="fill_empty">只补充空值</option><option value="quarantine">隔离差异待处理</option></select></label>
      <label>最大长度<input className="form-input" type="number" min={1} value={field.validation_rules?.max_length ?? ''} onChange={event => patch({ validation_rules: { ...field.validation_rules, max_length: event.target.value ? Number(event.target.value) : undefined } })} /></label>
      {field.field_type === 'number' && (['minimum', 'maximum'] as const).map(bound => <label key={bound}>{bound === 'minimum' ? '最小值' : '最大值'}<input className="form-input" type="number" value={field.validation_rules?.[bound] ?? ''} onChange={event => patch({ validation_rules: { ...field.validation_rules, [bound]: event.target.value ? Number(event.target.value) : undefined } })} /></label>)}
      <label><input type="checkbox" checked={field.validation_rules?.required || false} onChange={event => patch({ validation_rules: { ...field.validation_rules, required: event.target.checked } })} />必填</label>
      <button className="btn btn-primary" disabled={busy} onClick={() => void save()}>保存规则</button>
    </div>}
    <h3 style={{ marginTop: 28 }}>自定义字段归并</h3>
    <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap' }}>
      <select aria-label="来源字段" className="form-input" value={source} onChange={event => { setSource(event.target.value); setPreview(null) }}><option value="">选择自定义字段</option>{fields.filter(item => !item.is_system && item.versioned && !item.is_temporary).map(item => <option key={item.key} value={item.key}>{item.name}</option>)}</select>
      <select aria-label="目标字段" className="form-input" value={target} onChange={event => { setTarget(event.target.value); setPreview(null) }}><option value="">选择统一字段</option>{fields.filter(item => item.editable && item.versioned && !item.is_temporary && item.key !== source).map(item => <option key={item.key} value={item.key}>{item.name}</option>)}</select>
      <select aria-label="归并规则" className="form-input" value={action} onChange={event => { setAction(event.target.value); setPreview(null) }}><option value="keep_existing">保留目标当前值</option><option value="version_latest">来源值作为新版本</option><option value="merge">融合文本或集合</option></select>
      <button className="btn btn-secondary" disabled={!source || !target || busy} onClick={() => void consolidate(false)}>预览归并</button>
    </div>
    {preview && <div style={{ marginTop: 12 }}>{preview.records} 条记录 · {preview.changed} 条更新 · {preview.conflicts} 条差异 · {preview.issues.length} 条校验问题<button className="btn btn-primary" disabled={busy || preview.issues.length > 0} onClick={() => void consolidate(true)}>确认归并并停用来源字段</button>{preview.issues.map(item => <p key={item.patent_id}>专利 {item.patent_id}：{item.reason}</p>)}</div>}
  </section>
}
