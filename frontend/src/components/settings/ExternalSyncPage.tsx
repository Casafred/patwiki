import { useCallback, useEffect, useState } from 'react'
import { syncApi } from '../../api'
import { fieldService as fieldApi } from '../../services'
import { getErrorMessage } from '../../lib/errors'
import { useAppStore } from '../../store'
import type { ExternalObservation, FieldMeta, JsonObject, McpToolInfo, SyncConnector, SyncRun, SyncSubscription } from '../../types'

const EXTERNAL_UPDATE_FIELDS = [
  ['publication_date', '公开日'], ['grant_date', '授权日'], ['legal_status', '法律状态'],
  ['application_number', '申请号'], ['publication_number', '公开号'], ['title', '标题'],
  ['abstract', '摘要'], ['applicant', '申请人'], ['assignee', '受让人'], ['inventor', '发明人'],
  ['filing_date', '申请日'], ['country', '国家/地区'], ['ipc_all', 'IPC 分类'],
] as const

function countValue(run: SyncRun, key: string): string {
  const value = run.counts[key]
  return typeof value === 'number' ? String(value) : '0'
}

type McpTab = 'connectors' | 'monitor' | 'runs'

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
  const [targetFields, setTargetFields] = useState<string[]>(['publication_date', 'legal_status', 'title', 'abstract'])
  const [fields, setFields] = useState<FieldMeta[]>([])
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
  const [activeTab, setActiveTab] = useState<McpTab>('connectors')

  const load = useCallback(async () => {
    if (!currentDatabaseId) return
    try {
      const [connectorResult, subscriptionResult, runResult, observationResult, fieldResult] = await Promise.all([
        syncApi.connectors(),
        syncApi.subscriptions(currentDatabaseId),
        syncApi.runs(),
        syncApi.observations(),
        fieldApi.list(),
      ])
      setFields(fieldResult)
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
        scope_json: { applicant: applicant.trim() || undefined, expression: expression.trim() || undefined, update_fields: targetFields },
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

  const tabs: { key: McpTab; label: string; badge?: number }[] = [
    { key: 'connectors', label: '连接器', badge: connectors.length },
    { key: 'monitor', label: '自动监控', badge: subscriptions.length },
    { key: 'runs', label: '运行与审查', badge: observations.length },
  ]

  return (
    <div className="page-container automation-page mcp-page">
      <div className="page-header dashboard-header">
        <div>
          <h2 className="page-title">MCP 外部数据更新</h2>
          <p className="page-subtitle">连接数据源，设置当前库的更新范围、字段与周期；所有变更保留来源和运行记录。</p>
        </div>
        <button className="btn btn-secondary" disabled={busy || !currentDatabaseId} onClick={() => void load()}>刷新状态</button>
      </div>
      {error && <div className="error-message">{error}</div>}
      {message && <div className="success-message">{message}</div>}

      <nav className="mcp-tabs" role="tablist" aria-label="MCP 数据更新分区">
        {tabs.map(tab => (
          <button
            key={tab.key}
            type="button"
            role="tab"
            aria-selected={activeTab === tab.key}
            className={`mcp-tab ${activeTab === tab.key ? 'active' : ''}`}
            onClick={() => setActiveTab(tab.key)}
          >
            {tab.label}
            {typeof tab.badge === 'number' && tab.badge > 0 && <span className="mcp-tab-badge">{tab.badge}</span>}
          </button>
        ))}
      </nav>

      {activeTab === 'connectors' && (
        <div className="mcp-tab-body">
          <div className="section-heading">
            <h3>数据源连接器</h3>
            <span>{connectors.length} 个 · 健康检查验证连通性，发现工具刷新 MCP 目录</span>
          </div>
          {connectors.length > 0 ? (
            <div className="mcp-connector-grid">
              {connectors.map(connector => (
                <div className="mcp-connector-card" key={connector.id}>
                  <div className="mcp-connector-card-head">
                    <strong title={connector.code}>{connector.name}</strong>
                    <span className={`mcp-chip ${connector.enabled ? 'mcp-chip-ok' : 'mcp-chip-muted'}`}>{connector.enabled ? '已启用' : '已停用'}</span>
                  </div>
                  <div className="mcp-connector-card-tags">
                    <span className="mcp-chip mcp-chip-muted">{connector.provider_type}</span>
                    <span className="mcp-chip mcp-chip-muted">{connector.transport.toUpperCase()}</span>
                    {connector.mcp_catalog_updated_at && <span className="mcp-chip mcp-chip-muted">目录 {String(connector.mcp_catalog_updated_at).slice(0, 10)}</span>}
                  </div>
                  {connector.endpoint && <div className="mcp-connector-endpoint" title={connector.endpoint}>{connector.endpoint}</div>}
                  <div className="mcp-connector-actions">
                    <button className="btn btn-secondary" disabled={busy} onClick={() => void testConnector(connector)}>健康检查</button>
                    {connector.transport === 'mcp' && <button className="btn btn-secondary" disabled={busy} onClick={() => void discoverTools(connector)}>发现工具</button>}
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <div className="empty-state">暂无连接器。可在下方接入 HimmPat MCP。</div>
          )}

          <div className="mcp-access-layout">
            <section className="mcp-panel">
              <div className="section-heading"><h3>接入 HimmPat MCP</h3><span>主站地址 + API Key</span></div>
              <p className="mcp-panel-hint">填写 HimmPat 主站地址和 API Key。应用会分别调用检索、著录项和法律状态服务。</p>
              <div className="mcp-form-grid">
                <label>连接器 code<input className="form-input" value={mcpCode} onChange={event => setMcpCode(event.target.value)} /></label>
                <label>连接器名称<input className="form-input" value={mcpName} onChange={event => setMcpName(event.target.value)} /></label>
                <label className="mcp-form-full">MCP 服务入口<input className="form-input" value={mcpEndpoint} onChange={event => setMcpEndpoint(event.target.value)} /></label>
                <label className="mcp-form-full">API Key<input className="form-input" type="password" value={mcpApiKey} onChange={event => setMcpApiKey(event.target.value)} placeholder="Bearer 后面的 API Key" /></label>
                <label className="checkbox-label mcp-form-full"><input type="checkbox" checked={mcpEnrichLegal} onChange={event => setMcpEnrichLegal(event.target.checked)} />同步时补全法律状态（可能产生额外供应商调用）</label>
              </div>
              <button className="btn btn-primary" disabled={busy || !mcpCode.trim() || !mcpName.trim() || !mcpEndpoint.trim() || !mcpApiKey.trim()} onClick={() => void createHimmPatConnector()}>创建并连接 HimmPat MCP</button>
            </section>

            <section className="mcp-panel">
              <div className="section-heading"><h3>外部信息与目标列</h3><span>按规范属性匹配</span></div>
              <p className="mcp-panel-hint">系统以字段的规范属性匹配，而不依赖表头文字。例如“公开日”“公开日期”只要映射到 publication_date 属性，就会更新同一信息。自定义且未映射属性的列不会自动覆盖。</p>
              <div className="mcp-field-mapping-grid">
                {EXTERNAL_UPDATE_FIELDS.map(([key, label]) => <span key={key}>{label} → {fields.find(field => field.key === key)?.name || label} <small>({key})</small></span>)}
              </div>
            </section>
          </div>

          {tools && (
            <section className="mcp-panel">
              <div className="section-heading"><h3>MCP 工具目录</h3><span>{Array.isArray(tools.services) ? `${tools.services.length} 个服务` : '已发现'}</span></div>
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
            </section>
          )}
        </div>
      )}

      {activeTab === 'monitor' && (
        <div className="mcp-tab-body">
          <div className="mcp-monitor-layout">
            <section className="mcp-panel mcp-monitor-form">
              <div className="section-heading"><h3>新建自动监控规则</h3><span>{targetFields.length} 个目标字段</span></div>
              <div className="mcp-form-grid">
                <label className="mcp-form-full">数据连接器<select className="form-input" value={selectedConnectorId || ''} onChange={event => setSelectedConnectorId(Number(event.target.value) || null)}><option value="">请选择连接器</option>{connectors.map(connector => <option key={connector.id} value={connector.id}>{connector.name} · {connector.provider_type}</option>)}</select></label>
                <label>订阅名称<input className="form-input" value={name} onChange={event => setName(event.target.value)} /></label>
                <label>同步间隔（分钟）<input className="form-input" type="number" min="1" value={intervalMinutes} onChange={event => setIntervalMinutes(event.target.value)} /></label>
                <label className="mcp-form-full">申请人<input className="form-input" value={applicant} onChange={event => setApplicant(event.target.value)} placeholder="可选，按申请人圈定监控范围" /></label>
                <label className="mcp-form-full">关键词表达式<input className="form-input" value={expression} onChange={event => setExpression(event.target.value)} placeholder="可选，例如：(芯片 OR 半导体) AND 封装" /></label>
              </div>
              <fieldset className="mcp-target-fields">
                <legend>允许自动更新的目标字段</legend>
                <p>当前库字段名称可以调整，但需映射到对应规范属性。法律事件仍作为来源历史保存；只有勾选的属性会更新当前值。</p>
                <div className="mcp-target-fields-grid">{EXTERNAL_UPDATE_FIELDS.map(([key, label]) => <label key={key}><input type="checkbox" checked={targetFields.includes(key)} onChange={event => setTargetFields(previous => event.target.checked ? [...previous, key] : previous.filter(item => item !== key))} />{fields.find(field => field.key === key)?.name || label}<small>{key}</small></label>)}</div>
              </fieldset>
              <button className="btn btn-primary" disabled={busy || !currentDatabaseId || !selectedConnectorId || targetFields.length === 0} onClick={() => void createSubscription()}>保存自动监控规则</button>
            </section>

            <section className="mcp-monitor-list">
              <div className="section-heading"><h3>已有监控规则</h3><span>{subscriptions.length} 个 · {currentDatabaseId ? '当前库' : '未选择数据库'}</span></div>
              {subscriptions.length > 0 ? (
                <div className="mcp-rule-list">
                  {subscriptions.map(subscription => (
                    <div className="mcp-rule-card" key={subscription.id}>
                      <div className="mcp-rule-card-head">
                        <strong>{subscription.name}</strong>
                        <span className={`rule-status ${subscription.enabled ? 'enabled' : 'disabled'}`}>{subscription.enabled ? '已启用' : '已停用'}</span>
                      </div>
                      <div className="mcp-rule-card-meta">
                        <span>{subscription.schedule.interval_minutes ? `每 ${String(subscription.schedule.interval_minutes)} 分钟` : '手动'}</span>
                        <span>{subscription.review_policy}</span>
                        <span>上次运行：{subscription.last_run_at || '-'}</span>
                      </div>
                      <div className="mcp-rule-card-status">
                        <span className={`mcp-chip ${subscription.last_status === 'succeeded' ? 'mcp-chip-ok' : subscription.last_status ? 'mcp-chip-warn' : 'mcp-chip-muted'}`}>{subscription.last_status || '尚未运行'}</span>
                        <div className="mcp-rule-card-actions">
                          <button className="btn btn-secondary" disabled={busy || !subscription.enabled} onClick={() => void runSubscription(subscription)}>立即同步</button>
                        </div>
                      </div>
                    </div>
                  ))}
                </div>
              ) : (
                <div className="empty-state">当前数据库还没有监控规则。先在左侧创建一条，之后每次运行都会留档。</div>
              )}
            </section>
          </div>
        </div>
      )}

      {activeTab === 'runs' && (
        <div className="mcp-tab-body">
          <div className="mcp-runs-layout">
            <section className="mcp-panel">
              <div className="section-heading"><h3>最近运行</h3><span>{runs.length} 条</span></div>
              {runs.length > 0 ? (
                <div className="mcp-run-list">
                  {runs.slice(0, 10).map(run => (
                    <div className="mcp-run-row" key={run.id}>
                      <span className={`log-status ${run.status === 'succeeded' ? 'success' : run.status}`}>{run.status}</span>
                      <span>记录 {countValue(run, 'records')}</span>
                      <span>应用 {countValue(run, 'auto_applied')}</span>
                      <span>审查 {countValue(run, 'review')}</span>
                      <time>{run.finished_at || run.created_at || '-'}</time>
                    </div>
                  ))}
                </div>
              ) : (
                <div className="empty-state">暂无同步运行记录。</div>
              )}
            </section>

            <section className="mcp-panel">
              <div className="section-heading"><h3>待审查外部事实</h3><span>{observations.length} 条</span></div>
              {observations.length > 0 ? (
                <div className="mcp-observation-list">
                  {observations.slice(0, 20).map(observation => (
                    <div className="mcp-observation-card" key={observation.id}>
                      <div className="mcp-observation-head">
                        <span className="mcp-chip mcp-chip-info">{observation.canonical_field_key}</span>
                        <span className="mcp-observation-patent">专利 #{observation.patent_id || '-'}</span>
                      </div>
                      <div className="mcp-observation-diff">
                        <span className="mcp-observation-old" title={observation.current_value || ''}>{observation.current_value || '空'}</span>
                        <span className="mcp-observation-arrow">→</span>
                        <span className="mcp-observation-new" title={observation.candidate_value || ''}>{observation.candidate_value || '空'}</span>
                      </div>
                      <div className="mcp-observation-actions">
                        <button className="btn btn-secondary" disabled={busy} onClick={() => void decide(observation, 'accepted')}>接受</button>
                        <button className="btn btn-secondary" disabled={busy} onClick={() => void decide(observation, 'rejected')}>拒绝</button>
                      </div>
                    </div>
                  ))}
                </div>
              ) : (
                <div className="empty-state">暂无待审查事实。</div>
              )}
            </section>
          </div>
        </div>
      )}
    </div>
  )
}
