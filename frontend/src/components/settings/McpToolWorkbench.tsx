import { useState } from 'react'
import { syncApi } from '../../api'
import { getErrorMessage } from '../../lib/errors'
import type { JsonObject, JsonValue, McpToolInfo, SyncConnector } from '../../types'

type Property = { type?: string; description?: string; enum?: unknown[]; items?: { type?: string }; title?: string }

const PRESETS: { label: string; hint: string; match: string[] }[] = [
  { label: '检索专利', hint: '按关键词 / 检索式搜索', match: ['search', 'query', '检索'] },
  { label: '获取专利著录项', hint: '按公开号或申请号取回详情', match: ['detail', 'fetch', 'get', '著录', 'patent'] },
  { label: '查询法律状态', hint: '取回法律事件与当前状态', match: ['legal', 'status', '法律', 'event'] },
]

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

  const properties = (tool?.inputSchema?.properties || {}) as Record<string, Property>
  const required = (tool?.inputSchema?.required || []) as string[]
  const requiredEntries = Object.entries(properties).filter(([key]) => required.includes(key))
  const optionalEntries = Object.entries(properties).filter(([key]) => !required.includes(key))
  const presetTools = PRESETS.map(preset => ({
    ...preset,
    tool: tools.find(item => preset.match.some(keyword => item.name.toLowerCase().includes(keyword))),
  }))

  const selectTool = (nextTool: McpToolInfo) => {
    setToolName(nextTool.name); setValues({}); setError(''); setResult(null)
  }
  const reset = () => { setValues({}); setError(''); setResult(null) }

  const execute = async () => {
    if (!connector || !service || !tool) return
    setBusy(true); setError(''); setResult(null)
    try {
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
      setResult(await syncApi.callConnectorTool(connector.id, { service: String(service.service), tool: tool.name, arguments: arguments_ }))
    } catch (err) { setError(getErrorMessage(err, '工具调用失败')) }
    finally { setBusy(false) }
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
      <p className="mcp-tools-hint">更新会把著录项、法律状态等基础信息写入当前库，并保留来源快照和审查记录。</p>
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
      <button className="btn btn-primary" disabled={busy || !tool} onClick={() => void execute()}>{busy ? '执行中…' : '执行查询'}</button>
      {result && <ResultView result={result} />}
    </div>
  </section>
}