import { useEffect, useState } from 'react'
import { fieldApi } from '../../api'
import type { FieldMeta, FieldVersions } from '../../types'
import { getErrorMessage } from '../../lib/errors'
import { formatApiDateTime } from '../../lib/date'

export default function FieldVersionsPanel({ patentId, onChanged }: { patentId: number; onChanged: () => void }) {
  const [fields, setFields] = useState<FieldMeta[]>([])
  const [key, setKey] = useState('title')
  const [data, setData] = useState<FieldVersions | null>(null)
  const [value, setValue] = useState('')
  const [busy, setBusy] = useState(true)
  const [loadedPatentId, setLoadedPatentId] = useState<number | null>(null)
  const [error, setError] = useState('')
  const [selected, setSelected] = useState<string[]>([])
  const [refresh, setRefresh] = useState(0)
  useEffect(() => { void fieldApi.list().then(setFields).catch(error => setError(getErrorMessage(error))) }, [])
  useEffect(() => {
    let active = true
    void fieldApi.versions(patentId, key).then(next => {
      if (active) { setData(next); setLoadedPatentId(patentId); setValue(next.current_value || ''); setSelected([]) }
    }).catch(error => { if (active) setError(getErrorMessage(error)) }).finally(() => { if (active) setBusy(false) })
    return () => { active = false }
  }, [patentId, key, refresh])
  const save = async () => {
    if (!data) return
    setBusy(true); setError('')
    try { setData(await fieldApi.saveVersion(patentId, key, value || null, data.current_value)); onChanged(); setSelected([]) }
    catch (error) { setError(getErrorMessage(error)) } finally { setBusy(false) }
  }
  const mergeable = ['text', 'longtext', 'textarea', 'ai_field', 'multiselect', 'multi_select'].includes(data?.field.field_type || '') && !['application_number', 'publication_number', 'grant_number', 'country'].includes(key)
  const merge = () => {
    if (['multiselect', 'multi_select'].includes(data?.field.field_type || '')) {
      try { setValue(JSON.stringify([...new Set(selected.flatMap(text => JSON.parse(text) as unknown[]))])); return }
      catch { setError('集合值格式不正确'); return }
    }
    setValue(selected.join('\n\n'))
  }
  return <section>
    <div style={{ display: 'flex', gap: 12, marginBottom: 16 }}><select aria-label="字段版本" className="form-input" value={key} disabled={busy} onChange={event => setKey(event.target.value)}>{fields.filter(item => item.versioned && !item.is_temporary).map(item => <option key={item.key} value={item.key}>{item.name} · {item.value_source === 'manual' ? '人工' : '系统'} · {item.value_stability === 'variable' ? '可变' : '固定'}</option>)}</select><button className="btn btn-secondary" disabled={busy} onClick={() => setRefresh(previous => previous + 1)}>刷新</button></div>
    {error && <p role="alert" style={{ color: '#b91c1c' }}>{error}</p>}
    {data && data.field.key === key && loadedPatentId === patentId && <>
      <label>当前值{data.field.field_type === 'boolean' ? <input type="checkbox" checked={value === 'true'} disabled={busy || !data.field.editable} onChange={event => setValue(String(event.target.checked))} /> : ['number', 'date'].includes(data.field.field_type) ? <input className="form-input" type={data.field.field_type} disabled={busy || !data.field.editable} value={value} onChange={event => setValue(event.target.value)} /> : data.field.field_type === 'select' ? <select className="form-input" value={value} disabled={busy || !data.field.editable} onChange={event => setValue(event.target.value)}><option value="">空值</option>{data.field.options?.map(option => <option key={option} value={option}>{option}</option>)}</select> : <textarea className="form-input" rows={5} disabled={busy || !data.field.editable} value={value} onChange={event => setValue(event.target.value)} />}</label>
      <div style={{ display: 'flex', gap: 12, margin: '12px 0 24px' }}><button className="btn btn-primary" disabled={busy || !data.field.editable || value === (data.current_value || '')} onClick={() => void save()}>保存为新版本</button>{mergeable && <button className="btn btn-secondary" disabled={selected.length < 2} onClick={merge}>合并所选值</button>}</div>
      <h3>字段演变 · {data.versions.length} 条记录</h3>
      <div style={{ overflowX: 'auto' }}><table className="data-grid" style={{ width: '100%', tableLayout: 'fixed', minWidth: 580 }}><thead><tr><th style={{ width: 40 }}></th><th style={{ width: 170 }}>时间与来源</th><th>旧值</th><th>新值</th><th style={{ width: 75 }}>操作</th></tr></thead><tbody>{data.versions.map(item => <tr key={item.id}><td>{mergeable && <input aria-label="选择版本值" type="checkbox" checked={selected.includes(item.value || '')} onChange={() => setSelected(previous => previous.includes(item.value || '') ? previous.filter(text => text !== item.value) : [...previous, item.value || ''])} />}</td><td>{formatApiDateTime(item.created_at)}<br />{item.source_label || item.source}{item.import_batch_id && <div>批次 {item.import_batch_id}{item.source_row ? ` · 行 ${item.source_row}` : ''}</div>}</td><td style={{ whiteSpace: 'pre-wrap', overflowWrap: 'anywhere' }}>{item.old_value ?? '空值'}</td><td style={{ whiteSpace: 'pre-wrap', overflowWrap: 'anywhere' }}>{item.value ?? '空值'}</td><td><button className="btn btn-secondary" disabled={busy || !data.field.editable} onClick={() => setValue(item.value || '')}>选用</button><button className="btn btn-secondary" disabled={busy || !data.field.editable} onClick={() => setValue(item.old_value || '')}>回退</button></td></tr>)}</tbody></table></div>
      <h3 style={{ marginTop: 24 }}>导入候选与处理记录 · {data.imports.length} 条</h3>
      {data.imports.map(item => <div key={item.id} style={{ padding: '10px 0', borderBottom: '1px solid #e2e8f0', overflowWrap: 'anywhere' }}><div>{item.filename} · 批次 {item.batch_id} · {item.status} · {item.decision} · {formatApiDateTime(item.created_at)}</div><div style={{ whiteSpace: 'pre-wrap', margin: '6px 0' }}>{item.value}</div><button className="btn btn-secondary" disabled={busy || !data.field.editable} onClick={() => setValue(item.value || '')}>选用来源值</button></div>)}
    </>}
  </section>
}
