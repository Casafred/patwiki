import { useCallback, useEffect, useMemo, useState } from 'react'
import { Link, useLocation, useNavigate, useParams, useSearchParams } from 'react-router-dom'
import { fieldApi, importApi } from '../../api'
import type { FieldMeta, GovernanceAction, GovernanceDecision, GovernanceObservation, ImportFieldGovernanceAudit } from '../../types'
import { getErrorMessage } from '../../lib/errors'
import { formatApiDateTime } from '../../lib/date'
import { useAppStore } from '../../store'
import SyncConflictQueue from './SyncConflictQueue'

const ACTION_LABELS: Record<GovernanceAction, string> = {
  retain_source: '保留来源',
  ignore: '忽略展示',
  map_existing: '映射已有字段',
  propose_field: '提交字段候选',
}

const DIFFERENCE_LABELS: Record<string, string> = {
  unknown: '未知属性',
  new: '新增值',
  same: '相同',
  format: '格式差异',
  content: '内容差异',
  quarantined: '待隔离',
}

const RESOLUTION_LABELS: Record<string, string> = {
  mapped: '已映射字段',
  unmapped_retained: '来源值待映射',
  quarantined: '已隔离',
  source_only: '保留来源',
  ignored: '忽略展示',
  candidate: '字段候选',
}

const REVIEW_ACTION_LABELS: Record<string, string> = {
  adopt: '采用导入值',
  keep_existing: '保留现有值',
  fill_empty: '仅填充空值',
  merge: '融合合并',
  ignore: '忽略本单元格',
  quarantine: '隔离待处理',
}

function compact(value?: string | null) {
  if (!value) return '-'
  return value.length > 180 ? `${value.slice(0, 180)}...` : value
}

function formatDate(value?: string | null) {
  return formatApiDateTime(value)
}

function displayAuditValue(value: unknown) {
  if (value === null || value === undefined || value === '') return '（空）'
  if (typeof value === 'string') return value
  return JSON.stringify(value, null, 2)
}

