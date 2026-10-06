import { useState } from 'react'
import { syncApi } from '../../api'
import { getErrorMessage } from '../../lib/errors'
import type { JsonObject, JsonValue, McpToolInfo, SyncConnector, SyncUpdateBatch } from '../../types'

type Property = { type?: string; description?: string; enum?: unknown[]; items?: { type?: string }; title?: string }

const PRESETS: { label: string; hint: string; match: string[] }[] = [
  { label: '检索专利', hint: '按关键词 / 检索式搜索', match: ['search', 'query', '检索'] },
  { label: '获取专利著录项', hint: '按公开号或申请号取回详情', match: ['detail', 'fetch', 'get', '著录', 'patent'] },
  { label: '查询法律状态', hint: '取回法律事件与当前状态', match: ['legal', 'status', '法律', 'event'] },
]

const FIELD_LABELS: Record<string, string> = {
  publication_number: '公开号', application_number: '申请号', title: '标题', abstract: '摘要',
  applicant: '申请人', assignee: '受让人', inventor: '发明人', agent: '代理人',
  filing_date: '申请日', publication_date: '公开日', grant_date: '授权日', country: '国家/地区',
  ipc_all: 'IPC 分类', priority_number: '优先权号', priority_date: '优先权日',
  claims: '权利要求全文', description_full: '说明书全文',
  technical_problem: '技术问题', technical_solution: '技术方案', technical_effect: '技术效果',
  legal_status: '法律状态', legal_status_details: '法律状态详情',
}

const ONE_CLICK_FIELDS: Array<[string, string]> = [
  ['publication_date', '公开日'], ['grant_date', '授权日'], ['legal_status', '法律状态'],
  ['application_number', '申请号'], ['publication_number', '公开号'], ['title', '标题'],
  ['abstract', '摘要'], ['applicant', '申请人'], ['assignee', '受让人'], ['inventor', '发明人'],
  ['filing_date', '申请日'], ['country', '国家/地区'], ['ipc_all', 'IPC 分类'], ['agent', '代理人'],
  ['priority_date', '优先权日'], ['priority_number', '优先权号'], ['claims', '权利要求全文'],
  ['description_full', '说明书全文'], ['technical_problem', '技术问题'],
  ['technical_solution', '技术方案'], ['technical_effect', '技术效果'],
]

function fieldLabel(key: string): string {
  return FIELD_LABELS[key] || key
}

function scalarKeys(items: JsonObject[]): string[] {
  const first = items[0] || {}
  return Object.keys(first).filter(key => {
    const value = first[key]
    return value === null || ['string', 'number', 'boolean'].includes(typeof value)
  }).slice(0, 8)
}

function readable(value: JsonValue | undefined): string {
  if (value === null || value === undefined) return ''
  if (typeof value === 'object') return JSON.stringify(value)
  return String(value)
}

function ResultView({ result }: { result: JsonObject }) {
  const data = result.data
  const items = Array.isArray(data) ? (data as JsonObject[]) : null
  const keys = items && items.length ? scalarKeys(items) : []
  return <div className="mcp-tool-result">
    <div className="mcp-tool-result-head">
      <strong>执行结果</strong>
      <span>来源快照 #{String(result.snapshot_id ?? '-')} · {String(result.service ?? '')} / {String(result.tool ?? '')}</span>
    </div>
    {items && items.length > 0 && keys.length > 0
      ? <div className="mcp-tool-result-table">
        <table>
          <thead><tr>{keys.map(key => <th key={key}>{key}</th>)}</tr></thead>
          <tbody>{items.slice(0, 50).map((row, index) => <tr key={index}>{keys.map(key => <td key={key} title={readable(row[key])}>{readable(row[key])}</td>)}</tr>)}</tbody>
        </table>
        {items.length > 50 && <div className="mcp-tool-result-more">仅显示前 50 条，共 {items.length} 条</div>}
      </div>
      : <dl className="mcp-tool-result-kv">{Object.entries(result).filter(([key]) => key !== 'data').map(([key, value]) => <div key={key}><dt>{key}</dt><dd>{readable(value)}</dd></div>)}</dl>}
    <details>
      <summary>查看原始返回内容</summary>
      <pre>{JSON.stringify(data, null, 2)}</pre>
    </details>
  </div>
}

