import { useCallback, useEffect, useMemo, useState } from 'react'
import { fieldApi, importApi } from '../../api'
import type { FieldMeta, GovernanceAction, GovernanceObservation } from '../../types'
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
  const [items, setItems] = useState<GovernanceObservation[]>([])
  const [fields, setFields] = useState<FieldMeta[]>([])
  const [sourceField, setSourceField] = useState('')
  const [batchId, setBatchId] = useState('')
  const [mappingBySource, setMappingBySource] = useState<Record<string, string>>({})
  const [batchScope, setBatchScope] = useState(true)
  const [adoptedValue, setAdoptedValue] = useState(false)
  const [loading, setLoading] = useState(true)
  const [busyKey, setBusyKey] = useState<string | null>(null)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')

  const loadItems = useCallback(async () => {
    setLoading(true)
    setError('')
    try {
      const result = await importApi.listUnmapped({
        source_field: sourceField.trim() || undefined,
        batch_id: batchId.trim() ? Number(batchId) : undefined,
        limit: 200,
      })
      setItems(result.items)
    } catch (requestError: unknown) {
      setError(getErrorMessage(requestError, '待治理属性加载失败'))
    } finally {
      setLoading(false)
    }
  }, [batchId, sourceField])

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
      await loadItems()
    } catch (requestError: unknown) {
      setError(getErrorMessage(requestError, '治理操作失败，原始数据未删除'))
    } finally {
      setBusyKey(null)
    }
  }, [batchScope, loadItems, mappingBySource])

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
        <input className="form-input" value={sourceField} onChange={event => setSourceField(event.target.value)} placeholder="按来源列筛选" style={{ width: 190 }} list="governance-source-fields" />
        <datalist id="governance-source-fields">
          {sourceFields.map(field => <option key={field} value={field} />)}
        </datalist>
        <input className="form-input" value={batchId} onChange={event => setBatchId(event.target.value.replace(/\D/g, ''))} placeholder="导入批次 ID" inputMode="numeric" style={{ width: 130 }} />
        <label style={{ display: 'inline-flex', alignItems: 'center', gap: 5, fontSize: 12, color: '#475569' }}>
          <input type="checkbox" checked={batchScope} onChange={event => setBatchScope(event.target.checked)} />
          按同批次同来源列处理
        </label>
        <label style={{ display: 'inline-flex', alignItems: 'center', gap: 5, fontSize: 12, color: '#475569' }}>
          <input type="checkbox" checked={adoptedValue} onChange={event => setAdoptedValue(event.target.checked)} />
          映射时采用来源值覆盖已有值
        </label>
        <span style={{ marginLeft: 'auto', color: '#64748b', fontSize: 12 }}>待处理 {items.length} 条</span>
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
    </div>
  )
}
