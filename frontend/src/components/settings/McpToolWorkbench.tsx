import { useState } from 'react'
import { syncApi } from '../../api'
import { getErrorMessage } from '../../lib/errors'
import type { JsonObject, McpToolInfo, SyncConnector } from '../../types'

type Property = { type?: string; description?: string; enum?: unknown[]; items?: { type?: string } }

export default function McpToolWorkbench({ connectors }: { connectors: SyncConnector[] }) {
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
  const [result, setResult] = useState<JsonObject | null>(null)
  const properties = (tool?.inputSchema?.properties || {}) as Record<string, Property>
  const required = (tool?.inputSchema?.required || []) as string[]
  const reset = () => { setValues({}); setError(''); setResult(null) }
  const execute = async () => {
    if (!connector || !service || !tool) return
    setBusy(true); setError(''); setResult(null)
    try {
      const arguments_: JsonObject = {}
      for (const [key, property] of Object.entries(properties)) {
        const value = values[key]?.trim()
        if (!value) {
          if (required.includes(key)) throw new Error(`请填写 ${key}`)
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
  return <section className="mcp-panel">
    <div className="section-heading"><h3>HimmPat 工具工作台</h3><span>{tools.length} 个工具</span></div>
    <div className="mcp-form-grid">
      <label>连接器<select className="form-input" disabled={busy} value={connector?.id || ''} onChange={event => { setConnectorId(Number(event.target.value)); setServiceName(''); setToolName(''); reset() }}>{available.map(item => <option key={item.id} value={item.id}>{item.name}</option>)}</select></label>
      <label>服务<select className="form-input" disabled={busy} value={String(service?.service || '')} onChange={event => { setServiceName(event.target.value); setToolName(''); reset() }}>{services.map(item => <option key={String(item.service)} value={String(item.service)}>{String(item.service)}</option>)}</select></label>
      <label className="mcp-form-full">工具<select className="form-input" disabled={busy} value={tool?.name || ''} onChange={event => { setToolName(event.target.value); reset() }}>{tools.map(item => <option key={item.name} value={item.name}>{item.name}</option>)}</select></label>
    </div>
    {tool?.description && <p>{tool.description}</p>}
    <div className="mcp-form-grid">
      {Object.entries(properties).map(([key, property]) => <label key={`${tool?.name}-${key}`} className="mcp-form-full">
        {key}{required.includes(key) ? ' *' : ''}
        {property.enum || property.type === 'boolean'
          ? <select className="form-input" disabled={busy} value={values[key] || ''} onChange={event => setValues(old => ({ ...old, [key]: event.target.value }))}><option value="">请选择</option>{(property.enum || ['true', 'false']).map(value => <option key={String(value)} value={String(value)}>{String(value)}</option>)}</select>
          : property.type === 'integer' || property.type === 'number'
            ? <input type="number" className="form-input" disabled={busy} value={values[key] || ''} onChange={event => setValues(old => ({ ...old, [key]: event.target.value }))} />
            : <textarea className="form-input" disabled={busy} rows={property.type === 'object' ? 4 : 2} value={values[key] || ''} onChange={event => setValues(old => ({ ...old, [key]: event.target.value }))} />}
        {property.description && <small>{property.description}</small>}
      </label>)}
    </div>
    {error && <div className="error-message">{error}</div>}
    <button className="btn btn-primary" disabled={busy || !tool} onClick={() => void execute()}>{busy ? '执行中' : '执行查询'}</button>
    {result && <div style={{ marginTop: 16 }}><strong>查询结果 · 来源快照 #{String(result.snapshot_id)}</strong><pre style={{ whiteSpace: 'pre-wrap', overflowWrap: 'anywhere', maxHeight: 500, overflow: 'auto' }}>{JSON.stringify(result.data, null, 2)}</pre></div>}
  </section>
}