function UpdatePreview({ batch, busy, onConfirm, onCancel }: {
  batch: SyncUpdateBatch
  busy: boolean
  onConfirm: (items: { item_id: number; fields: string[] }[]) => void
  onCancel: () => void
}) {
  const [selected, setSelected] = useState<Record<number, string[]>>(() => {
    const initial: Record<number, string[]> = {}
    for (const item of batch.items) initial[item.id] = item.changed_fields
    return initial
  })
  const ready = batch.items.filter(item => item.status === 'ready' || item.status === 'no_change')
  const toggle = (itemId: number, key: string, checked: boolean) => {
    setSelected(previous => {
      const current = previous[itemId] || []
      return { ...previous, [itemId]: checked ? [...current, key] : current.filter(field => field !== key) }
    })
  }
  return <div className="mcp-map-preview">
    <div className="mcp-tool-result-head"><strong>写入预览</strong><span>批次 #{batch.id} · 状态 {batch.status}</span></div>
    {ready.length === 0 && <p className="mcp-tools-hint">没有可写入的字段变更。</p>}
    {ready.map(item => <div key={item.id} className="mcp-map-preview-item">
      <div className="mcp-map-preview-title">专利 #{item.patent_id} · {item.status}{item.error_message ? ` · ${item.error_message}` : ''}</div>
      {item.changed_fields.length === 0
        ? <p className="mcp-tools-hint">字段与本地一致，无需写入。</p>
        : <ul className="mcp-map-preview-fields">
          {item.changed_fields.map(key => <li key={key}>
            <label>
              <input type="checkbox" disabled={busy} checked={(selected[item.id] || []).includes(key)} onChange={event => toggle(item.id, key, event.target.checked)} />
              <span className="mcp-map-field-name">{fieldLabel(key)}<small>{key}</small></span>
            </label>
            <div className="mcp-map-field-diff">
              <span className="mcp-map-field-before">{readable(item.current_fields[key] as JsonValue)}</span>
              <span className="mcp-map-field-arrow">→</span>
              <span className="mcp-map-field-after">{readable(item.candidate_fields[key] as JsonValue)}</span>
            </div>
          </li>)}
        </ul>}
    </div>)}
    <div className="mcp-map-preview-actions">
      <button className="btn btn-primary" disabled={busy || ready.length === 0} onClick={() => onConfirm(ready.map(item => ({ item_id: item.id, fields: selected[item.id] || [] })))}>{busy ? '写入中…' : '确认写入所选字段'}</button>
      <button className="btn" disabled={busy} onClick={onCancel}>取消</button>
    </div>
  </div>
}

