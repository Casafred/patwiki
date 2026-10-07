import { useCallback, useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { collaborationSyncApi } from '../../api'
import type { FieldMeta, JsonValue, SyncGovernanceConflict } from '../../types'
import { formatApiDateTime } from '../../lib/date'
import { getErrorMessage } from '../../lib/errors'
import { mergeImportedCollectionValues } from '../../lib/importMerge'

const PAGE_SIZE = 30

function displayValue(value: unknown) {
  if (value === null || value === undefined || value === '') return '（空）'
  if (typeof value === 'string') return value
  if (typeof value === 'object') return JSON.stringify(value, null, 2)
  return String(value)
}

function initialManualValue(value: unknown) {
  return typeof value === 'string' ? value : displayValue(value) === '（空）' ? '' : JSON.stringify(value, null, 2)
}

function initialMergedValue(item: SyncGovernanceConflict) {
  const local = item.current_local_value_available ? item.current_local_value : item.local_value
  const incoming = item.remote_value
  if (Array.isArray(local) && Array.isArray(incoming)) {
    const merged = mergeImportedCollectionValues(item.field_key, local, incoming)
    return JSON.stringify(merged, null, 2)
  }
  return initialManualValue(incoming)
}

function fieldLabel(fieldKey: string, fields: FieldMeta[]) {
  if (fieldKey === '__delete__') return '删除记录'
  const actualFieldKey = fieldKey.startsWith('library:') ? fieldKey.split(':').slice(2).join(':') : fieldKey
  const field = fields.find(item => item.key === actualFieldKey)
  return field
    ? `${fieldKey.startsWith('library:') ? '共享字段 · ' : ''}${field.name} · ${field.key}`
    : fieldKey.startsWith('library:') ? `共享字段 · ${actualFieldKey}` : fieldKey
}

function mergeAllowed(fieldKey: string, fields: FieldMeta[]) {
  const actualFieldKey = fieldKey.startsWith('library:') ? fieldKey.split(':').slice(2).join(':') : fieldKey
  if (['__delete__', 'application_number', 'publication_number', 'grant_number', 'filing_date', 'publication_date', 'grant_date', 'priority_date', 'legal_status_date', 'legal_status', 'patent_type', 'has_risk', 'risk_level', 'country'].includes(actualFieldKey)) return false
  const field = fields.find(item => item.key === actualFieldKey)
  if (!field) return fieldKey.startsWith('library:')
  const type = field.field_type?.toLowerCase()
  return !['date', 'datetime', 'number', 'boolean', 'single_select', 'select', 'rating', 'link', 'url', 'attachment', 'formula', 'lookup', 'rollup'].includes(type || '')
}

function parseManualValue(fieldKey: string, text: string, fields: FieldMeta[], forceJson = false): JsonValue {
  const actualFieldKey = fieldKey.startsWith('library:') ? fieldKey.split(':').slice(2).join(':') : fieldKey
  const field = fields.find(item => item.key === actualFieldKey)
  if (forceJson || actualFieldKey === 'custom_fields' || field?.field_type === 'multiselect' || field?.field_type === 'multi_select') {
    return JSON.parse(text) as JsonValue
  }
  if (field?.field_type === 'number') {
    const value = Number(text)
    if (!Number.isFinite(value)) throw new Error('请输入有效数字')
    return value
  }
  if (field?.field_type === 'boolean') {
    if (text.toLowerCase() === 'true' || text === '是') return true
    if (text.toLowerCase() === 'false' || text === '否') return false
    throw new Error('布尔字段请输入 true 或 false')
  }
  return text
}

export default function SyncConflictQueue({
  databaseId,
  fields,
  onCountChange,
}: {
  databaseId?: number
  fields: FieldMeta[]
  onCountChange?: (count: number) => void
}) {
  const [status, setStatus] = useState<'pending' | 'resolved'>('pending')
  const [pageSize, setPageSize] = useState(PAGE_SIZE)
  const [items, setItems] = useState<SyncGovernanceConflict[]>([])
  const [total, setTotal] = useState(0)
  const [offset, setOffset] = useState(0)
  const [fieldFilter, setFieldFilter] = useState('')
  const [queryInput, setQueryInput] = useState('')
  const [query, setQuery] = useState('')
  const [selected, setSelected] = useState<Set<string>>(new Set())
  const [sourceChoices, setSourceChoices] = useState<Record<string, string>>({})
  const [manualValues, setManualValues] = useState<Record<string, { value: string; reason: string }>>({})
  const [manualOpenUid, setManualOpenUid] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')

  const loadConflicts = useCallback(async () => {
    setLoading(true)
    setError('')
    try {
      const result = await collaborationSyncApi.listGovernanceConflicts({
        database_id: databaseId,
        status,
        q: query || undefined,
        field_key: fieldFilter || undefined,
        offset,
        limit: pageSize,
      })
      setItems(result.items)
      setTotal(result.total)
      if (status === 'pending' && !query && !fieldFilter) onCountChange?.(result.total)
      setSelected(new Set())
    } catch (requestError: unknown) {
      setError(getErrorMessage(requestError, '冲突队列加载失败'))
    } finally {
      setLoading(false)
    }
  }, [databaseId, fieldFilter, offset, onCountChange, pageSize, query, status])

  useEffect(() => {
    // Keep the queue current when its database, filters, or page changes.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    void loadConflicts()
  }, [loadConflicts])

  const pageNumber = Math.floor(offset / pageSize) + 1
  const pageCount = Math.max(1, Math.ceil(total / pageSize))
  const selectedItems = useMemo(() => items.filter(item => selected.has(item.conflict_uid)), [items, selected])
  const allVisibleSelected = items.length > 0 && items.every(item => selected.has(item.conflict_uid))

  const resolvedSourceUid = useCallback((item: SyncGovernanceConflict) => {
    const selectedUid = sourceChoices[item.conflict_uid]
    if (selectedUid) return selectedUid
    if (item.source_database_uid) return item.source_database_uid
    if (item.source_database_options.length === 1) return item.source_database_options[0].database_uid
    return undefined
  }, [sourceChoices])

  const applyDecisions = useCallback(async (
    decisions: Array<{ item: SyncGovernanceConflict; choice: 'local' | 'remote' | 'manual' | 'merge'; value?: JsonValue; reason?: string }>,
  ) => {
    if (!decisions.length) return
    const groups = new Map<string, {
      packageUid: string
      databaseId: number
      sourceDatabaseUid?: string
      decisions: Array<{ entity_uid: string; field_key: string; choice: 'local' | 'remote' | 'manual' | 'merge'; value?: JsonValue; reason?: string }>
    }>()
    for (const decision of decisions) {
      const sourceDatabaseUid = resolvedSourceUid(decision.item)
      if (decision.item.source_database_options.length > 1 && !sourceDatabaseUid) {
        throw new Error(`“${decision.item.patent_title || decision.item.entity_uid}”对应多个来源库，请先选择来源库`)
      }
      const key = `${decision.item.package_uid}:${decision.item.target_database_id}:${sourceDatabaseUid || ''}`
      const group = groups.get(key) || {
        packageUid: decision.item.package_uid,
        databaseId: decision.item.target_database_id,
        sourceDatabaseUid,
        decisions: [],
      }
      group.decisions.push({
        entity_uid: decision.item.entity_uid,
        field_key: decision.item.field_key,
        choice: decision.choice,
        value: decision.value,
        reason: decision.reason,
      })
      groups.set(key, group)
    }

    setBusy(true)
    setError('')
    setNotice('')
    let completed = 0
    let remaining = 0
    const failures: string[] = []
    try {
      for (const group of groups.values()) {
        try {
          const result = await collaborationSyncApi.apply(group.packageUid, {
            database_id: group.databaseId,
            source_database_uid: group.sourceDatabaseUid,
            decisions: group.decisions,
          })
          completed += group.decisions.length
          remaining += result.pending_conflicts
        } catch (requestError: unknown) {
          failures.push(`${group.packageUid}：${getErrorMessage(requestError, '提交失败')}`)
        }
      }
      if (failures.length) {
        setError(`已处理 ${completed} 项，其余未完成：${failures.join('；')}`)
      } else {
        setNotice(`已处理 ${completed} 项冲突${remaining ? `；仍有 ${remaining} 项待处理` : ''}`)
      }
      setManualOpenUid(null)
      setManualValues({})
      setSourceChoices({})
      setSelected(new Set())
      await loadConflicts()
    } finally {
      setBusy(false)
    }
  }, [loadConflicts, resolvedSourceUid])

  const decideOne = async (item: SyncGovernanceConflict, choice: 'local' | 'remote') => {
    try {
      await applyDecisions([{ item, choice, reason: choice === 'local' ? '数据治理：保留本地值' : '数据治理：采用来源值' }])
    } catch (requestError: unknown) {
      setError(getErrorMessage(requestError, '冲突决策失败'))
    }
  }

  const decideManual = async (item: SyncGovernanceConflict) => {
    const form = manualValues[item.conflict_uid] || { value: initialMergedValue(item), reason: '' }
    try {
      const localValue = item.current_local_value_available ? item.current_local_value : item.local_value
      const forceJson = Array.isArray(localValue) || Array.isArray(item.remote_value)
      const value = parseManualValue(item.field_key, form.value, fields, forceJson)
      await applyDecisions([{
        item,
        choice: 'merge',
        value,
        reason: form.reason.trim() || '数据治理：融合本地值与来源增量',
      }])
    } catch (requestError: unknown) {
      setError(getErrorMessage(requestError, '合并值格式无效'))
    }
  }

  const decideSelected = async (choice: 'local' | 'remote') => {
    if (choice === 'remote' && selectedItems.some(item => item.field_key === '__delete__')
      && !window.confirm('所选内容包含远端删除操作。确认从目标数据库移除这些专利记录？')) return
    try {
      await applyDecisions(selectedItems.map(item => ({
        item,
        choice,
        reason: choice === 'local' ? '数据治理：批量保留本地值' : '数据治理：批量采用来源值',
      })))
    } catch (requestError: unknown) {
      setError(getErrorMessage(requestError, '批量冲突决策失败'))
    }
  }

  const submitSearch = () => {
    setOffset(0)
    setQuery(queryInput.trim())
  }

  return (
    <section className="gov-workspace">
      <div className="gov-queue-toolbar">
        <div className="gov-filter-group">
          <label className="gov-search-field">
            <span>检索专利、同步包或字段</span>
            <input
              className="form-input"
              value={queryInput}
              onChange={event => setQueryInput(event.target.value)}
              onKeyDown={event => { if (event.key === 'Enter') submitSearch() }}
              placeholder="标题、申请号、公开号、包 UID"
            />
          </label>
          <label className="gov-search-field gov-field-filter">
            <span>字段</span>
            <input className="form-input" value={fieldFilter} onChange={event => { setFieldFilter(event.target.value); setOffset(0) }} list="governance-conflict-fields" placeholder="全部字段" />
            <datalist id="governance-conflict-fields">
              {fields.map(field => <option key={field.key} value={field.key} label={field.name} />)}
            </datalist>
          </label>
          <button className="btn btn-secondary" onClick={submitSearch} disabled={loading || busy}>查询</button>
          <button className="btn btn-secondary" onClick={() => { setFieldFilter(''); setQueryInput(''); setQuery(''); setOffset(0) }} disabled={loading || busy || (!fieldFilter && !query && !queryInput)}>清除筛选</button>
        </div>
        <button className="btn btn-secondary" onClick={() => void loadConflicts()} disabled={loading || busy}>刷新</button>
      </div>

      <div className="gov-status-tabs" role="tablist" aria-label="冲突状态">
        <button type="button" className={status === 'pending' ? 'is-active' : ''} role="tab" aria-selected={status === 'pending'} onClick={() => { setStatus('pending'); setOffset(0) }}>待处理</button>
        <button type="button" className={status === 'resolved' ? 'is-active' : ''} role="tab" aria-selected={status === 'resolved'} onClick={() => { setStatus('resolved'); setOffset(0) }}>已处理</button>
        <span className="gov-result-count">{loading ? '读取中' : `${total} 项`}</span>
        <label className="gov-audit-page-size"><span>每页</span><select className="form-input" value={pageSize} onChange={event => { setOffset(0); setPageSize(Number(event.target.value)) }}><option value={30}>30</option><option value={50}>50</option><option value={100}>100</option></select></label>
      </div>

      {error && <div className="management-error gov-message">{error}</div>}
      {notice && <div className="gov-notice gov-message" role="status">{notice}</div>}

      {status === 'pending' && items.length > 0 && (
        <div className="gov-bulk-toolbar">
          <label>
            <input
              type="checkbox"
              checked={allVisibleSelected}
              onChange={event => setSelected(event.target.checked ? new Set(items.map(item => item.conflict_uid)) : new Set())}
            />
            选择本页
          </label>
          <span>{selected.size ? `已选 ${selected.size} 项` : '勾选多项后可批量决策'}</span>
          <button className="btn btn-secondary" disabled={busy || !selected.size} onClick={() => void decideSelected('local')}>批量保留本地</button>
          <button className="btn btn-primary" disabled={busy || !selected.size} onClick={() => void decideSelected('remote')}>批量采用来源</button>
        </div>
      )}

      {loading ? (
        <div className="loading-state gov-empty">正在加载冲突队列...</div>
      ) : items.length === 0 ? (
        <div className="empty-state gov-empty">{status === 'pending' ? '当前筛选下没有待处理冲突' : '还没有已处理冲突记录'}</div>
      ) : (
        <div className="gov-conflict-list">
          {items.map(item => {
            const manualForm = manualValues[item.conflict_uid] || { value: initialMergedValue(item), reason: '' }
            const selectedSource = resolvedSourceUid(item)
            const label = fieldLabel(item.field_key, fields)
            const patentIdentity = [item.application_number, item.publication_number, item.grant_number].filter(Boolean).join(' · ')
            return (
              <article className="gov-conflict-item" key={item.conflict_uid}>
                <header className="gov-conflict-header">
                  {status === 'pending' && (
                    <input
                      type="checkbox"
                      aria-label={`选择 ${item.patent_title || item.entity_uid} 的 ${label} 冲突`}
                      checked={selected.has(item.conflict_uid)}
                      onChange={event => setSelected(previous => {
                        const next = new Set(previous)
                        if (event.target.checked) next.add(item.conflict_uid)
                        else next.delete(item.conflict_uid)
                        return next
                      })}
                    />
                  )}
                  <div className="gov-conflict-subject">
                    <strong>
                      {item.patent_id
                        ? <Link className="gov-patent-link" to={databaseId ? `/db/${databaseId}/patents/${item.patent_id}` : `/patents/${item.patent_id}`}>{item.patent_title || '专利记录'}</Link>
                        : item.patent_title || '专利记录'}
                    </strong>
                    <span>{patentIdentity || `实体 UID ${item.entity_uid}`}{item.patent_id ? ` · #${item.patent_id}` : ''}</span>
                  </div>
                  <div className="gov-conflict-tags">
                    <span className="gov-tag gov-tag-field">{label}</span>
                    <span className="gov-tag">{item.source_database_name || '同步来源'}</span>
                    <span className="gov-tag">目标：{item.target_database_name}</span>
                  </div>
                </header>

                <div className="gov-conflict-context">
                  <span>同步包 <code>{item.package_uid}</code></span>
                  <span>发现时间 {formatApiDateTime(item.created_at)}</span>
                  {item.source_database_options.length > 1 && (
                    <label className="gov-source-choice">
                      <span>来源库</span>
                      <select className="form-input" value={selectedSource || ''} onChange={event => setSourceChoices(previous => ({ ...previous, [item.conflict_uid]: event.target.value }))}>
                        <option value="">选择来源库</option>
                        {item.source_database_options.map(option => <option key={option.database_uid} value={option.database_uid}>{option.name}</option>)}
                      </select>
                    </label>
                  )}
                </div>

                <div className="gov-value-grid">
                  <div className="gov-value-panel gov-value-base">
                    <span>共同基线</span>
                    <pre>{displayValue(item.base_value)}</pre>
                  </div>
                  <div className="gov-value-panel gov-value-local">
                    <span>本地当前值</span>
                    <pre>{displayValue(item.current_local_value ?? item.local_value)}</pre>
                    {item.current_local_value_available && JSON.stringify(item.current_local_value) !== JSON.stringify(item.local_value) && (
                      <small>冲突发现时：{displayValue(item.local_value)}</small>
                    )}
                  </div>
                  <div className="gov-value-panel gov-value-remote">
                    <span>同步来源值</span>
                    <pre>{displayValue(item.remote_value)}</pre>
                  </div>
                </div>

                {status === 'pending' ? (
                  <>
                    {manualOpenUid === item.conflict_uid && (
                      <div className="gov-manual-editor">
                        <label>
                          合并后的值
                          <textarea className="form-input" value={manualForm.value} onChange={event => setManualValues(previous => ({ ...previous, [item.conflict_uid]: { ...manualForm, value: event.target.value } }))} rows={3} />
                        </label>
                        <small className="gov-merge-hint">集合值已按去重并集预填；其他字段请在此整理最终值。</small>
                        <label>
                          决策原因
                          <input className="form-input" value={manualForm.reason} onChange={event => setManualValues(previous => ({ ...previous, [item.conflict_uid]: { ...manualForm, reason: event.target.value } }))} placeholder="可选，写入决策审计" />
                        </label>
                        <button className="btn btn-primary" disabled={busy || item.source_database_options.length > 1 && !selectedSource} onClick={() => void decideManual(item)}>保存合并结果</button>
                        <button className="btn btn-secondary" disabled={busy} onClick={() => setManualOpenUid(null)}>取消</button>
                      </div>
                    )}
                    <footer className="gov-conflict-actions">
                      <span>选择后会重新核对同步包中的冲突，再写入决定值。</span>
                      <div>
                        <button className="btn btn-secondary" disabled={busy || item.source_database_options.length > 1 && !selectedSource} onClick={() => void decideOne(item, 'local')}>保留本地</button>
                        <button className="btn btn-primary" disabled={busy || item.source_database_options.length > 1 && !selectedSource} onClick={() => void decideOne(item, 'remote')}>{item.field_key === '__delete__' ? '接受远端删除' : '采用来源'}</button>
                        <button className="btn btn-secondary" disabled={busy || !mergeAllowed(item.field_key, fields)} onClick={() => {
                          const nextOpen = manualOpenUid === item.conflict_uid ? null : item.conflict_uid
                          setManualOpenUid(nextOpen)
                          if (nextOpen) setManualValues(previous => ({
                            ...previous,
                            [item.conflict_uid]: previous[item.conflict_uid] || { value: initialMergedValue(item), reason: '' },
                          }))
                        }}>融合合并</button>
                      </div>
                    </footer>
                  </>
                ) : (
                  <footer className="gov-conflict-resolution">
                    <span>处理结果：{item.decision === 'remote' ? '采用来源值' : ['manual', 'merge'].includes(item.decision || '') ? '融合合并' : item.decision === 'local' ? '保留本地值' : item.decision || '已处理'}</span>
                    <span>处理时间 {formatApiDateTime(item.decided_at)}</span>
                    {item.decision_reason && <span>原因：{item.decision_reason}</span>}
                  </footer>
                )}
              </article>
            )
          })}
        </div>
      )}

      <div className="gov-pagination">
        <button className="btn btn-secondary" disabled={offset === 0 || loading || busy} onClick={() => setOffset(Math.max(0, offset - pageSize))}>上一页</button>
        <span>第 {pageNumber} / {pageCount} 页</span>
        <button className="btn btn-secondary" disabled={offset + pageSize >= total || loading || busy} onClick={() => setOffset(offset + pageSize)}>下一页</button>
      </div>
    </section>
  )
}
