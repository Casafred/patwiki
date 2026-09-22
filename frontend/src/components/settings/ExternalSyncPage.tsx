import { useCallback, useEffect, useState } from 'react'
import { syncApi } from '../../api'
import { getErrorMessage } from '../../lib/errors'
import { useAppStore } from '../../store'
import type { ExternalObservation, JsonObject, McpToolInfo, SyncConnector, SyncRun, SyncSubscription } from '../../types'

function countValue(run: SyncRun, key: string): string {
  const value = run.counts[key]
  return typeof value === 'number' ? String(value) : '0'
}

export default function ExternalSyncPage() {
  const { currentDatabaseId } = useAppStore()
  const [connectors, setConnectors] = useState<SyncConnector[]>([])
  const [subscriptions, setSubscriptions] = useState<SyncSubscription[]>([])
  const [runs, setRuns] = useState<SyncRun[]>([])
  const [observations, setObservations] = useState<ExternalObservation[]>([])
  const [name, setName] = useState('申请人监控')
  const [applicant, setApplicant] = useState('')
  const [expression, setExpression] = useState('')
  const [intervalMinutes, setIntervalMinutes] = useState('1440')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [message, setMessage] = useState('')
  const [mcpCode, setMcpCode] = useState('himmpat-mcp')
  const [mcpName, setMcpName] = useState('HimmPat MCP')
  const [mcpEndpoint, setMcpEndpoint] = useState('https://www.himmpat.com')
  const [mcpApiKey, setMcpApiKey] = useState('')
  const [mcpEnrichLegal, setMcpEnrichLegal] = useState(false)
  const [tools, setTools] = useState<JsonObject | null>(null)
  const [selectedConnectorId, setSelectedConnectorId] = useState<number | null>(null)

  const load = useCallback(async () => {
    if (!currentDatabaseId) return
    try {
      const [connectorResult, subscriptionResult, runResult, observationResult] = await Promise.all([
        syncApi.connectors(),
        syncApi.subscriptions(currentDatabaseId),
        syncApi.runs(),
        syncApi.observations(),
      ])
      setConnectors(connectorResult.items)
      const availableConnector = connectorResult.items.find(item => item.enabled) || connectorResult.items[0]
      setSelectedConnectorId(current => current && connectorResult.items.some(item => item.id === current) ? current : availableConnector?.id || null)
      const savedCatalog = connectorResult.items.find(item => item.transport === 'mcp' && Object.keys(item.mcp_catalog || {}).length > 0)?.mcp_catalog
      if (savedCatalog) setTools(savedCatalog)
      setSubscriptions(subscriptionResult.items)
      setRuns(runResult.items)
      setObservations(observationResult.items)
    } catch (loadError: unknown) {
      setError(getErrorMessage(loadError, '同步数据加载失败'))
    }
  }, [currentDatabaseId])

  // Synchronize the workspace with persisted sync state when the database changes.
  // eslint-disable-next-line react-hooks/set-state-in-effect
  useEffect(() => { void load() }, [load])

  const createSubscription = async () => {
    if (!currentDatabaseId || !selectedConnectorId || !name.trim()) return
    setBusy(true); setError(''); setMessage('')
    try {
      await syncApi.createSubscription({
        database_id: currentDatabaseId,
        connector_id: selectedConnectorId,
        name: name.trim(),
        scope_json: { applicant: applicant.trim() || undefined, expression: expression.trim() || undefined },
        schedule_json: { interval_minutes: Number(intervalMinutes) || 1440 },
        review_policy: 'safe_auto_apply',
        enabled: true,
      })
      setMessage('同步订阅已创建')
      await load()
    } catch (createError: unknown) {
      setError(getErrorMessage(createError, '同步订阅创建失败'))
    } finally { setBusy(false) }
  }

  const testConnector = async (connector: SyncConnector) => {
    setBusy(true); setError(''); setMessage('')
    try {
      const result = await syncApi.testConnector(connector.id)
      setMessage(`${connector.name}：${result.message}`)
    } catch (testError: unknown) {
      setError(getErrorMessage(testError, '连接器检查失败'))
    } finally { setBusy(false) }
  }

  const createHimmPatConnector = async () => {
    setBusy(true); setError(''); setMessage('')
    try {
      await syncApi.createConnector({
        code: mcpCode.trim(),
        name: mcpName.trim(),
        transport: 'mcp',
        provider_type: 'himmpat_mcp',
        endpoint: mcpEndpoint.trim(),
        capabilities_json: { search: true, fetch_patent: true, legal_events: mcpEnrichLegal, cursor_pagination: true },
        config_json: {
          auth: { credential_value: mcpApiKey.trim() },
          enrich_legal_status: mcpEnrichLegal,
          enrich_legal_on_fetch: false,
          retry: { max_attempts: 2, backoff_seconds: 0.5, max_delay_seconds: 5 },
        },
        enabled: true,
      })
      setMcpApiKey('')
      setMessage('HimmPat MCP 连接器已创建。请先执行工具发现或健康检查。')
      await load()
    } catch (createError: unknown) {
      setError(getErrorMessage(createError, 'MCP 连接器创建失败'))
    } finally { setBusy(false) }
  }

  const discoverTools = async (connector: SyncConnector) => {
    setBusy(true); setError(''); setMessage('')
    try {
      const result = await syncApi.discoverConnector(connector.id)
      setTools(result)
      setMessage(`${connector.name}：工具目录已更新`)
    } catch (discoverError: unknown) {
      setError(getErrorMessage(discoverError, 'MCP 工具发现失败'))
    } finally { setBusy(false) }
  }

  const runSubscription = async (subscription: SyncSubscription) => {
    setBusy(true); setError(''); setMessage('')
    try {
      const run = await syncApi.runSubscription(subscription.id)
      setMessage(`同步完成：读取 ${countValue(run, 'records')} 条，变更 ${countValue(run, 'auto_applied')} 项`)
      await load()
    } catch (runError: unknown) {
      setError(getErrorMessage(runError, '同步执行失败'))
      await load()
    } finally { setBusy(false) }
  }

  const decide = async (observation: ExternalObservation, decision: 'accepted' | 'rejected') => {
    setBusy(true); setError('')
    try {
      await syncApi.decideObservation(observation.id, decision)
      await load()
    } catch (decisionError: unknown) {
      setError(getErrorMessage(decisionError, '观察决策失败'))
    } finally { setBusy(false) }
  }

  return (
    <div className="page-container automation-page">
      <div className="page-header dashboard-header">
        <div>
          <h2 className="page-title">外部数据同步</h2>
          <p className="page-subtitle">连接外部专利数据源，按订阅更新事实并保留可审查来源。</p>
        </div>
        <button className="btn btn-secondary" disabled={busy || !currentDatabaseId} onClick={() => void load()}>刷新状态</button>
      </div>
      {error && <div className="error-message">{error}</div>}
      {message && <div className="success-message">{message}</div>}

      <section className="automation-log-panel">
        <div className="section-heading"><h3>连接器</h3><span>{connectors.length} 个</span></div>
        {connectors.map(connector => <div className="automation-log-row" key={connector.id}>
          <strong>{connector.name}</strong><span>{connector.provider_type}</span><span>{connector.enabled ? '已启用' : '已停用'}</span>
          <button className="btn btn-secondary" disabled={busy} onClick={() => void testConnector(connector)}>健康检查</button>
          {connector.transport === 'mcp' && <button className="btn btn-secondary" disabled={busy} onClick={() => void discoverTools(connector)}>发现工具</button>}
        </div>)}
        {connectors.length === 0 && <div className="empty-state">暂无连接器。</div>}
      </section>

      <section className="automation-form">
        <h3>接入 HimmPat MCP</h3>
        <p className="page-subtitle">填写 HimmPat 主站地址和 API Key。应用会分别调用检索、著录项和法律状态服务。</p>
        <label>连接器 code<input className="form-input" value={mcpCode} onChange={event => setMcpCode(event.target.value)} /></label>
        <label>连接器名称<input className="form-input" value={mcpName} onChange={event => setMcpName(event.target.value)} /></label>
        <label>MCP 服务入口<input className="form-input" value={mcpEndpoint} onChange={event => setMcpEndpoint(event.target.value)} /></label>
        <label>API Key<input className="form-input" type="password" value={mcpApiKey} onChange={event => setMcpApiKey(event.target.value)} placeholder="Bearer 后面的 API Key" /></label>
        <label className="checkbox-label"><input type="checkbox" checked={mcpEnrichLegal} onChange={event => setMcpEnrichLegal(event.target.checked)} />同步时补全法律状态（可能产生额外供应商调用）</label>
        <button className="btn btn-primary" disabled={busy || !mcpCode.trim() || !mcpName.trim() || !mcpEndpoint.trim() || !mcpApiKey.trim()} onClick={() => void createHimmPatConnector()}>创建并连接 HimmPat MCP</button>
      </section>

      {tools && <section className="automation-log-panel"><div className="section-heading"><h3>MCP 工具目录</h3><span>{Array.isArray(tools.services) ? `${tools.services.length} 个服务` : '已发现'}</span></div>
        {Array.isArray(tools.services) && tools.services.map((service, index) => {
          const item = service as JsonObject
          const serviceTools = (Array.isArray(item.tools) ? item.tools : []) as unknown as McpToolInfo[]
          return <div className="mcp-service" key={`${String(item.service || 'service')}-${index}`}>
            <div className="mcp-service-header"><strong>{String(item.service || '-')}</strong><span>{String(item.tool_count || serviceTools.length)} 个工具</span><span>{String(item.latency_ms || 0)} ms</span></div>
            <div className="mcp-tool-list">{serviceTools.map((tool, toolIndex) => {
              const schema = tool.inputSchema || {}
              const required = Array.isArray(schema.required) ? schema.required.map(String) : []
              return <div className="mcp-tool" key={`${tool.name}-${toolIndex}`}>
                <code>{tool.name || '未命名工具'}</code>
                <span>{tool.description || '未提供说明'}</span>
                <small>必填参数：{required.length ? required.join('、') : '无'}</small>
              </div>
            })}</div>
          </div>
        })}
      </section>}

      <section className="automation-form">
        <h3>新建监控订阅</h3>
        <label>数据连接器<select className="form-input" value={selectedConnectorId || ''} onChange={event => setSelectedConnectorId(Number(event.target.value) || null)}><option value="">请选择连接器</option>{connectors.map(connector => <option key={connector.id} value={connector.id}>{connector.name} · {connector.provider_type}</option>)}</select></label>
        <label>订阅名称<input className="form-input" value={name} onChange={event => setName(event.target.value)} /></label>
        <label>申请人<input className="form-input" value={applicant} onChange={event => setApplicant(event.target.value)} placeholder="可选" /></label>
        <label>关键词表达式<input className="form-input" value={expression} onChange={event => setExpression(event.target.value)} placeholder="可选" /></label>
        <label>同步间隔（分钟）<input className="form-input" type="number" min="1" value={intervalMinutes} onChange={event => setIntervalMinutes(event.target.value)} /></label>
        <button className="btn btn-primary" disabled={busy || !currentDatabaseId || !selectedConnectorId} onClick={() => void createSubscription()}>保存订阅</button>
      </section>

      <section className="automation-list">
        <div className="section-heading"><h3>同步订阅</h3><span>{subscriptions.length} 个</span></div>
        {subscriptions.map(subscription => <div className="automation-rule" key={subscription.id}>
          <div className="automation-rule-main"><div><h3>{subscription.name}</h3><p>{subscription.review_policy} · {subscription.schedule.interval_minutes ? `每 ${String(subscription.schedule.interval_minutes)} 分钟` : '手动'}</p></div><span className={`rule-status ${subscription.enabled ? 'enabled' : 'disabled'}`}>{subscription.enabled ? '已启用' : '已停用'}</span></div>
          <div className="automation-rule-meta"><span>{subscription.last_status || '尚未运行'}</span><span>{subscription.last_run_at || '-'}</span></div>
          <div className="automation-actions"><button className="btn btn-secondary" disabled={busy || !subscription.enabled} onClick={() => void runSubscription(subscription)}>立即同步</button></div>
        </div>)}
        {subscriptions.length === 0 && <div className="empty-state">当前数据库还没有同步订阅。</div>}
      </section>

      <section className="automation-log-panel"><div className="section-heading"><h3>最近运行</h3><span>{runs.length} 条</span></div>
        {runs.slice(0, 10).map(run => <div className="automation-log-row" key={run.id}><span className={`log-status ${run.status === 'succeeded' ? 'success' : run.status}`}>{run.status}</span><span>记录 {countValue(run, 'records')}</span><span>应用 {countValue(run, 'auto_applied')}</span><span>审查 {countValue(run, 'review')}</span><time>{run.finished_at || run.created_at || '-'}</time></div>)}
        {runs.length === 0 && <div className="empty-state">暂无同步运行记录。</div>}
      </section>

      <section className="automation-log-panel"><div className="section-heading"><h3>待审查外部事实</h3><span>{observations.length} 条</span></div>
        {observations.slice(0, 20).map(observation => <div className="automation-log-row" key={observation.id}><span>{observation.canonical_field_key}</span><span>{observation.current_value || '空'} → {observation.candidate_value || '空'}</span><span>专利 #{observation.patent_id || '-'}</span><button className="btn btn-secondary" disabled={busy} onClick={() => void decide(observation, 'accepted')}>接受</button><button className="btn btn-secondary" disabled={busy} onClick={() => void decide(observation, 'rejected')}>拒绝</button></div>)}
        {observations.length === 0 && <div className="empty-state">暂无待审查事实。</div>}
      </section>
    </div>
  )
}
