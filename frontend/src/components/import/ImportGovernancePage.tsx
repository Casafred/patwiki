import { useCallback, useEffect, useMemo, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { fieldApi, importApi } from '../../api'
import type { FieldMeta, GovernanceAction, GovernanceDecision, GovernanceObservation } from '../../types'
import { getErrorMessage } from '../../lib/errors'

const ACTION_LABELS: Record<GovernanceAction, string> = {
  retain_source: '保留来源',
  ignore: '忽略默认展示',
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

function compact(value?: string | null) {
  if (!value) return '-'
  return value.length > 120 ? `${value.slice(0, 120)}...` : value
}

function formatDate(value?: string | null) {
  if (!value) return '-'
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString('zh-CN')
}

export default function ImportGovernancePage() {
  const [searchParams] = useSearchParams()
  const [items, setItems] = useState<GovernanceObservation[]>([])
  const [total, setTotal] = useState(0)
  const [offset, setOffset] = useState(0)
  const pageSize = 50
  const [fields, setFields] = useState<FieldMeta[]>([])
  const [sourceField, setSourceField] = useState('')
  const [batchId, setBatchId] = useState('')
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

  const loadItems = useCallback(async () => {
    setLoading(true)
    setError('')
    try {
      const result = await importApi.listUnmapped({
        source_field: sourceField.trim() || undefined,
        batch_id: batchId.trim() ? Number(batchId) : undefined,
        patent_id: patentId.trim() ? Number(patentId) : undefined,
        source_row_id: sourceRowId.trim() ? Number(sourceRowId) : undefined,
        offset,
        limit: pageSize,
      })
      setItems(result.items)
      setTotal(result.total)
      return result
    } catch (requestError: unknown) {
      setError(getErrorMessage(requestError, '待治理属性加载失败'))
    } finally {
      setLoading(false)
    }
    return null
  }, [batchId, offset, pageSize, patentId, sourceField, sourceRowId])

  useEffect(() => {
    // Synchronize the table with the current filters.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    void loadItems()
  }, [loadItems])

  useEffect(() => {
    fieldApi.list()
      .then(result => setFields(result.filter(field => field.editable !== false && !field.is_formula)))
      .catch(() => setFields([]))
  }, [])

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

  return (
    <div className="management-page">
      <div className="page-header">
        <div>
          <h2 className="page-title">数据治理</h2>
          <p className="page-subtitle">处理未知导入属性，保留来源证据后再决定是否升级为正式字段</p>
        </div>
        <button className="btn btn-secondary" onClick={() => void loadItems()} disabled={loading}>刷新</button>
      </div>

      {error && <div className="management-error" style={{ marginBottom: 12 }}>{error}</div>}
      {notice && <div style={{ margin: '0 28px 12px', padding: '9px 12px', border: '1px solid #bfe6de', borderRadius: 6, background: '#eefaf7', color: '#226d65', fontSize: 12 }}>{notice}</div>}

      <div className="management-split" style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap', marginBottom: 12 }}>
        <input className="form-input" value={sourceField} onChange={event => { setSourceField(event.target.value); setOffset(0) }} placeholder="按来源列筛选" style={{ width: 190 }} list="governance-source-fields" />
        <datalist id="governance-source-fields">
          {sourceFields.map(field => <option key={field} value={field} />)}
        </datalist>
        <input className="form-input" value={batchId} onChange={event => { setBatchId(event.target.value.replace(/\D/g, '')); setOffset(0) }} placeholder="导入批次 ID" inputMode="numeric" style={{ width: 130 }} />
        <input className="form-input" value={patentId} onChange={event => { setPatentId(event.target.value.replace(/\D/g, '')); setOffset(0) }} placeholder="专利 ID" inputMode="numeric" style={{ width: 110 }} />
        <input className="form-input" value={sourceRowId} onChange={event => { setSourceRowId(event.target.value.replace(/\D/g, '')); setOffset(0) }} placeholder="来源行 ID" inputMode="numeric" style={{ width: 120 }} />
        <label style={{ display: 'inline-flex', alignItems: 'center', gap: 5, fontSize: 12, color: '#475569' }}>
          <input type="checkbox" checked={batchScope} onChange={event => setBatchScope(event.target.checked)} />
          按同批次同来源列处理
        </label>
        <label style={{ display: 'inline-flex', alignItems: 'center', gap: 5, fontSize: 12, color: '#475569' }}>
          <input type="checkbox" checked={adoptedValue} onChange={event => setAdoptedValue(event.target.checked)} />
          映射时采用来源值覆盖已有值
        </label>
        <span style={{ marginLeft: 'auto', color: '#64748b', fontSize: 12 }}>待处理 {total} 条，本页 {items.length} 条</span>
      </div>

      <div className="management-table" style={{ overflowX: 'auto' }}>
        {loading ? (
          <div className="loading-state" style={{ minHeight: 180 }}>加载中...</div>
        ) : items.length === 0 ? (
          <div className="empty-state" style={{ minHeight: 180 }}>暂无待治理属性</div>
        ) : (
          <table className="data-grid" style={{ minWidth: 1280 }}>
            <thead>
              <tr>
                <th>来源</th>
                <th>专利/行</th>
                <th>原始列</th>
                <th>原始值</th>
                <th>当前值</th>
                <th>候选值</th>
                <th>差异</th>
                <th>映射目标</th>
                <th>操作</th>
              </tr>
            </thead>
            <tbody>
              {items.map(item => {
                const selectedField = mappingBySource[item.source_field_name] || ''
                const busy = busyKey?.startsWith(`${item.id}:`) ?? false
                return (
                  <tr key={item.id}>
                    <td style={{ maxWidth: 180 }}>
                      <div title={item.filename}>{compact(item.filename)}</div>
                      <small>{compact(item.source_table_title)} / {compact(item.worksheet_name)}</small>
                    </td>
                    <td>{item.patent_id ? `#${item.patent_id}` : '待补身份'}<br /><small>第 {item.source_row} 行</small></td>
                    <td><strong>{item.source_field_name}</strong><br /><small>{item.field_resolution}</small></td>
                    <td title={item.raw_value || ''}>{compact(item.raw_value)}</td>
                    <td title={item.current_value || ''}>{compact(item.current_value)}</td>
                    <td title={item.candidate_value || ''}>{compact(item.candidate_value)}</td>
                    <td>{DIFFERENCE_LABELS[item.difference_type] || item.difference_type}</td>
                    <td>
                      <select
                        className="form-input"
                        value={selectedField}
                        onChange={event => setMappingBySource(previous => ({ ...previous, [item.source_field_name]: event.target.value }))}
                        style={{ minWidth: 170 }}
                      >
                        <option value="">选择已有字段</option>
                        {fields.map(field => <option key={field.key} value={field.key}>{field.name} ({field.key})</option>)}
                      </select>
                    </td>
                    <td>
                      <div style={{ display: 'flex', gap: 5, flexWrap: 'wrap', minWidth: 260 }}>
                        <button className="btn btn-secondary" disabled={busy} onClick={() => void decide(item, 'retain_source')}>保留来源</button>
                        <button className="btn btn-secondary" disabled={busy} onClick={() => void decide(item, 'ignore')}>忽略</button>
                        <button className="btn btn-secondary" disabled={busy || !selectedField} onClick={() => void decide(item, 'map_existing', adoptedValue)}>映射</button>
                        <button className="btn btn-secondary" disabled={busy} onClick={() => void decide(item, 'propose_field')}>提交候选</button>
                        <button className="btn btn-secondary" disabled={busy} onClick={() => void showHistory(item)}>查看历史</button>
                      </div>
                      <small style={{ display: 'block', marginTop: 4 }}>最近决策：{item.final_decision || '-'} / {formatDate(item.decided_at)}</small>
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        )}
      </div>

      <div style={{ display: 'flex', justifyContent: 'flex-end', alignItems: 'center', gap: 10, marginTop: 12 }}>
        <button className="btn btn-secondary" disabled={offset === 0 || loading} onClick={() => setOffset(Math.max(0, offset - pageSize))}>上一页</button>
        <span style={{ color: '#64748b', fontSize: 12 }}>第 {pageNumber} / {pageCount} 页</span>
        <button className="btn btn-secondary" disabled={offset + pageSize >= total || loading} onClick={() => setOffset(offset + pageSize)}>下一页</button>
      </div>

      {historyItem && (
        <section style={{ marginTop: 18, borderTop: '1px solid #e2e8f0', paddingTop: 14 }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 12, flexWrap: 'wrap' }}>
            <div>
              <h3 style={{ margin: 0, fontSize: 15, color: '#1e293b' }}>治理历史</h3>
              <div style={{ marginTop: 4, color: '#64748b', fontSize: 12 }}>
                {historyItem.source_field_name} / 第 {historyItem.source_row} 行 / {compact(historyItem.raw_value)}
              </div>
            </div>
            <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
              {revertibleBatchId && (
                <button className="btn btn-secondary" disabled={historyBusyKey !== null} onClick={() => void revertBatch(revertibleBatchId)}>
                  恢复最近治理批次
                </button>
              )}
              <button className="btn btn-secondary" onClick={() => { setHistoryItem(null); setHistory([]) }}>关闭</button>
            </div>
          </div>
          {historyLoading ? (
            <div className="loading-state" style={{ minHeight: 80 }}>加载中...</div>
          ) : history.length === 0 ? (
            <div className="empty-state" style={{ minHeight: 80 }}>暂无治理历史</div>
          ) : (
            <div className="management-table" style={{ overflowX: 'auto', marginTop: 10 }}>
              <table className="data-grid" style={{ minWidth: 900 }}>
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
