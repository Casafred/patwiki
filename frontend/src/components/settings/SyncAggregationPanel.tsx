import { useEffect, useState } from 'react'
import { collaborationSyncApi, syncApi } from '../../api'
import type { CollaborationPackage, PatentDatabase, SyncConnector, SyncUpdateBatch } from '../../types'
import { getErrorMessage } from '../../lib/errors'

type Conflict = { package_uid: string; entity_uid: string; field_key: string; base_value: unknown; local_value: unknown; remote_value: unknown }

export default function SyncAggregationPanel({ databases, packages }: { databases: PatentDatabase[]; packages: CollaborationPackage[] }) {
  const [name, setName] = useState('')
  const [databaseId, setDatabaseId] = useState('')
  const [selected, setSelected] = useState<string[]>([])
  const [batch, setBatch] = useState<Record<string, unknown> | null>(null)
  const [password, setPassword] = useState('')
  const [recipients, setRecipients] = useState('')
  const [message, setMessage] = useState('')
  const [busy, setBusy] = useState(false)
  const [decisions, setDecisions] = useState<Record<string, 'local' | 'remote' | 'manual'>>({})
  const [manualValues, setManualValues] = useState<Record<string, string>>({})
  const [reasons, setReasons] = useState<Record<string, string>>({})
  const [connectors, setConnectors] = useState<SyncConnector[]>([])
  const [connectorId, setConnectorId] = useState('')
  const [updateBatch, setUpdateBatch] = useState<SyncUpdateBatch | null>(null)
  const [updateChoices, setUpdateChoices] = useState<Record<number, string[]>>({})
  useEffect(() => { void syncApi.connectors().then(result => setConnectors(result.items.filter(item => item.enabled))).catch(error => setMessage(getErrorMessage(error))) }, [])
  const runUpdate = async (confirm: boolean) => {
    setBusy(true)
    try {
      const result = confirm
        ? await collaborationSyncApi.confirmAggregationUpdates(batchUid, Object.entries(updateChoices).map(([id, selectedFields]) => ({ item_id: Number(id), fields: selectedFields })))
        : await collaborationSyncApi.previewAggregationUpdates(batchUid, Number(connectorId))
      setUpdateBatch(result); if (!confirm) setUpdateChoices({}); setMessage(confirm ? '统一更新已审核' : '统一更新查询完成')
    } catch (error) { setMessage(getErrorMessage(error)) } finally { setBusy(false) }
  }
  const run = async (action: () => Promise<Record<string, unknown>>) => {
    setBusy(true)
    try { setBatch(await action()); setMessage('已保存') }
    catch (error) { setMessage(getErrorMessage(error)) }
    finally { setBusy(false) }
  }
  const batchUid = String(batch?.batch_uid || '')
  const preview = batch?.preview as { conflicts?: Conflict[]; auto_merge?: number; new?: number; deleted?: number; conflict?: number; unmatched?: number; unchanged?: number } | undefined
  const conflictKey = (item: Conflict) => `${item.package_uid}:${item.entity_uid}:${item.field_key}`
  const submit = async () => {
    const choices = (preview?.conflicts || []).flatMap(item => {
      const key = conflictKey(item)
      const choice = decisions[key]
      if (!choice) return []
      const raw = manualValues[key] || ''
      let value: unknown = undefined
      if (choice === 'manual') {
        const reference = item.remote_value ?? item.local_value
        value = typeof reference === 'string' || reference == null ? raw : JSON.parse(raw)
        if (reference != null && typeof reference !== typeof value) throw new Error('手工合并值的类型与字段不一致')
      }
      return [{ entity_uid: item.entity_uid, field_key: item.field_key, package_uid: item.package_uid, choice, value, reason: reasons[key] }]
    })
    return collaborationSyncApi.submitAggregationBatch(batchUid, { decisions: choices })
  }
  return <section style={{ borderTop: '1px solid #d9e0e8', paddingTop: 16, marginTop: 16 }}>
    <h4>部门汇总与发布</h4>
    <div style={{ display: 'grid', gap: 8 }}>
      <input aria-label="批次名称" placeholder="批次名称" value={name} onChange={event => setName(event.target.value)} />
      <select aria-label="部门总库" value={databaseId} onChange={event => setDatabaseId(event.target.value)}><option value="">选择部门总库</option>{databases.map(database => <option key={database.id} value={database.id}>{database.name}</option>)}</select>
      <div style={{ maxHeight: 180, overflow: 'auto' }}>{packages.filter(item => item.direction === 'inbox').map(item => <label key={item.package_uid} style={{ display: 'block', padding: 5 }}><input type="checkbox" checked={selected.includes(item.package_uid)} onChange={event => setSelected(current => event.target.checked ? [...current, item.package_uid] : current.filter(value => value !== item.package_uid))} /> {item.package_uid} · {item.count} 条 · {item.status}</label>)}</div>
      <button disabled={busy || !name.trim() || !databaseId || !selected.length} onClick={() => void run(() => collaborationSyncApi.createAggregationBatch({ name, target_database_id: Number(databaseId), package_uids: selected }))}>创建汇总批次</button>
      {batch && <>
        <strong>{String(batch.name)} · {String(batch.status)}</strong>
        <button disabled={busy || batch.status === 'published'} onClick={() => void run(() => collaborationSyncApi.previewAggregationBatch(batchUid))}>预审 / 刷新待审冲突</button>
        {preview && <div>自动合并 {preview.auto_merge || 0} · 新增 {preview.new || 0} · 删除 {preview.deleted || 0} · 冲突 {preview.conflict || 0} · 未匹配 {preview.unmatched || 0} · 无变化 {preview.unchanged || 0}</div>}
        {(preview?.conflicts || []).map(item => <div key={conflictKey(item)} style={{ borderTop: '1px solid #d9e0e8', paddingTop: 8, display: 'grid', gap: 6 }}>
          <strong style={{ fontSize: 12 }}>{item.field_key} · {item.entity_uid}</strong>
          <span style={{ fontSize: 11, overflowWrap: 'anywhere' }}>来源：{item.package_uid}</span>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(160px, 1fr))', gap: 8, fontSize: 12, overflowWrap: 'anywhere' }}><span>基线：{JSON.stringify(item.base_value)}</span><span>总库：{JSON.stringify(item.local_value)}</span><span>成员：{JSON.stringify(item.remote_value)}</span></div>
          <select aria-label={`处理 ${item.field_key} 冲突`} value={decisions[conflictKey(item)] || ''} onChange={event => setDecisions(current => { const next = { ...current }; if (event.target.value) next[conflictKey(item)] = event.target.value as 'local' | 'remote' | 'manual'; else delete next[conflictKey(item)]; return next })}><option value="">暂不处理</option><option value="local">保留总库值</option><option value="remote">接受此成员值</option><option value="manual">手工合并</option></select>
          {decisions[conflictKey(item)] === 'manual' && <textarea aria-label="手工最终值" value={manualValues[conflictKey(item)] || ''} placeholder="最终值" onChange={event => setManualValues(current => ({ ...current, [conflictKey(item)]: event.target.value }))} />}
          <input aria-label="处理理由" placeholder="处理理由" value={reasons[conflictKey(item)] || ''} onChange={event => setReasons(current => ({ ...current, [conflictKey(item)]: event.target.value }))} />
        </div>)}
        <button disabled={busy || batch.status === 'published' || !batch.preview} onClick={() => void run(submit)}>提交汇总 / 保存冲突处理</button>
        {batch.status === 'submitted' && <section style={{ borderTop: '1px solid #d9e0e8', paddingTop: 12 }}>
          <h5>统一更新专利</h5>
          <select aria-label="统一更新连接器" value={connectorId} onChange={event => setConnectorId(event.target.value)}><option value="">选择数据连接器</option>{connectors.map(item => <option key={item.id} value={item.id}>{item.name}</option>)}</select>
          <button disabled={busy || !connectorId} onClick={() => void runUpdate(false)}>查询成员更新请求</button>
          {updateBatch?.items.map(item => <div key={item.id} style={{ borderTop: '1px solid #e5e7eb', padding: '8px 0', overflowWrap: 'anywhere' }}>
            <strong>专利 #{item.patent_id} · {item.status}</strong>{item.error_message && <p role="alert">{item.error_message}</p>}
            {item.changed_fields.map(field => <label key={field} style={{ display: 'block', fontSize: 12, padding: 4 }}><input type="checkbox" disabled={updateBatch.status !== 'preview'} checked={(updateChoices[item.id] || []).includes(field)} onChange={event => setUpdateChoices(current => ({ ...current, [item.id]: event.target.checked ? [...(current[item.id] || []), field] : (current[item.id] || []).filter(value => value !== field) }))} /> {field}: {JSON.stringify(item.current_fields[field])} → {JSON.stringify(item.candidate_fields[field])}</label>)}
          </div>)}
          {updateBatch?.status === 'preview' && <button disabled={busy} onClick={() => void runUpdate(true)}>确认选中的公共字段更新</button>}
        </section>}
        <input aria-label="发布接收账号" value={recipients} placeholder="发布接收账号，逗号分隔" onChange={event => setRecipients(event.target.value)} />
        <input aria-label="发布密码" type="password" value={password} placeholder="发布密码" onChange={event => setPassword(event.target.value)} />
        <button disabled={busy || batch.status !== 'submitted' || password.length < 10} onClick={() => void run(() => collaborationSyncApi.publishAggregationBatch(batchUid, { recipient_names: recipients.split(',').map(value => value.trim()).filter(Boolean), password }))}>发布部门总库</button>
        {typeof batch.publication_package_uid === 'string' && <div>发布包：{batch.publication_package_uid}</div>}
      </>}
      {message && <div role="status">{message}</div>}
    </div>
  </section>
}
