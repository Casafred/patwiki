import { useCallback, useEffect, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { syncApi } from '../../api'
import { fieldService as fieldApi } from '../../services'
import { getErrorMessage } from '../../lib/errors'
import { useAppStore } from '../../store'
import type { ExternalObservation, FieldMeta, JsonObject, SyncConnector, SyncRecord, SyncRun, SyncSubscription } from '../../types'
import { HIMMPAT_UPDATE_FIELD_OPTIONS } from '../../lib/externalSync'
import McpFieldUpdate from './McpFieldUpdate'
import McpFieldSelection from './McpFieldSelection'

function countValue(run: SyncRun, key: string): string {
  const value = run.counts[key]
  return typeof value === 'number' ? String(value) : '0'
}

type McpTab = 'connectors' | 'monitor' | 'runs'

export default function ExternalSyncPage() {
  const [searchParams] = useSearchParams()
  const { currentDatabaseId } = useAppStore()
  const [connectors, setConnectors] = useState<SyncConnector[]>([])
  const [archivedConnectors, setArchivedConnectors] = useState<SyncConnector[]>([])
  const [subscriptions, setSubscriptions] = useState<SyncSubscription[]>([])
  const [runs, setRuns] = useState<SyncRun[]>([])
  const [observations, setObservations] = useState<ExternalObservation[]>([])
  const [name, setName] = useState('申请人监控')
  const [applicant, setApplicant] = useState('')
  const [expression, setExpression] = useState('')
  const [intervalMinutes, setIntervalMinutes] = useState('1440')
  const [scheduleMode, setScheduleMode] = useState<'minutes' | 'days' | 'date'>('minutes')
  const [intervalDays, setIntervalDays] = useState('7')
  const [runAt, setRunAt] = useState('')
  const [selectedTrackedPatentIds, setSelectedTrackedPatentIds] = useState<number[]>([])
  const [monitorMode, setMonitorMode] = useState<'applicant' | 'expression' | 'publication'>('applicant')
  const [publicationText, setPublicationText] = useState('')
  const [publicationMatches, setPublicationMatches] = useState<{ patent_id: number; publication_number?: string; application_number?: string; title: string; country?: string; ungranted: boolean }[]>([])
  const [unmatchedPublications, setUnmatchedPublications] = useState<string[]>([])
  const [statusStrategyJson, setStatusStrategyJson] = useState('{\n  "granted": { "interval_days": 30 },\n  "pending": { "interval_days": 7 },\n  "unknown": { "interval_days": 14 }\n}')
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
  const [selectedConnectorId, setSelectedConnectorId] = useState<number | null>(null)
  const [activeTab, setActiveTab] = useState<McpTab>('connectors')
  const [expandedRunId, setExpandedRunId] = useState<number | null>(null)
  const [runRecords, setRunRecords] = useState<SyncRecord[]>([])
  const [runObservations, setRunObservations] = useState<ExternalObservation[]>([])
  const [runDetailBusy, setRunDetailBusy] = useState(false)
  const updateFields = HIMMPAT_UPDATE_FIELD_OPTIONS.map(field => ({
    ...field,
    label: fields.find(meta => meta.key === field.key)?.name || field.label,
  }))

  const defaultMonitorName = (mode: typeof monitorMode) => mode === 'applicant' ? '申请人监控' : mode === 'expression' ? '检索式监控' : '公开号跟踪'

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
      setArchivedConnectors(connectorResult.archived_items || [])
      const availableConnector = connectorResult.items.find(item => item.enabled) || connectorResult.items[0]
      setSelectedConnectorId(current => current && connectorResult.items.some(item => item.id === current) ? current : availableConnector?.id || null)
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

  useEffect(() => {
    const ids = (searchParams.get('patent_ids') || '').split(',').map(Number).filter(id => Number.isInteger(id) && id > 0)
    if (ids.length) {
      // eslint-disable-next-line react-hooks/set-state-in-effect
      setActiveTab('monitor')
      setMonitorMode('publication')
      setName('公开号跟踪')
      setSelectedTrackedPatentIds(ids)
      if (currentDatabaseId) void syncApi.resolvePublications({ database_id: currentDatabaseId, patent_ids: ids }).then(result => setPublicationMatches(result.matched)).catch(() => undefined)
    }
  }, [searchParams, currentDatabaseId])

  const createSubscription = async () => {
    if (!currentDatabaseId || !selectedConnectorId || !name.trim()) return
    setBusy(true); setError(''); setMessage('')
    try {
      if (scheduleMode === 'date' && !runAt) throw new Error('请选择首次触发时间')
      const trackedPatentIds = monitorMode === 'publication' ? publicationMatches.filter(item => selectedTrackedPatentIds.includes(item.patent_id)).map(item => item.patent_id) : []
      if (monitorMode === 'publication' && trackedPatentIds.length === 0) throw new Error('请先匹配公开号并确认选择专利')
      if (monitorMode === 'applicant' && !applicant.trim()) throw new Error('请输入申请人')
      if (monitorMode === 'expression' && !expression.trim()) throw new Error('请输入检索式')
      let statusStrategies: JsonObject = {}
      if (statusStrategyJson.trim()) {
        try { statusStrategies = JSON.parse(statusStrategyJson) as JsonObject } catch { throw new Error('法律状态策略必须是有效 JSON') }
      }
      const schedule = scheduleMode === 'days'
        ? { interval_days: Number(intervalDays) || 1 }
        : scheduleMode === 'date'
          ? { run_at: new Date(runAt).toISOString(), repeat_days: Number(intervalDays) || 0 }
          : { interval_minutes: Number(intervalMinutes) || 1440 }
      await syncApi.createSubscription({
        database_id: currentDatabaseId,
        connector_id: selectedConnectorId,
        name: name.trim(),
        mode: monitorMode === 'publication' ? 'tracked_patents' : monitorMode,
        scope_json: { applicant: monitorMode === 'applicant' ? applicant.trim() : undefined, expression: monitorMode === 'expression' ? expression.trim() : undefined, update_fields: targetFields },
        schedule_json: schedule,
        tracked_patent_ids: trackedPatentIds,
        status_strategies: statusStrategies,
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

  const deleteConnector = async (connector: SyncConnector) => {
    if (!window.confirm(`从可用连接器中移除“${connector.name}”（${connector.code}）？已有运行记录和审计来源会保留，可在页面下方恢复。`)) return
    setBusy(true); setError(''); setMessage('')
    try {
      await syncApi.deleteConnector(connector.id)
      setMessage(`${connector.name} 已移至已删除连接器，历史记录已保留`)
      await load()
    } catch (deleteError: unknown) {
      setError(getErrorMessage(deleteError, '连接器移除失败'))
    } finally { setBusy(false) }
  }

  const restoreConnector = async (connector: SyncConnector) => {
    setBusy(true); setError(''); setMessage('')
    try {
      await syncApi.restoreConnector(connector.id)
      setMessage(`${connector.name} 已恢复为停用状态；启用后可重新使用`)
      await load()
    } catch (restoreError: unknown) {
      setError(getErrorMessage(restoreError, '连接器恢复失败'))
    } finally { setBusy(false) }
  }

  const toggleConnector = async (connector: SyncConnector) => {
    setBusy(true); setError(''); setMessage('')
    try {
      await syncApi.updateConnector(connector.id, { enabled: !connector.enabled })
      setMessage(`${connector.name} 已${connector.enabled ? '停用' : '启用'}`)
      await load()
    } catch (updateError: unknown) {
      setError(getErrorMessage(updateError, '连接器状态更新失败'))
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
      await syncApi.discoverConnector(connector.id)
      setMessage(`${connector.name}：工具目录已更新`)
    } catch (discoverError: unknown) {
      setError(getErrorMessage(discoverError, 'MCP 工具发现失败'))
    } finally { setBusy(false) }
  }

  const runSubscription = async (subscription: SyncSubscription) => {
    setBusy(true); setError(''); setMessage('')
    try {
      const run = await syncApi.runSubscription(subscription.id)
      if (run.error_message) setError(`${run.status}：${run.error_message}`)
      else setMessage(`同步完成：读取 ${countValue(run, 'records')} 条，变更 ${countValue(run, 'auto_applied')} 项`)
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

  const toggleRunDetail = async (run: SyncRun) => {
    if (expandedRunId === run.id) { setExpandedRunId(null); return }
    setExpandedRunId(run.id); setRunDetailBusy(true); setRunRecords([]); setRunObservations([])
    try {
      const [recordResult, observationResult] = await Promise.all([syncApi.runRecords(run.id), syncApi.runObservations(run.id)])
      setRunRecords(recordResult.items); setRunObservations(observationResult.items)
    } catch (detailError: unknown) {
      setError(getErrorMessage(detailError, '运行详情加载失败'))
    } finally { setRunDetailBusy(false) }
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
                    <div className="mcp-connector-identity"><strong>{connector.name}</strong><code>{connector.code}</code></div>
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
                    <button className="btn btn-secondary" disabled={busy} onClick={() => void toggleConnector(connector)}>{connector.enabled ? '停用' : '启用'}</button>
                    <button className="btn btn-ghost mcp-delete-connector" disabled={busy} onClick={() => void deleteConnector(connector)}>删除</button>
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <div className="empty-state">暂无连接器。可在下方接入 HimmPat MCP。</div>
          )}

          {archivedConnectors.length > 0 && (
            <section className="mcp-archived-connectors">
              <div className="section-heading"><h3>已删除连接器</h3><span>历史记录保留 · 恢复后需手动启用</span></div>
              <div className="mcp-archived-list">
                {archivedConnectors.map(connector => <div className="mcp-archived-row" key={connector.id}>
                  <span><strong>{connector.name}</strong> <code>{connector.code}</code></span>
                  <button className="btn btn-secondary" disabled={busy} onClick={() => void restoreConnector(connector)}>恢复</button>
                </div>)}
              </div>
            </section>
          )}

          <div className="mcp-access-layout">
            <section className="mcp-panel">
              <div className="section-heading"><h3>接入 HimmPat MCP</h3><span>主站地址 + API Key</span></div>
              <p className="mcp-panel-hint">填写 HimmPat 主站地址和 API Key。应用会分别调用检索、著录项和法律状态服务。</p>
              <div className="mcp-form-grid">
                <label>连接器 code<input className="form-input" value={mcpCode} onChange={event => setMcpCode(event.target.value)} /><small>唯一且稳定的机器标识，用来保留连接器及历史引用；相同 code 不能创建两条连接。</small></label>
                <label>连接器名称<input className="form-input" value={mcpName} onChange={event => setMcpName(event.target.value)} /><small>供用户识别的展示名称，可以调整；provider_type 决定实际调用的适配器。</small></label>
                <label className="mcp-form-full">MCP 服务入口<input className="form-input" value={mcpEndpoint} onChange={event => setMcpEndpoint(event.target.value)} /></label>
                <label className="mcp-form-full">API Key<input className="form-input" type="password" value={mcpApiKey} onChange={event => setMcpApiKey(event.target.value)} placeholder="Bearer 后面的 API Key" /></label>
                <label className="checkbox-label mcp-form-full"><input type="checkbox" checked={mcpEnrichLegal} onChange={event => setMcpEnrichLegal(event.target.checked)} />同步时补全法律状态（可能产生额外供应商调用）</label>
              </div>
              <button className="btn btn-primary" disabled={busy || !mcpCode.trim() || !mcpName.trim() || !mcpEndpoint.trim() || !mcpApiKey.trim()} onClick={() => void createHimmPatConnector()}>创建并连接 HimmPat MCP</button>
            </section>

            <McpFieldUpdate connectors={connectors} databaseId={currentDatabaseId} fields={updateFields} selectedFields={targetFields} onChange={setTargetFields} onUpdated={load} />
          </div>

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
                <label>触发方式<select className="form-input" value={scheduleMode} onChange={event => setScheduleMode(event.target.value as 'minutes' | 'days' | 'date')}><option value="minutes">按分钟（兼容）</option><option value="days">每隔天数</option><option value="date">指定年月日</option></select></label>
                {scheduleMode === 'minutes' && <label>同步间隔（分钟）<input className="form-input" type="number" min="1" value={intervalMinutes} onChange={event => setIntervalMinutes(event.target.value)} /></label>}
                {scheduleMode === 'days' && <label>每隔天数<input className="form-input" type="number" min="1" value={intervalDays} onChange={event => setIntervalDays(event.target.value)} /></label>}
                {scheduleMode === 'date' && <><label>首次触发时间<input className="form-input" type="datetime-local" value={runAt} onChange={event => setRunAt(event.target.value)} /></label><label>重复间隔天数（可选）<input className="form-input" type="number" min="0" value={intervalDays} onChange={event => setIntervalDays(event.target.value)} /></label></>}
                <label className="mcp-form-full">跟踪方式<select className="form-input" value={monitorMode} onChange={event => { const mode = event.target.value as typeof monitorMode; setMonitorMode(mode); setName(defaultMonitorName(mode)); setSelectedTrackedPatentIds([]); setPublicationMatches([]) }}><option value="applicant">申请人跟踪</option><option value="expression">检索式跟踪</option><option value="publication">专利公开号跟踪</option></select></label>
                {monitorMode === 'applicant' && <label className="mcp-form-full">申请人<input className="form-input" value={applicant} onChange={event => setApplicant(event.target.value)} placeholder="输入申请人名称" /></label>}
                {monitorMode === 'expression' && <label className="mcp-form-full">检索式<input className="form-input" value={expression} onChange={event => setExpression(event.target.value)} placeholder="例如：(芯片 OR 半导体) AND 封装" /></label>}
                {monitorMode === 'publication' && <>
                  <label className="mcp-form-full">批量输入公开号<textarea className="form-input" rows={5} value={publicationText} onChange={event => setPublicationText(event.target.value)} placeholder="每行一个，例如 CN123456789A、US20240123456A1" /></label>
                  <div className="mcp-form-full"><button className="btn btn-secondary" disabled={busy || !currentDatabaseId || !publicationText.trim()} onClick={() => { setBusy(true); void syncApi.resolvePublications({ database_id: currentDatabaseId!, publications: publicationText.split(/[\s,，;；]+/).filter(Boolean) }).then(result => { setPublicationMatches(result.matched); setUnmatchedPublications(result.unmatched); setSelectedTrackedPatentIds(result.matched.map(item => item.patent_id)) }).catch(error => setError(getErrorMessage(error, '公开号匹配失败'))).finally(() => setBusy(false)) }}>匹配当前库</button>
                    {publicationMatches.length > 0 && <div className="mcp-publication-matches"><strong>匹配到 {publicationMatches.length} 件，请确认后加入跟踪</strong>{publicationMatches.map(item => <label key={item.patent_id} className="checkbox-label"><input type="checkbox" checked={selectedTrackedPatentIds.includes(item.patent_id)} onChange={event => setSelectedTrackedPatentIds(old => event.target.checked ? [...old, item.patent_id] : old.filter(id => id !== item.patent_id))} />{item.publication_number || '无公开号'} · {item.title}{item.ungranted ? ' · 未授权公开' : ''}</label>)}</div>}
                    {unmatchedPublications.length > 0 && <small>未匹配：{unmatchedPublications.join('、')}</small>}</div>
                </>}
              </div>
              <label className="mcp-form-full" style={{ display: 'block', marginTop: 10 }}>按法律状态设置扫描策略（JSON；键为 legal_status，支持 interval_days、enabled、update_fields）<textarea className="form-input" rows={4} value={statusStrategyJson} onChange={event => setStatusStrategyJson(event.target.value)} /></label>
              <fieldset className="mcp-target-fields">
                <legend>允许自动更新的目标字段</legend>
                <p>法律事件仍作为来源历史保存；只有勾选的属性会更新当前值。</p>
                <McpFieldSelection fields={updateFields} selectedFields={targetFields} onChange={setTargetFields} disabled={busy} />
              </fieldset>
              <button className="btn btn-primary" disabled={busy || !currentDatabaseId || !selectedConnectorId || targetFields.length === 0} onClick={() => void createSubscription()}>保存自动监控规则</button>
            </section>

            <section className="mcp-monitor-list">
              <div className="section-heading"><h3>已有监控规则</h3><span>{subscriptions.length} 个 · {currentDatabaseId ? '当前库' : '未选择数据库'}</span></div>
              {subscriptions.length > 0 ? (
                <div className="mcp-rule-list">
                  {subscriptions.map(subscription => {
                    const connectorBlocked = !subscription.connector_enabled || Boolean(subscription.connector_deleted_at)
                    const active = subscription.enabled && !connectorBlocked
                    return (
                      <div className="mcp-rule-card" key={subscription.id}>
                        <div className="mcp-rule-card-head">
                          <strong>{subscription.name}</strong>
                          <span className={`rule-status ${active ? 'enabled' : 'disabled'}`}>{!subscription.enabled ? '已停用' : subscription.connector_deleted_at ? '连接器已删除' : connectorBlocked ? '连接器已停用' : '已启用'}</span>
                        </div>
                        <div className="mcp-rule-card-meta">
                          {subscription.connector_name && <span>连接器：{subscription.connector_name}</span>}
                          <span>{subscription.schedule.interval_days ? `每 ${String(subscription.schedule.interval_days)} 天` : subscription.schedule.run_at ? `指定 ${String(subscription.schedule.run_at).slice(0, 16)}` : subscription.schedule.interval_minutes ? `每 ${String(subscription.schedule.interval_minutes)} 分钟` : '手动'}</span>
                          {subscription.tracked_patent_count ? <span>跟踪 {subscription.tracked_patent_count} 件</span> : null}
                          <span>{subscription.review_policy}</span>
                          <span>上次运行：{subscription.last_run_at || '-'}</span>
                        </div>
                        <div className="mcp-rule-card-status">
                          <span className={`mcp-chip ${subscription.last_status === 'succeeded' ? 'mcp-chip-ok' : subscription.last_status ? 'mcp-chip-warn' : 'mcp-chip-muted'}`}>{subscription.last_status || '尚未运行'}</span>
                          <div className="mcp-rule-card-actions">
                            <button className="btn btn-secondary" disabled={busy || !active} onClick={() => void runSubscription(subscription)}>立即同步</button>
                            <button className="btn btn-secondary" disabled={busy} onClick={() => { setBusy(true); void syncApi.updateSubscription(subscription.id, { enabled: !subscription.enabled }).then(load).catch(error => setError(getErrorMessage(error))).finally(() => setBusy(false)) }}>{subscription.enabled ? '停用' : '启用'}</button>
                            <button className="btn btn-danger" disabled={busy} onClick={() => { if (!window.confirm(`删除监控规则“${subscription.name}”？历史运行和来源记录会保留。`)) return; setBusy(true); void syncApi.deleteSubscription(subscription.id).then(load).catch(error => setError(getErrorMessage(error))).finally(() => setBusy(false)) }}>删除</button>
                          </div>
                        </div>
                      </div>
                    )
                  })}
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
                  {runs.slice(0, 10).map(run => {
                    const expanded = expandedRunId === run.id
                    return <div className={`mcp-run-row-wrap ${expanded ? 'expanded' : ''}`} key={run.id}>
                      <button type="button" className="mcp-run-row" aria-expanded={expanded} onClick={() => void toggleRunDetail(run)}>
                        <span className={`log-status ${run.status === 'succeeded' ? 'success' : run.status}`}>{run.status}</span>
                        <span>记录 {countValue(run, 'records')}</span>
                        <span>应用 {countValue(run, 'auto_applied')}</span>
                        <span>审查 {countValue(run, 'review')}</span>
                        <time>{run.finished_at || run.created_at || '-'}</time>
                        <span className="mcp-run-toggle">{expanded ? '收起' : '详情'}</span>
                      </button>
                      {expanded && <div className="mcp-run-details">
                        {runDetailBusy ? <div className="semantic-muted">正在加载运行详情…</div> : <>
                          <div className="mcp-run-detail-grid">
                            <div><span>连接器</span><strong>{connectors.find(item => item.id === run.connector_id)?.name || `#${run.connector_id}`}</strong></div>
                            <div><span>触发方式</span><strong>{run.trigger}</strong></div>
                            <div><span>开始时间</span><strong>{run.started_at || '-'}</strong></div>
                            <div><span>结束时间</span><strong>{run.finished_at || '-'}</strong></div>
                            <div><span>错误</span><strong>{run.error_code || run.error_message || '无'}</strong></div>
                            <div><span>返回记录</span><strong>{runRecords.length} 条</strong></div>
                          </div>
                          <strong className="mcp-run-section-title">回填的专利行与单元格（{runObservations.length}）</strong>
                          {runObservations.length > 0
                            ? <div className="mcp-run-detail-table"><table><thead><tr><th>专利</th><th>字段</th><th>原值</th><th>新值</th><th>处理</th></tr></thead><tbody>
                              {runObservations.slice(0, 200).map(item => <tr key={item.id}><td>#{item.patent_id ?? '-'}</td><td>{item.canonical_field_key}</td><td title={item.current_value || ''}>{item.current_value || '空'}</td><td title={item.candidate_value || ''}>{item.candidate_value || '空'}</td><td>{item.decision}</td></tr>)}
                            </tbody></table></div>
                            : <div className="semantic-muted">本次运行没有字段级回填记录。</div>}
                          <strong className="mcp-run-section-title">返回内容（{runRecords.length}）</strong>
                          {runRecords.length > 0
                            ? <div className="mcp-run-records">
                              {runRecords.slice(0, 50).map(record => <div className="mcp-run-record" key={record.id}>
                                <div className="mcp-run-record-head">
                                  <strong>{record.patent_number || record.external_record_id}</strong>
                                  {record.patent_title && <span title={record.patent_title}>{record.patent_title}</span>}
                                  <span>结果 {record.outcome}</span>
                                  {record.error_message && <span>错误 {record.error_message}</span>}
                                </div>
                                {record.snapshot_payload !== undefined && record.snapshot_payload !== null && <details><summary>查看返回原文</summary><pre>{JSON.stringify(record.snapshot_payload, null, 2)}</pre></details>}
                              </div>)}
                            </div>
                            : <div className="semantic-muted">本次运行没有返回记录。</div>}
                        </>}
                      </div>}
                    </div>
                  })}
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