export default function ImportGovernancePage() {
  const navigate = useNavigate()
  const location = useLocation()
  const { databaseId } = useParams<{ databaseId: string }>()
  const { currentDatabaseId } = useAppStore()
  const [searchParams] = useSearchParams()
  const [items, setItems] = useState<GovernanceObservation[]>([])
  const [total, setTotal] = useState(0)
  const [offset, setOffset] = useState(0)
  const [pageSize, setPageSize] = useState(50)
  const [fields, setFields] = useState<FieldMeta[]>([])
  const [allFields, setAllFields] = useState<FieldMeta[]>([])
  const [activeView, setActiveView] = useState<'conflicts' | 'fields' | 'audits'>('conflicts')
  const [conflictCount, setConflictCount] = useState(0)
  const [sourceField, setSourceField] = useState('')
  const [batchId, setBatchId] = useState(() => searchParams.get('batch_id')?.replace(/\D/g, '') || '')
  const [patentId, setPatentId] = useState(() => searchParams.get('patent_id')?.replace(/\D/g, '') || '')
  const [sourceRowId, setSourceRowId] = useState(() => searchParams.get('source_row_id')?.replace(/\D/g, '') || '')
  const [mappingBySource, setMappingBySource] = useState<Record<string, string>>({})
  const [batchScope, setBatchScope] = useState(true)
  const [adoptedValue, setAdoptedValue] = useState(false)
  const [loading, setLoading] = useState(true)
  const [busyKey, setBusyKey] = useState<string | null>(null)
  const [historyItem, setHistoryItem] = useState<GovernanceObservation | null>(null)
  const [history, setHistory] = useState<GovernanceDecision[]>([])
  const [historyLoading, setHistoryLoading] = useState(false)
  const [historyBusyKey, setHistoryBusyKey] = useState<string | null>(null)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const [auditItems, setAuditItems] = useState<ImportFieldGovernanceAudit[]>([])
  const [auditTotal, setAuditTotal] = useState(0)
  const [auditOffset, setAuditOffset] = useState(0)
  const [auditSearch, setAuditSearch] = useState('')
  const [auditQuery, setAuditQuery] = useState('')
  const [auditField, setAuditField] = useState('')
  const [auditSource, setAuditSource] = useState('')
  const [auditLoading, setAuditLoading] = useState(false)
  const [auditPageSize, setAuditPageSize] = useState(30)

  const loadItems = useCallback(async () => {
    setLoading(true)
    setError('')
    try {
      const result = await importApi.listUnmapped({
        source_field: sourceField.trim() || undefined,
        batch_id: batchId.trim() ? Number(batchId) : undefined,
        patent_id: patentId.trim() ? Number(patentId) : undefined,
        source_row_id: sourceRowId.trim() ? Number(sourceRowId) : undefined,
        database_id: databaseId ? Number(databaseId) : currentDatabaseId ?? undefined,
        offset,
        limit: pageSize,
      })
      setItems(result.items)
      setTotal(result.total)
      return result
    } catch (requestError: unknown) {
      setError(getErrorMessage(requestError, '待治理字段加载失败'))
    } finally {
      setLoading(false)
    }
    return null
  }, [batchId, currentDatabaseId, databaseId, offset, pageSize, patentId, sourceField, sourceRowId])

  useEffect(() => {
    const timer = window.setTimeout(() => void loadItems(), 220)
    return () => window.clearTimeout(timer)
  }, [loadItems])

  useEffect(() => {
    fieldApi.list()
      .then(result => {
        setAllFields(result)
        setFields(result.filter(field => field.editable !== false && !field.is_formula))
      })
      .catch(() => { setFields([]); setAllFields([]) })
  }, [])

  const loadAudits = useCallback(async () => {
    setAuditLoading(true)
    setError('')
    try {
      const result = await importApi.listImportGovernanceAudits({
        database_id: databaseId ? Number(databaseId) : currentDatabaseId ?? undefined,
        q: auditQuery.trim() || undefined,
        field_key: auditField.trim() || undefined,
        source_kind: auditSource || undefined,
        offset: auditOffset,
        limit: auditPageSize,
      })
      setAuditItems(result.items)
      setAuditTotal(result.total)
    } catch (requestError: unknown) {
      setError(getErrorMessage(requestError, '导入变更审计加载失败'))
    } finally {
      setAuditLoading(false)
    }
  }, [auditField, auditOffset, auditPageSize, auditQuery, auditSource, currentDatabaseId, databaseId])

  useEffect(() => {
    void loadAudits()
  }, [loadAudits])

  const sourceFields = useMemo(
    () => [...new Set(items.map(item => item.source_field_name))].sort((a, b) => a.localeCompare(b)),
    [items],
  )

  const decide = useCallback(async (item: GovernanceObservation, action: GovernanceAction, adopt = false) => {
    const canonicalFieldKey = mappingBySource[item.source_field_name]
    if (action === 'map_existing' && !canonicalFieldKey) {
      setError(`请先为来源列“${item.source_field_name}”选择目标字段`)
      return
    }
    const key = `${item.id}:${action}:${adopt ? 'adopt' : 'keep'}`
    setBusyKey(key)
    setError('')
    setNotice('')
    try {
      const result = await importApi.decideObservation(item.id, {
        action,
        canonical_field_key: canonicalFieldKey || undefined,
        apply_to_batch: batchScope,
        adopted_value: adopt,
        decided_by: 'local-user',
      })
      setNotice(`${ACTION_LABELS[action]}完成：处理 ${result.updated_count} 条观察，采用来源值 ${result.adopted_value_count} 条`)
      const refreshed = await loadItems()
      if (refreshed && refreshed.items.length === 0 && offset > 0) setOffset(Math.max(0, offset - pageSize))
    } catch (requestError: unknown) {
      setError(getErrorMessage(requestError, '治理操作失败，原始数据未删除'))
    } finally {
      setBusyKey(null)
    }
  }, [batchScope, loadItems, mappingBySource, offset, pageSize])

  const showHistory = useCallback(async (item: GovernanceObservation) => {
    setHistoryItem(item)
    setHistory([])
    setHistoryLoading(true)
    try {
      setHistory(await importApi.listObservationDecisions(item.id))
    } catch (requestError: unknown) {
      setError(getErrorMessage(requestError, '治理历史加载失败'))
    } finally {
      setHistoryLoading(false)
    }
  }, [])

  const revertBatch = useCallback(async (decisionBatchId: string) => {
    if (!window.confirm('确认恢复这一治理批次？系统会保留决策记录，并恢复观察和专利字段的变更前状态。')) return
    setHistoryBusyKey(decisionBatchId)
    setError('')
    try {
      const result = await importApi.revertGovernanceBatch(decisionBatchId, { reversed_by: 'local-user' })
      setNotice(`治理批次已恢复：观察 ${result.restored_observation_count} 条，专利字段 ${result.restored_value_count} 项`)
      await loadItems()
      if (historyItem) await showHistory(historyItem)
    } catch (requestError: unknown) {
      setError(getErrorMessage(requestError, '治理批次恢复失败，系统未覆盖后续修改'))
    } finally {
      setHistoryBusyKey(null)
    }
  }, [historyItem, loadItems, showHistory])

  const pageNumber = Math.floor(offset / pageSize) + 1
  const pageCount = Math.max(1, Math.ceil(total / pageSize))
  const revertibleBatchId = history.find(decision => decision.decision_batch_id && !decision.reversed)?.decision_batch_id
  const scopedDatabaseId = databaseId ? Number(databaseId) : currentDatabaseId ?? undefined

  return (
    <div className="management-page gov-page">
      <div className="page-header">
        <div>
          <h2 className="page-title">数据治理</h2>
          <p className="page-subtitle">来源差异与字段取舍</p>
        </div>
        <div className="workspace-page-actions">
          <button className="btn btn-secondary" onClick={() => navigate(databaseId ? `/db/${databaseId}/patents${location.search}` : `/patents${location.search}`)}>返回数据表</button>
          {activeView === 'fields' && <button className="btn btn-secondary" onClick={() => void loadItems()} disabled={loading}>刷新</button>}
          {activeView === 'audits' && <button className="btn btn-secondary" onClick={() => void loadAudits()} disabled={auditLoading}>刷新</button>}
        </div>
      </div>

      <div className="gov-overview">
        <div className="gov-overview-stat"><span>待处理冲突</span><strong>{conflictCount}</strong></div>
        <div className="gov-overview-stat"><span>待治理字段值</span><strong>{total}</strong></div>
        <div className="gov-overview-stat gov-overview-detail"><span>导入取舍审计</span><strong>{auditTotal}</strong></div>
      </div>

      <div className="gov-main-tabs" role="tablist" aria-label="数据治理视图">
        <button type="button" role="tab" aria-selected={activeView === 'conflicts'} className={activeView === 'conflicts' ? 'is-active' : ''} onClick={() => setActiveView('conflicts')}>
          冲突处理 <span>{conflictCount}</span>
        </button>
        <button type="button" role="tab" aria-selected={activeView === 'fields'} className={activeView === 'fields' ? 'is-active' : ''} onClick={() => setActiveView('fields')}>
          字段治理 <span>{total}</span>
        </button>
        <button type="button" role="tab" aria-selected={activeView === 'audits'} className={activeView === 'audits' ? 'is-active' : ''} onClick={() => setActiveView('audits')}>
          导入取舍审计 <span>{auditTotal}</span>
        </button>
      </div>

      {activeView === 'conflicts' ? (
        <SyncConflictQueue databaseId={scopedDatabaseId} fields={allFields} onCountChange={setConflictCount} />
      ) : activeView === 'fields' ? (
        <section className="gov-workspace">
          {error && <div className="management-error gov-message">{error}</div>}
          {notice && <div className="gov-notice gov-message" role="status">{notice}</div>}

          <div className="gov-observation-toolbar">
            <div className="gov-filter-group">
              <label className="gov-search-field">
                <span>来源列</span>
                <input className="form-input" value={sourceField} onChange={event => { setSourceField(event.target.value); setOffset(0) }} placeholder="选择或输入来源列" list="governance-source-fields" />
                <datalist id="governance-source-fields">
                  {sourceFields.map(field => <option key={field} value={field} />)}
                </datalist>
              </label>
              <label className="gov-search-field gov-id-filter">
                <span>批次 ID</span>
                <input className="form-input" value={batchId} onChange={event => { setBatchId(event.target.value.replace(/\D/g, '')); setOffset(0) }} inputMode="numeric" />
              </label>
              <label className="gov-search-field gov-id-filter">
                <span>专利 ID</span>
                <input className="form-input" value={patentId} onChange={event => { setPatentId(event.target.value.replace(/\D/g, '')); setOffset(0) }} inputMode="numeric" />
              </label>
              <label className="gov-search-field gov-id-filter">
                <span>来源行 ID</span>
                <input className="form-input" value={sourceRowId} onChange={event => { setSourceRowId(event.target.value.replace(/\D/g, '')); setOffset(0) }} inputMode="numeric" />
              </label>
            </div>
          <div className="gov-filter-options">
            <label><input type="checkbox" checked={batchScope} onChange={event => setBatchScope(event.target.checked)} />按同批次同来源列处理</label>
            <label><input type="checkbox" checked={adoptedValue} onChange={event => setAdoptedValue(event.target.checked)} />映射时采用来源值</label>
            <button className="btn btn-secondary" onClick={() => { setSourceField(''); setBatchId(''); setPatentId(''); setSourceRowId(''); setOffset(0) }} disabled={loading || (!sourceField && !batchId && !patentId && !sourceRowId)}>清除筛选</button>
            <label className="gov-audit-page-size"><span>每页</span><select className="form-input" value={pageSize} onChange={event => { setOffset(0); setPageSize(Number(event.target.value)) }}><option value={20}>20</option><option value={50}>50</option><option value={100}>100</option></select></label>
            <span>共 {total} 项</span>
            </div>
          </div>

          {loading ? (
            <div className="loading-state gov-empty">正在加载字段记录...</div>
          ) : items.length === 0 ? (
            <div className="empty-state gov-empty">当前筛选下没有待治理字段</div>
          ) : (
            <div className="gov-observation-list">
              {items.map(item => {
                const selectedField = mappingBySource[item.source_field_name] || ''
                const busy = busyKey?.startsWith(`${item.id}:`) ?? false
                const quarantined = item.field_resolution === 'quarantined' || item.source_row_status === 'retained_source_row' || item.source_row_status === 'quarantined'
                return (
                  <article className="gov-observation-card" key={item.id}>
                    <header className="gov-observation-header">
                      <div className="gov-observation-field">
                        <strong>{item.source_field_name}</strong>
                        <span>{RESOLUTION_LABELS[item.field_resolution] || item.field_resolution} · {DIFFERENCE_LABELS[item.difference_type] || item.difference_type}</span>
                      </div>
                      <div className="gov-observation-source">
                        <strong title={item.filename}>{compact(item.filename)}</strong>
                        <span>{compact(item.source_table_title)}{item.worksheet_name ? ` · ${compact(item.worksheet_name)}` : ''}</span>
                      </div>
                    </header>

                    <div className="gov-observation-meta">
                      <span>{item.patent_id ? `专利 #${item.patent_id}` : '尚未关联专利'}</span>
                      <span>批次 #{item.batch_id}</span>
                      <span>来源第 {item.source_row} 行</span>
                      {item.source_row_reason && <span title={item.source_row_reason}>{compact(item.source_row_reason)}</span>}
                      <span>最近决策 {item.final_decision ? REVIEW_ACTION_LABELS[item.final_decision] || item.final_decision : '未处理'} · {formatDate(item.decided_at)}</span>
                    </div>

                    <div className="gov-observation-values">
                      <div className="gov-value-panel gov-value-base"><span>来源原始值</span><pre>{item.raw_value || '-'}</pre></div>
                      <div className="gov-value-panel gov-value-local"><span>当前字段值</span><pre>{item.current_value || '-'}</pre></div>
                      <div className="gov-value-panel gov-value-remote"><span>候选值</span><pre>{item.candidate_value || '-'}</pre></div>
                    </div>

                    {item.source_row_values && Object.keys(item.source_row_values).length > 0 && (
                      <details className="gov-evidence-details">
                        <summary>展开来源行证据 · {Object.keys(item.source_row_values).length} 个字段</summary>
                        <div className="gov-evidence-grid">
                          {Object.entries(item.source_row_values).map(([key, value]) => {
                            const evidence = typeof value === 'string' ? value : JSON.stringify(value)
                            return (
                              <div key={key}>
                                <strong>{key}</strong>
                                <span title={evidence}>{compact(evidence)}</span>
                                {item.source_row_hyperlinks?.[key] && <a href={item.source_row_hyperlinks[key]} target="_blank" rel="noreferrer">打开来源链接</a>}
                              </div>
                            )
                          })}
                        </div>
                      </details>
                    )}

                    <footer className="gov-observation-actions">
                      <div className="gov-mapping-control">
                        <label htmlFor={`governance-map-${item.id}`}>映射到已有字段</label>
                        <select
                          id={`governance-map-${item.id}`}
                          className="form-input"
                          value={selectedField}
                          onChange={event => setMappingBySource(previous => ({ ...previous, [item.source_field_name]: event.target.value }))}
                        >
                          <option value="">选择字段</option>
                          {fields.map(field => <option key={field.key} value={field.key}>{field.name} ({field.key})</option>)}
                        </select>
                      </div>
                      {quarantined ? (
                        <span className="gov-quarantine-note">来源行需修正后重新导入；原始值已保留</span>
                      ) : (
                        <div className="gov-action-group">
                          <button className="btn btn-secondary" disabled={busy} onClick={() => void decide(item, 'retain_source')}>保留来源</button>
                          <button className="btn btn-secondary" disabled={busy} onClick={() => void decide(item, 'ignore')}>忽略展示</button>
                          <button className="btn btn-primary" disabled={busy || !selectedField} onClick={() => void decide(item, 'map_existing', adoptedValue)}>映射字段</button>
                          <button className="btn btn-secondary" disabled={busy} onClick={() => void decide(item, 'propose_field')}>提交候选</button>
                          <button className="btn btn-secondary" disabled={busy} onClick={() => void showHistory(item)}>查看历史</button>
                        </div>
                      )}
                    </footer>
                  </article>
                )
              })}
            </div>
          )}

          <div className="gov-pagination">
            <button className="btn btn-secondary" disabled={offset === 0 || loading} onClick={() => setOffset(Math.max(0, offset - pageSize))}>上一页</button>
            <span>第 {pageNumber} / {pageCount} 页</span>
            <button className="btn btn-secondary" disabled={offset + pageSize >= total || loading} onClick={() => setOffset(offset + pageSize)}>下一页</button>
          </div>
        </section>
      ) : (
        <section className="gov-workspace">
          {error && <div className="management-error gov-message">{error}</div>}
          <div className="gov-audit-toolbar">
            <label className="gov-search-field gov-audit-search">
              <span>检索专利、字段或来源</span>
              <input className="form-input" value={auditSearch} onChange={event => setAuditSearch(event.target.value)} onKeyDown={event => { if (event.key === 'Enter') { setAuditOffset(0); setAuditQuery(auditSearch.trim()) } }} placeholder="标题、专利号、字段名、来源" />
            </label>
            <label className="gov-search-field gov-field-filter">
              <span>字段</span>
              <input className="form-input" value={auditField} onChange={event => { setAuditField(event.target.value); setAuditOffset(0) }} placeholder="全部字段" list="governance-audit-fields" />
              <datalist id="governance-audit-fields">{allFields.map(field => <option key={field.key} value={field.key} label={field.name} />)}</datalist>
            </label>
            <label className="gov-search-field gov-audit-source">
              <span>导入来源</span>
              <select className="form-input" value={auditSource} onChange={event => { setAuditSource(event.target.value); setAuditOffset(0) }}>
                <option value="">全部来源</option>
                <option value="file_import">文件导入</option>
                <option value="collaboration_sync">协同同步</option>
                <option value="department_publication">部门发布</option>
                <option value="external_sync">外部同步</option>
                <option value="governance_import">治理映射</option>
              </select>
            </label>
            <button className="btn btn-secondary" onClick={() => { setAuditOffset(0); setAuditQuery(auditSearch.trim()) }} disabled={auditLoading}>查询</button>
            <button className="btn btn-secondary" onClick={() => { setAuditSearch(''); setAuditQuery(''); setAuditField(''); setAuditSource(''); setAuditOffset(0) }} disabled={auditLoading || (!auditSearch && !auditQuery && !auditField && !auditSource)}>清除</button>
            <label className="gov-audit-page-size"><span>每页</span><select className="form-input" value={auditPageSize} onChange={event => { setAuditOffset(0); setAuditPageSize(Number(event.target.value)) }}><option value={30}>30</option><option value={50}>50</option><option value={100}>100</option></select></label>
            <span className="gov-result-count">共 {auditTotal} 条</span>
          </div>
          {auditLoading ? <div className="loading-state gov-empty">正在加载导入取舍审计...</div> : auditItems.length === 0 ? <div className="empty-state gov-empty">当前筛选下没有非空异值取舍记录</div> : (
            <div className="gov-observation-list">
              {auditItems.map(item => (
                <article className="gov-audit-item" key={item.id}>
                  <header className="gov-audit-header">
                    <div className="gov-conflict-subject">
                      <strong>{item.patent_id ? <Link className="gov-patent-link" to={databaseId ? `/db/${databaseId}/patents/${item.patent_id}` : `/patents/${item.patent_id}`}>{item.patent_title || `专利 #${item.patent_id}`}</Link> : item.patent_title || `专利 #${item.patent_uid || '已删除'}`}</strong>
                      <span>{[item.application_number, item.publication_number].filter(Boolean).join(' · ') || `专利 #${item.patent_id}`}</span>
                    </div>
                    <div className="gov-conflict-tags">
                      <span className="gov-tag gov-tag-field">{item.field_key}</span>
                      <span className="gov-tag">{item.source_label || item.source_kind}</span>
                      <span className="gov-tag">{item.resolution === 'merge' ? '融合合并' : item.resolution === 'manual' ? '自定义取值' : item.resolution === 'keep_existing' ? '保留原值' : item.resolution === 'quarantine' ? '隔离待处理' : '采用导入值'}</span>
                    </div>
                  </header>
                  <div className="gov-audit-context">
                    <span>{formatDate(item.created_at)}</span>
                    {item.import_batch_id && <span>批次 #{item.import_batch_id}</span>}
                    {item.source_row && <span>来源第 {item.source_row} 行</span>}
                    {item.source_field_name && <span>来源列：{item.source_field_name}</span>}
                    {item.decided_by && <span>处理人：{item.decided_by}</span>}
                  </div>
                  <div className="gov-value-grid gov-audit-values">
                    <div className="gov-value-panel gov-value-local"><span>导入前</span><pre>{displayAuditValue(item.old_value)}</pre></div>
                    <div className="gov-value-panel gov-value-remote"><span>导入候选</span><pre>{displayAuditValue(item.incoming_value)}</pre></div>
                    <div className="gov-value-panel gov-value-final"><span>最终值</span><pre>{displayAuditValue(item.final_value)}</pre></div>
                  </div>
                  {item.reason && <p className="gov-audit-reason">{item.reason}</p>}
                </article>
              ))}
            </div>
          )}
          <div className="gov-pagination">
            <button className="btn btn-secondary" disabled={auditOffset === 0 || auditLoading} onClick={() => setAuditOffset(Math.max(0, auditOffset - auditPageSize))}>上一页</button>
            <span>第 {Math.floor(auditOffset / auditPageSize) + 1} / {Math.max(1, Math.ceil(auditTotal / auditPageSize))} 页</span>
            <button className="btn btn-secondary" disabled={auditOffset + auditPageSize >= auditTotal || auditLoading} onClick={() => setAuditOffset(auditOffset + auditPageSize)}>下一页</button>
          </div>
        </section>
      )}

      {historyItem && activeView === 'fields' && (
        <section className="gov-history-panel">
          <div className="gov-history-header">
            <div>
              <h3>治理历史</h3>
              <div>{historyItem.source_field_name} / 第 {historyItem.source_row} 行 / {compact(historyItem.raw_value)}</div>
            </div>
            <div className="gov-action-group">
              {revertibleBatchId && (
                <button className="btn btn-secondary" disabled={historyBusyKey !== null} onClick={() => void revertBatch(revertibleBatchId)}>
                  恢复最近治理批次
                </button>
              )}
              <button className="btn btn-secondary" onClick={() => { setHistoryItem(null); setHistory([]) }}>关闭</button>
            </div>
          </div>
          {historyLoading ? (
            <div className="loading-state gov-empty">加载中...</div>
          ) : history.length === 0 ? (
            <div className="empty-state gov-empty">暂无治理历史</div>
          ) : (
            <div className="management-table gov-history-table">
              <table className="data-grid">
                <thead><tr><th>时间</th><th>动作</th><th>批次</th><th>映射版本</th><th>操作者</th><th>原因</th><th>状态</th></tr></thead>
                <tbody>
                  {history.map(decision => (
                    <tr key={decision.id}>
                      <td>{formatDate(decision.created_at)}</td>
                      <td>{ACTION_LABELS[decision.action]}</td>
                      <td title={decision.decision_batch_id || ''}>{compact(decision.decision_batch_id)}</td>
                      <td>{decision.mapping_version || '-'}</td>
                      <td>{decision.decided_by}</td>
                      <td>{compact(decision.reason)}</td>
                      <td>{decision.reversed ? '已恢复' : '已执行'}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </section>
      )}
    </div>
  )
}
