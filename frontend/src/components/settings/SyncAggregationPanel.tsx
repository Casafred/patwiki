import { useState } from 'react'
import { collaborationSyncApi } from '../../api'
import type { CollaborationPackage, PatentDatabase } from '../../types'
import { getErrorMessage } from '../../lib/errors'

export default function SyncAggregationPanel({ databases, packages }: { databases: PatentDatabase[]; packages: CollaborationPackage[] }) {
  const [name, setName] = useState('')
  const [databaseId, setDatabaseId] = useState('')
  const [selected, setSelected] = useState<string[]>([])
  const [batch, setBatch] = useState<Record<string, unknown> | null>(null)
  const [password, setPassword] = useState('')
  const [recipients, setRecipients] = useState('')
  const [message, setMessage] = useState('')
  const [busy, setBusy] = useState(false)
  const run = async (action: () => Promise<Record<string, unknown>>) => {
    setBusy(true)
    try { setBatch(await action()); setMessage('已保存') }
    catch (error) { setMessage(getErrorMessage(error)) }
    finally { setBusy(false) }
  }
  const batchUid = String(batch?.batch_uid || '')
  return <section style={{ borderTop: '1px solid #d9e0e8', paddingTop: 16, marginTop: 16 }}>
    <h4>部门汇总与发布</h4>
    <div style={{ display: 'grid', gap: 8 }}>
      <input aria-label="批次名称" placeholder="批次名称" value={name} onChange={event => setName(event.target.value)} />
      <select aria-label="部门总库" value={databaseId} onChange={event => setDatabaseId(event.target.value)}><option value="">选择部门总库</option>{databases.map(database => <option key={database.id} value={database.id}>{database.name}</option>)}</select>
      <div style={{ maxHeight: 180, overflow: 'auto' }}>{packages.filter(item => item.direction === 'inbox').map(item => <label key={item.package_uid} style={{ display: 'block', padding: 5 }}><input type="checkbox" checked={selected.includes(item.package_uid)} onChange={event => setSelected(current => event.target.checked ? [...current, item.package_uid] : current.filter(value => value !== item.package_uid))} /> {item.package_uid} · {item.count} 条 · {item.status}</label>)}</div>
      <button disabled={busy || !name.trim() || !databaseId || !selected.length} onClick={() => void run(() => collaborationSyncApi.createAggregationBatch({ name, target_database_id: Number(databaseId), package_uids: selected }))}>创建汇总批次</button>
      {batch && <>
        <strong>{String(batch.name)} · {String(batch.status)}</strong>
        <button disabled={busy || batch.status !== 'open'} onClick={() => void run(() => collaborationSyncApi.previewAggregationBatch(batchUid))}>预审</button>
        {batch.preview && <pre style={{ maxHeight: 220, overflow: 'auto', whiteSpace: 'pre-wrap' }}>{JSON.stringify(batch.preview, null, 2)}</pre>}
        <button disabled={busy || batch.status !== 'open' || !batch.preview} onClick={() => void run(() => collaborationSyncApi.submitAggregationBatch(batchUid, {}))}>提交汇总</button>
        <input aria-label="发布接收账号" value={recipients} placeholder="发布接收账号，逗号分隔" onChange={event => setRecipients(event.target.value)} />
        <input aria-label="发布密码" type="password" value={password} placeholder="发布密码" onChange={event => setPassword(event.target.value)} />
        <button disabled={busy || batch.status !== 'submitted' || password.length < 10 || !recipients.trim()} onClick={() => void run(() => collaborationSyncApi.publishAggregationBatch(batchUid, { recipient_names: recipients.split(',').map(value => value.trim()).filter(Boolean), password }))}>发布部门总库</button>
        {typeof batch.publication_package_uid === 'string' && <div>发布包：{batch.publication_package_uid}</div>}
      </>}
      {message && <div role="status">{message}</div>}
    </div>
  </section>
}