export default function McpToolWorkbench({ connectors, databaseId, onUpdated }: { connectors: SyncConnector[]; databaseId?: number | null; onUpdated?: () => void }) {
  const available = connectors.filter(item => item.enabled && item.transport === 'mcp')
  const [connectorId, setConnectorId] = useState<number>(0)
  const connector = available.find(item => item.id === connectorId) || available[0]
  const services = (connector?.mcp_catalog?.services || []) as JsonObject[]
  const [serviceName, setServiceName] = useState('')
  const service = services.find(item => item.service === serviceName) || services[0]
  const tools = (service?.tools || []) as unknown as McpToolInfo[]
  const [toolName, setToolName] = useState('')
  const tool = tools.find(item => item.name === toolName) || tools[0]
  const [values, setValues] = useState<Record<string, string>>({})
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [message, setMessage] = useState('')
  const [result, setResult] = useState<JsonObject | null>(null)

  const [updateIdentifierType, setUpdateIdentifierType] = useState('publication_number')
  const [updateIdentifier, setUpdateIdentifier] = useState('')
  const [updating, setUpdating] = useState(false)
  const [updateFields, setUpdateFields] = useState<string[]>(['publication_date', 'legal_status', 'title', 'abstract'])

  const [mapIdentifier, setMapIdentifier] = useState('')
  const [mapping, setMapping] = useState(false)
  const [mapBatch, setMapBatch] = useState<SyncUpdateBatch | null>(null)
  const [confirming, setConfirming] = useState(false)

  const properties = (tool?.inputSchema?.properties || {}) as Record<string, Property>
  const required = (tool?.inputSchema?.required || []) as string[]
  const requiredEntries = Object.entries(properties).filter(([key]) => required.includes(key))
  const optionalEntries = Object.entries(properties).filter(([key]) => !required.includes(key))
  const mappableFields = tool?.mappable_fields || []
  const presetTools = PRESETS.map(preset => ({
    ...preset,
    tool: tools.find(item => preset.match.some(keyword => item.name.toLowerCase().includes(keyword))),
  }))

  const selectTool = (nextTool: McpToolInfo) => {
    setToolName(nextTool.name); setValues({}); setError(''); setResult(null); setMapBatch(null)
  }
  const reset = () => { setValues({}); setError(''); setResult(null); setMapBatch(null) }

  const buildArguments = (): JsonObject => {
    const arguments_: JsonObject = {}
    for (const [key, property] of Object.entries(properties)) {
      const value = values[key]?.trim()
      if (!value) {
        if (required.includes(key)) throw new Error(`请填写 ${property.title || key}`)
        continue
      }
      if (property.type === 'array') {
        arguments_[key] = value.startsWith('[') ? JSON.parse(value) : property.items?.type === 'string' ? value.split(/[\n,，;；]+/).map(item => item.trim()).filter(Boolean) : JSON.parse(value)
      } else if (property.type === 'object') {
        arguments_[key] = JSON.parse(value)
      } else if (property.type === 'integer' || property.type === 'number') {
        const number = Number(value)
        if (!Number.isFinite(number) || (property.type === 'integer' && !Number.isInteger(number))) throw new Error(`${key} 必须是有效数字`)
        arguments_[key] = number
      } else if (property.type === 'boolean') arguments_[key] = value === 'true'
      else arguments_[key] = value
    }
    return arguments_
  }

  const execute = async () => {
    if (!connector || !service || !tool) return
    setBusy(true); setError(''); setResult(null); setMapBatch(null)
    try {
      const arguments_ = buildArguments()
      setResult(await syncApi.callConnectorTool(connector.id, { service: String(service.service), tool: tool.name, arguments: arguments_ }))
    } catch (err) { setError(getErrorMessage(err, '工具调用失败')) }
    finally { setBusy(false) }
  }

  const mapToFields = async () => {
    if (!connector || !service || !tool || !databaseId) return
    if (!mapIdentifier.trim()) { setError('请填写要写入的本地专利公开号'); return }
    setMapping(true); setError(''); setMessage(''); setMapBatch(null)
    try {
      const resolved = await syncApi.resolvePublications({ database_id: databaseId, publications: [mapIdentifier.trim()] })
      const match = resolved.matched[0]
      if (!match) throw new Error(`本地库中未找到 ${mapIdentifier.trim()}，请先在当前库中建立该专利`)
      const arguments_ = buildArguments()
      const batch = await syncApi.mapToolResultPreview(connector.id, {
        database_id: databaseId,
        patent_id: match.patent_id,
        service: String(service.service),
        tool: tool.name,
        arguments: arguments_,
      })
      setMapBatch(batch)
    } catch (err) { setError(getErrorMessage(err, '映射到字段失败')) }
    finally { setMapping(false) }
  }

  const confirmMap = async (items: { item_id: number; fields: string[] }[]) => {
    if (!mapBatch) return
    setConfirming(true); setError(''); setMessage('')
    try {
      const batch = await syncApi.confirmUpdate(mapBatch.id, items)
      const written = batch.items.reduce((total, item) => total + (item.status === 'updated' ? item.selected_fields.length : 0), 0)
      setMessage(`已写入 ${written} 个字段，并保留来源快照与审查记录`)
      setMapBatch(null)
      onUpdated?.()
    } catch (err) { setError(getErrorMessage(err, '写入字段失败')) }
    finally { setConfirming(false) }
  }

  const cancelMap = async () => {
    if (!mapBatch) return
    try { await syncApi.cancelUpdate(mapBatch.id) } catch { /* 取消失败不影响界面重置 */ }
    setMapBatch(null)
  }

  const runOneClickUpdate = async () => {
    if (!connector || !updateIdentifier.trim()) return
    setUpdating(true); setError(''); setMessage('')
    try {
      const run = await syncApi.refreshPatent({
        connector_id: connector.id,
        identifier_type: updateIdentifierType,
        identifier: updateIdentifier.trim(),
        database_id: databaseId ?? undefined,
        fields: updateFields,
      })
      if (run.error_message) setError(`更新失败：${run.error_message}`)
      else setMessage(`已从 ${connector.name} 更新 ${updateIdentifier.trim()}：变更 ${String(run.counts?.auto_applied ?? 0)} 项，待审查 ${String(run.counts?.review ?? 0)} 项`)
      setUpdateIdentifier('')
      onUpdated?.()
    } catch (err) { setError(getErrorMessage(err, '一键更新失败')) }
    finally { setUpdating(false) }
  }

  if (!available.length) {
    return <section className="mcp-panel mcp-tools-tab"><div className="empty-state">还没有可用的 HimmPat MCP 连接器。请先在“连接器”页接入并启用。</div></section>
  }

  return <section className="mcp-tools-tab">
    <div className="mcp-tools-block">
      <div className="section-heading"><h3>一键更新基础信息</h3><span>按公开号 / 申请号刷新单件专利</span></div>
      <div className="mcp-inline-form">
        <label>连接器<select className="form-input" disabled={updating} value={connector?.id || ''} onChange={event => setConnectorId(Number(event.target.value))}>{available.map(item => <option key={item.id} value={item.id}>{item.name}</option>)}</select></label>
        <label>标识类型<select className="form-input" disabled={updating} value={updateIdentifierType} onChange={event => setUpdateIdentifierType(event.target.value)}><option value="publication_number">公开号</option><option value="application_number">申请号</option></select></label>
        <label className="mcp-inline-grow">号码<input className="form-input" disabled={updating} value={updateIdentifier} onChange={event => setUpdateIdentifier(event.target.value)} placeholder="例如 CN123456789A" /></label>
        <button className="btn btn-primary" disabled={updating || !updateIdentifier.trim()} onClick={() => void runOneClickUpdate()}>{updating ? '更新中…' : '更新到当前库'}</button>
      </div>
      <fieldset className="mcp-target-fields">
        <legend>更新字段</legend>
        <p>勾选后才会回填当前库；技术问题、技术方案、技术效果和权利要求也可在这里一并获取。</p>
        <div className="mcp-target-fields-grid">{ONE_CLICK_FIELDS.map(([key, label]) => <label key={key}><input type="checkbox" checked={updateFields.includes(key)} onChange={event => setUpdateFields(previous => event.target.checked ? [...previous, key] : previous.filter(item => item !== key))} />{label}<small>{key}</small></label>)}</div>
      </fieldset>
    </div>

    <div className="mcp-tools-block">
      <div className="section-heading"><h3>工具调用</h3><span>{tools.length} 个工具 · 常用操作一键选取</span></div>
      <div className="mcp-preset-row">{presetTools.map(preset => <button key={preset.label} type="button" className="mcp-preset" disabled={busy || !preset.tool} onClick={() => preset.tool && selectTool(preset.tool)}><strong>{preset.label}</strong><small>{preset.tool ? preset.tool.name : preset.hint}</small></button>)}</div>
      <div className="mcp-inline-form">
        <label>服务<select className="form-input" disabled={busy} value={String(service?.service || '')} onChange={event => { setServiceName(event.target.value); setToolName(''); reset() }}>{services.map(item => <option key={String(item.service)} value={String(item.service)}>{String(item.service)}</option>)}</select></label>
        <label className="mcp-inline-grow">工具<select className="form-input" disabled={busy} value={tool?.name || ''} onChange={event => { setToolName(event.target.value); reset() }}>{tools.map(item => <option key={item.name} value={item.name}>{item.name}</option>)}</select></label>
      </div>
      {tool?.description && <p className="mcp-tools-hint">{tool.description}</p>}
      <div className="mcp-form-grid">
        {requiredEntries.map(([key, property]) => <label key={`${tool?.name}-${key}`} className="mcp-form-full">
          {property.title || key} *
          {property.enum || property.type === 'boolean'
            ? <select className="form-input" disabled={busy} value={values[key] || ''} onChange={event => setValues(old => ({ ...old, [key]: event.target.value }))}><option value="">请选择</option>{(property.enum || ['true', 'false']).map(value => <option key={String(value)} value={String(value)}>{String(value)}</option>)}</select>
            : property.type === 'integer' || property.type === 'number'
              ? <input type="number" className="form-input" disabled={busy} value={values[key] || ''} onChange={event => setValues(old => ({ ...old, [key]: event.target.value }))} />
              : <textarea className="form-input" disabled={busy} rows={property.type === 'object' ? 4 : 2} value={values[key] || ''} onChange={event => setValues(old => ({ ...old, [key]: event.target.value }))} />}
          {property.description && <small>{property.description}</small>}
        </label>)}
      </div>
      {optionalEntries.length > 0 && <details className="mcp-optional-params">
        <summary>可选参数（{optionalEntries.length}）</summary>
        <div className="mcp-form-grid">{optionalEntries.map(([key, property]) => <label key={`${tool?.name}-${key}`} className="mcp-form-full">
          {property.title || key}
          {property.enum || property.type === 'boolean'
            ? <select className="form-input" disabled={busy} value={values[key] || ''} onChange={event => setValues(old => ({ ...old, [key]: event.target.value }))}><option value="">请选择</option>{(property.enum || ['true', 'false']).map(value => <option key={String(value)} value={String(value)}>{String(value)}</option>)}</select>
            : property.type === 'integer' || property.type === 'number'
              ? <input type="number" className="form-input" disabled={busy} value={values[key] || ''} onChange={event => setValues(old => ({ ...old, [key]: event.target.value }))} />
              : <textarea className="form-input" disabled={busy} rows={property.type === 'object' ? 4 : 2} value={values[key] || ''} onChange={event => setValues(old => ({ ...old, [key]: event.target.value }))} />}
          {property.description && <small>{property.description}</small>}
        </label>)}</div>
      </details>}
      {error && <div className="error-message">{error}</div>}
      {message && <div className="success-message">{message}</div>}
      <div className="mcp-inline-form">
        <button className="btn btn-primary" disabled={busy || !tool} onClick={() => void execute()}>{busy ? '执行中…' : '执行查询'}</button>
      </div>
      {result && <ResultView result={result} />}
      {tool && mappableFields.length > 0 && <div className="mcp-map-panel">
        <div className="section-heading"><h3>映射到专利字段</h3><span>把工具结果写入当前库的专利字段</span></div>
        <p className="mcp-tools-hint">该工具的结果可映射到：{mappableFields.map(fieldLabel).join('、')}。执行查询后点击下方按钮生成写入预览，确认后写入。</p>
        <div className="mcp-inline-form">
          <label className="mcp-inline-grow">目标专利公开号<input className="form-input" disabled={mapping || confirming} value={mapIdentifier} onChange={event => setMapIdentifier(event.target.value)} placeholder="例如 CN123456789A" /></label>
          <button className="btn" disabled={mapping || confirming || !mapIdentifier.trim()} onClick={() => void mapToFields()}>{mapping ? '生成预览中…' : '映射并预览'}</button>
        </div>
        {mapBatch && <UpdatePreview batch={mapBatch} busy={confirming} onConfirm={items => void confirmMap(items)} onCancel={() => void cancelMap()} />}
      </div>}
    </div>
  </section>
}
