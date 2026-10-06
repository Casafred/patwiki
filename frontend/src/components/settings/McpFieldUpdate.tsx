import { useState } from 'react'
import { syncApi } from '../../api'
import { getErrorMessage } from '../../lib/errors'
import { patentText } from '../../lib/patentText'
import type { SyncConnector, SyncUpdateBatch } from '../../types'

const FIELD_GROUPS: { label: string; keys: string[]; hint?: string }[] = [
  { label: '基础著录项', keys: ['publication_date', 'grant_date', 'legal_status', 'application_number', 'publication_number', 'title', 'abstract', 'applicant', 'assignee', 'inventor', 'filing_date', 'country', 'ipc_all', 'agent', 'priority_date', 'priority_number'] },
  { label: '说明书与权利要求', keys: ['claims', 'description_full', 'technical_problem', 'technical_solution', 'technical_effect', 'legal_status_details', 'mcp_claim_metadata', 'mcp_description_metadata'] },
  { label: '原文与附图', hint: '会产生额外调用；资源会下载并保存到当前专利的附件字段。', keys: ['mcp_pdf_original', 'mcp_abstract_figure', 'mcp_description_figures'] },
  { label: '同族与引用', keys: ['mcp_family_members', 'mcp_citation_data', 'mcp_cited_patents'] },
  { label: '法律与权属运营', keys: ['mcp_legal_event_details', 'mcp_reexamination', 'mcp_invalidation', 'mcp_transfer_events', 'mcp_license_events', 'mcp_pledge_events', 'mcp_preservation_events'] },
  { label: '价值评估', hint: '评估结果是供应商分析快照，需结合原始证据审查。', keys: ['mcp_value_evaluation', 'mcp_technology_value', 'mcp_legal_value', 'mcp_market_value', 'mcp_strategic_value'] },
  { label: '完整著录数据', keys: ['mcp_record_fields', 'mcp_priority_claims', 'mcp_classification_details', 'mcp_party_details'] },
]

function candidateText(value: unknown): string {
  if (value === null || value === undefined) return ''
  if (typeof value === 'object') {
    try { return JSON.stringify(value, null, 2) } catch { return String(value) }
  }
  return patentText(String(value))
}

export default function McpFieldUpdate({ connectors, databaseId, fields, selectedFields, onToggle, onUpdated }: {
  connectors: SyncConnector[]; databaseId: number | null; fields: readonly (readonly [string, string])[]
  selectedFields: string[]; onToggle: (key: string, checked: boolean) => void; onUpdated: () => void
}) {
  const available = connectors.filter(item => item.enabled && item.transport === 'mcp')
  const [connectorId, setConnectorId] = useState(0)
  const connector = available.find(item => item.id === connectorId) || available[0]
  const fieldMap = new Map(fields)
  const [identifier, setIdentifier] = useState('')
  const [busy, setBusy] = useState(false)
  const [message, setMessage] = useState('')
  const [batch, setBatch] = useState<SyncUpdateBatch | null>(null)
  const [selection, setSelection] = useState<Record<number, string[]>>({})
  const preview = async () => {
    if (!databaseId || !connector) return
    setBusy(true); setMessage(''); setBatch(null)
    try {
      const matches = await syncApi.resolvePublications({ database_id: databaseId, publications: [identifier.trim()] })
      if (!matches.matched.length) throw new Error('当前库未找到该专利，请输入当前库已有专利的公开号')
      const result = await syncApi.previewUpdate({ connector_id: connector.id, database_id: databaseId, patent_ids: matches.matched.map(item => item.patent_id), fields: selectedFields })
      setBatch(result)
      setSelection(Object.fromEntries(result.items.map(item => [item.id, item.changed_fields])))
    } catch (error) { setMessage(getErrorMessage(error, '获取失败')) }
    finally { setBusy(false) }
  }
  const confirm = async () => {
    if (!batch) return
    setBusy(true)
    try {
      const result = await syncApi.confirmUpdate(batch.id, batch.items.filter(item => item.status === 'ready').map(item => ({ item_id: item.id, fields: selection[item.id] || [] })))
      setMessage(`已更新 ${result.items.filter(item => item.status === 'updated').length} 件专利`)
      setBatch(null); onUpdated()
    } catch (error) { setMessage(getErrorMessage(error, '更新失败')) }
    finally { setBusy(false) }
  }
  return <section className="mcp-panel">
    <div className="section-heading"><h3>MCP 字段映射与一键更新</h3><span>{selectedFields.length} 个目标字段</span></div>
    <fieldset className="mcp-target-fields"><legend>获取并回填的字段</legend>
      <p>只会调用勾选的 MCP 工具；PDF、附图、法律运营和价值评估可能产生额外供应商调用。</p>
      {FIELD_GROUPS.map(group => {
        const groupFields = group.keys.map(key => [key, fieldMap.get(key) || key] as const).filter(([key]) => fields.some(field => field[0] === key))
        if (!groupFields.length) return null
        return <div className="mcp-field-group" key={group.label}>
          <div className="mcp-field-group-title"><strong>{group.label}</strong>{group.hint && <small>{group.hint}</small>}</div>
          <div className="mcp-target-fields-grid">{groupFields.map(([key, label]) => <label key={key} title={key}><input type="checkbox" disabled={busy} checked={selectedFields.includes(key)} onChange={event => onToggle(key, event.target.checked)} />{label}<small>{key}</small></label>)}</div>
        </div>
      })}
    </fieldset>
    <div className="mcp-inline-form">
      {available.length > 1 && <label>连接器<select className="form-input" disabled={busy} value={connector?.id || ''} onChange={event => setConnectorId(Number(event.target.value))}>{available.map(item => <option key={item.id} value={item.id}>{item.name}</option>)}</select></label>}
      <label className="mcp-inline-grow">专利公开号<input className="form-input" disabled={busy} value={identifier} onChange={event => setIdentifier(event.target.value)} placeholder="例如 CN123456789A" /></label>
      <button className="btn btn-primary" disabled={busy || !connector || !databaseId || !identifier.trim() || !selectedFields.length} onClick={() => void preview()}>{busy ? '获取中...' : 'MCP 一键更新'}</button>
    </div>
    {message && <div role="status" className="mcp-tools-hint">{message}</div>}
    {batch && <div className="mcp-map-preview">
      {batch.items.map(item => <div key={item.id}>
        {item.error_message && <div className="error-message">{item.error_message}</div>}
        {item.status === 'no_change' && <div>所选字段与当前内容一致</div>}
        {item.changed_fields.map(key => <div key={key}>
          <label><input type="checkbox" disabled={busy} checked={(selection[item.id] || []).includes(key)} onChange={event => setSelection(previous => ({ ...previous, [item.id]: event.target.checked ? [...(previous[item.id] || []), key] : (previous[item.id] || []).filter(field => field !== key) }))} />{fields.find(field => field[0] === key)?.[1] || key}</label>
          <div className="tech-claims-raw">{candidateText(item.candidate_fields[key])}</div>
        </div>)}
      </div>)}
      <div className="mcp-map-preview-actions"><button className="btn btn-primary" disabled={busy || !batch.items.some(item => item.status === 'ready' && selection[item.id]?.length)} onClick={() => void confirm()}>确认覆盖所选字段</button><button className="btn" disabled={busy} onClick={() => { void syncApi.cancelUpdate(batch.id).catch(error => setMessage(getErrorMessage(error))); setBatch(null) }}>取消</button></div>
    </div>}
  </section>
}
