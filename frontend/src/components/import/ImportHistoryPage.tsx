import { Fragment, useCallback, useEffect, useState } from 'react'
import { useLocation, useNavigate, useParams } from 'react-router-dom'
import { importApi } from '../../api'
import type { ImportBatch, ImportChangeReview, ImportReviewAction } from '../../types'
import { getErrorMessage } from '../../lib/errors'
import { formatApiDateTime } from '../../lib/date'
import { useAppStore } from '../../store'
import Icon from '../common/Icon'
import ImportModal from './ImportModal'

const STATUS_LABELS: Record<string, string> = {
  pending: '等待中',
  processing: '处理中',
  review_required: '待审查',
  completed: '已完成',
  failed: '失败',
  rolled_back: '已回滚',
}

function formatDate(value?: string) {
  return formatApiDateTime(value)
}

function formatCount(value: number | undefined) {
  return value ?? 0
}

function isCollaborationSyncBatch(batch: ImportBatch) {
  return batch.review_config?.batch_kind === 'collaboration_sync'
}

export default function ImportHistoryPage() {
  const navigate = useNavigate()
  const location = useLocation()
  const { databaseId } = useParams<{ databaseId: string }>()
  const { currentDatabaseId, databases } = useAppStore()
  const [batches, setBatches] = useState<ImportBatch[]>([])
  const [statusFilter, setStatusFilter] = useState('')
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [expandedBatchIds, setExpandedBatchIds] = useState<Set<number>>(new Set())
  const [batchRecords, setBatchRecords] = useState<Record<number, Awaited<ReturnType<typeof importApi.records>>>>({})
  const [recordsLoading, setRecordsLoading] = useState<number | null>(null)
  const [reviewBatchId, setReviewBatchId] = useState<number | null>(null)
  const [reviewChanges, setReviewChanges] = useState<ImportChangeReview[]>([])
  const [reviewTotal, setReviewTotal] = useState(0)
  const [reviewActions, setReviewActions] = useState<Record<number, ImportReviewAction>>({})
  const [reviewBusy, setReviewBusy] = useState(false)
  const [recordScope, setRecordScope] = useState('all')
  const [onlyConflicts, setOnlyConflicts] = useState(false)
  const [resumeId, setResumeId] = useState<string | null>(null)
  const isMaster = databases.find(database => database.id === currentDatabaseId)?.is_default
  const isSynchronized = (batch: ImportBatch) => isCollaborationSyncBatch(batch) || (isMaster && Number(batch.review_config?.database_id) !== currentDatabaseId)
  const visibleBatches = batches.filter(batch => recordScope === 'all' || (recordScope === 'sync' ? isSynchronized(batch) : !isSynchronized(batch)))

  const summary = batches.reduce((result, batch) => ({
    batches: result.batches + 1,
    completed: result.completed + (batch.status.toLowerCase() === 'completed' ? 1 : 0),
    failed: result.failed + (batch.status.toLowerCase() === 'failed' ? 1 : 0),
    rows: result.rows + formatCount(batch.total_rows),
    errors: result.errors + formatCount(batch.error_count),
  }), { batches: 0, completed: 0, failed: 0, rows: 0, errors: 0 })

  const loadBatches = useCallback(async () => {
    setLoading(true)
    setError('')
    try {
      const result = await importApi.listBatches({
        status: statusFilter || undefined,
        database_id: currentDatabaseId ?? undefined,
        limit: 100,
      })
      setBatches(result)
    } catch (requestError: unknown) {
      setError(getErrorMessage(requestError, '导入历史加载失败'))
    } finally {
      setLoading(false)
    }
  }, [currentDatabaseId, statusFilter])

  const currentDatabaseName = databases.find(database => database.id === currentDatabaseId)?.name

  const toggleBatch = (batchId: number) => {
    if (!expandedBatchIds.has(batchId)) void loadRecords(batchId)
    setExpandedBatchIds(current => {
      const next = new Set(current)
      if (next.has(batchId)) next.delete(batchId)
      else next.add(batchId)
      return next
    })
  }

  const loadRecords = async (batchId: number, offset = 0) => {
    setRecordsLoading(batchId)
    try {
      const result = await importApi.records(batchId, offset)
      setBatchRecords(current => ({ ...current, [batchId]: { ...result, items: offset ? [...(current[batchId]?.items || []), ...result.items] : result.items } }))
    } catch (cause) { setError(getErrorMessage(cause, '专利清单加载失败')) }
    finally { setRecordsLoading(null) }
  }

  const openReview = async (batchId: number) => {
    setReviewBusy(true)
    setError('')
    try {
      const result = await importApi.getChanges(batchId, false, 0, 2000, onlyConflicts)
      setReviewChanges(result.items)
      setReviewTotal(result.total)
      setReviewActions(Object.fromEntries(result.items.map(item => [item.id, item.review_action])))
      setReviewBatchId(batchId)
      setExpandedBatchIds(current => new Set(current).add(batchId))
    } catch (cause) {
      setError(getErrorMessage(cause, '导入审查加载失败'))
    } finally {
      setReviewBusy(false)
    }
  }

  const applyReviewed = async (batchId: number) => {
    setReviewBusy(true)
    setError('')
    try {
      await importApi.reviewBatch(batchId, {
        items: Object.entries(reviewActions).map(([id, action]) => ({ observation_id: Number(id), action })),
      })
      await importApi.applyBatch(batchId)
      setReviewBatchId(null)
      await loadBatches()
    } catch (cause) {
      setError(getErrorMessage(cause, '执行导入失败，批次仍可继续审查'))
    } finally {
      setReviewBusy(false)
    }
  }

  const rollback = async (batchId: number) => {
    if (!window.confirm('确认撤回这次导入？系统会删除本批新建记录，并恢复本批修改前的字段值。')) return
    setReviewBusy(true)
    try { await importApi.rollbackBatch(batchId); await loadBatches() }
    catch (cause) { setError(getErrorMessage(cause, '导入撤回失败')) }
    finally { setReviewBusy(false) }
  }

  useEffect(() => {
    // Import history is synchronized with the selected status through an API request.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    void loadBatches()
  }, [loadBatches])

  return (
    <div className="workspace-page import-history-page">
      <div className="workspace-page-shell import-history-shell">
      <div className="page-header workspace-page-header">
        <div>
          <h2 className="page-title">导入历史</h2>
          <p className="page-subtitle">{currentDatabaseName ? `当前库：${currentDatabaseName} · ` : ''}查看文件导入与库间同步的处理结果</p>
        </div>
        <div className="workspace-page-actions">
          <button className="btn btn-secondary" onClick={() => navigate(databaseId ? `/db/${databaseId}/patents${location.search}` : `/patents${location.search}`)}>返回数据表</button>
          <select className="form-input" value={statusFilter} onChange={event => setStatusFilter(event.target.value)}>
            <option value="">全部状态</option>
            {Object.entries(STATUS_LABELS).map(([value, label]) => <option key={value} value={value}>{label}</option>)}
          </select>
          <select aria-label="记录来源" className="form-input" value={recordScope} onChange={event => setRecordScope(event.target.value)}><option value="all">全部记录</option><option value="import">本库导入</option><option value="sync">同步记录</option></select>
          <button className="btn btn-secondary" onClick={() => void loadBatches()} disabled={loading}>刷新</button>
        </div>
      </div>

      <div className="import-summary-strip">
        <div><span>批次</span><strong>{summary.batches}</strong></div>
        <div><span>成功</span><strong className="is-positive">{summary.completed}</strong></div>
        <div><span>失败</span><strong className="is-negative">{summary.failed}</strong></div>
        <div><span>处理行数</span><strong>{summary.rows}</strong></div>
        <div><span>问题行数</span><strong className={summary.errors > 0 ? 'is-negative' : ''}>{summary.errors}</strong></div>
      </div>

      {error && (
        <div className="workspace-error">
          {error}
        </div>
      )}

      <div className="import-history-table-wrap">
        {loading ? (
          <div className="loading-state" style={{ minHeight: 180 }}>加载中...</div>
        ) : visibleBatches.length === 0 ? (
          <div className="empty-state" style={{ minHeight: 180 }}>暂无导入记录</div>
        ) : (
          <table className="data-grid import-history-table">
            <thead>
              <tr>
                <th className="import-history-expand-col" aria-label="展开详情"></th>
                <th>来源</th>
                <th>状态</th>
                <th>总行数</th>
                <th>新增</th>
                <th>更新</th>
                <th>未变更</th>
                <th>错误</th>
                <th>开始时间</th>
                <th>完成时间</th>
              </tr>
            </thead>
            <tbody>
              {visibleBatches.map(batch => {
                 const statusKey = batch.status.toLowerCase()
                 const isSyncBatch = isCollaborationSyncBatch(batch)
                 const expanded = expandedBatchIds.has(batch.id)
                 return (
                   <Fragment key={batch.id}>
                   <tr className={expanded ? 'is-expanded' : undefined}>
                     <td className="import-history-expand-col">
                       <button
                         type="button"
                         className="import-history-expand-button"
                         onClick={() => toggleBatch(batch.id)}
                         aria-label={expanded ? '收起批次详情' : '展开批次详情'}
                         title={expanded ? '收起批次详情' : '展开批次详情'}
                       >
                         <Icon name={expanded ? 'chevron-up' : 'chevron-down'} size={14} />
                       </button>
                     </td>
                     <td className="import-file-cell" title={batch.filename}>
                      <strong>{batch.filename}</strong>
                      <span>{batch.source_table_title || '未命名来源表'}{batch.worksheet_name ? ` · ${batch.worksheet_name}` : ''}</span>
                      <span>{isSynchronized(batch) ? '同步来源：' : '来源库：'}{String(databases.find(database => database.id === Number(batch.review_config?.database_id))?.name || batch.review_config?.target_database_name || '历史记录')}</span>
                    </td>
                    <td>
                      <span className={`status-badge status-${statusKey}`}>
                        {isSyncBatch && statusKey === 'review_required' ? '有待处理冲突' : STATUS_LABELS[statusKey] || batch.status}
                      </span>
                    </td>
                    <td>{formatCount(batch.total_rows)}</td>
                    <td className="count-positive">{formatCount(batch.inserted_count)}</td>
                    <td className="count-info">{formatCount(batch.updated_count)}</td>
                    <td>{formatCount(batch.skipped_count)}</td>
                    <td className={batch.error_count > 0 ? 'count-negative' : ''}>{formatCount(batch.error_count)}</td>
                    <td>{formatDate(batch.started_at)}</td>
                     <td>{formatDate(batch.completed_at)}</td>
                   </tr>
                   {expanded && (
                     <tr className="import-history-detail-row">
                       <td colSpan={10}>
                         <div className="import-history-detail">
                           <div className="import-history-detail-heading">
                             <strong>批次详情</strong>
                             <span>批次 #{batch.id}</span>
                           </div>
                           <div className="import-history-detail-grid">
                             <div><span>来源表标题</span><strong>{batch.source_table_title || '未记录'}</strong></div>
                             {!isSyncBatch && <div><span>工作表</span><strong>{batch.worksheet_name || '默认工作表'}</strong></div>}
                             <div><span>来源系统</span><strong>{isSyncBatch ? '部门协同同步' : batch.source_system || '人工导入'}</strong></div>
                             <div><span>{isSyncBatch ? '同步信息' : '导入备注'}</span><strong>{batch.import_note || '未填写'}</strong></div>
                             {isSyncBatch && <>
                               <div><span>同步包 UID</span><strong>{String(batch.review_config?.package_uid || '未记录')}</strong></div>
                               <div><span>目标数据库</span><strong>{String(batch.review_config?.target_database_name || currentDatabaseName || '未记录')}</strong></div>
                               <div><span>待处理冲突</span><strong>{formatCount(Number(batch.review_config?.pending_conflicts ?? batch.error_count))}</strong></div>
                             </>}
                             <div><span>已处理行数</span><strong>{formatCount(batch.processed_rows)} / {formatCount(batch.total_rows)}</strong></div>
                             <div><span>字段更新</span><strong>{formatCount(batch.updated_count)} 条记录</strong></div>
                             <div><span>错误明细</span><strong>{formatCount(batch.error_count)} 条</strong></div>
                             <div><span>文件指纹</span><strong>{batch.file_hash ? batch.file_hash.slice(0, 12) : '未记录'}</strong></div>
                             <div><span>回撤状态</span><strong>{isSyncBatch ? '由同步冲突和审计记录追踪' : statusKey === 'rolled_back' ? '已回撤' : '可在导入结果中回撤'}</strong></div>
                           </div>
                           <strong>涉及专利（{batchRecords[batch.id]?.total ?? '-'} 条）</strong>
                           <div style={{ maxHeight: 320, overflow: 'auto', marginTop: 8, marginBottom: 14 }}>
                             <table className="data-grid"><thead><tr><th>来源行</th><th>公开号 / 授权号</th><th>申请号</th><th>名称</th><th>处理结果</th></tr></thead>
                               <tbody>{batchRecords[batch.id]?.items.map((item, index) => <tr key={`${item.source_row}-${index}`}>
                                 <td>{item.source_row ?? '-'}</td>
                                 <td>{item.patent_id ? <a href={`${databaseId ? `/db/${databaseId}` : ''}/patents/${item.patent_id}?publication=${encodeURIComponent(item.publication_number || '')}`}>{item.publication_number || `Wiki #${item.patent_id}`}</a> : item.publication_number || '-'}</td>
                                 <td>{item.application_number || '-'}</td><td>{item.title || '-'}</td><td title={item.reason}>{item.status}</td>
                               </tr>)}</tbody>
                             </table>
                             {recordsLoading === batch.id && <div>加载中...</div>}
                             {batchRecords[batch.id]?.total === 0 && <div>此批次没有可追溯的专利记录。</div>}
                             {batchRecords[batch.id] && batchRecords[batch.id].items.length < batchRecords[batch.id].total && <button className="btn btn-secondary" disabled={recordsLoading === batch.id} onClick={() => void loadRecords(batch.id, batchRecords[batch.id].items.length)}>加载更多</button>}
                           </div>
                           {isSyncBatch && statusKey === 'review_required' && <div style={{ marginTop: 12, padding: '9px 11px', borderLeft: '3px solid #d97706', background: '#fffbeb', color: '#78350f', fontSize: 12 }}>
                             仍有字段冲突待处理，请到“设置 → 部门协同与数据同步”查看同步包并完成决策。
                           </div>}
                           <div style={{ display: 'flex', gap: 8, marginTop: 12, flexWrap: 'wrap' }}>
                             {!isSyncBatch && statusKey === 'review_required' && <button className="btn btn-primary" disabled={reviewBusy} onClick={() => void openReview(batch.id)}>继续审查并执行</button>}
                             {!isSyncBatch && statusKey === 'review_required' && Number(batch.review_config?.database_id) === currentDatabaseId && <button className="btn btn-secondary" disabled={reviewBusy} onClick={() => {
                               setReviewBusy(true)
                               void importApi.resumeBatch(batch.id).then(result => setResumeId(result.import_id)).catch(error => setError(getErrorMessage(error))).finally(() => setReviewBusy(false))
                             }}>返回字段映射</button>}
                             {statusKey === 'completed' && <button className="btn btn-secondary" onClick={() => navigate(databaseId ? `/db/${databaseId}/patents` : `/db/${currentDatabaseId}/patents`)}>查看目标数据库</button>}
                             {!isSyncBatch && statusKey === 'completed' && <button className="btn btn-danger" disabled={reviewBusy} onClick={() => void rollback(batch.id)}>撤回本次导入</button>}
                             {!isSyncBatch && <button className="btn btn-secondary" onClick={() => navigate(`${databaseId ? `/db/${databaseId}` : currentDatabaseId ? `/db/${currentDatabaseId}` : ''}/governance?batch_id=${batch.id}`)}>查看本批待治理数据</button>}
                           </div>
                           {reviewBatchId === batch.id && <div style={{ marginTop: 14 }}>
                             <strong>字段审查 · {reviewChanges.length} / {reviewTotal} 个来源值</strong>
                             <label style={{ marginLeft: 12 }}><input type="checkbox" checked={onlyConflicts} disabled={reviewBusy} onChange={event => {
                               const checked = event.target.checked
                               setReviewBusy(true)
                               void importApi.reviewBatch(batch.id, { items: Object.entries(reviewActions).map(([id, action]) => ({ observation_id: Number(id), action })) }).then(() => importApi.getChanges(batch.id, false, 0, 2000, checked)).then(result => { setOnlyConflicts(checked); setReviewChanges(result.items); setReviewTotal(result.total); setReviewActions(Object.fromEntries(result.items.map(item => [item.id, item.review_action]))) }).catch(error => setError(getErrorMessage(error))).finally(() => setReviewBusy(false))
                             }} />仅新旧值冲突</label>
                             {reviewTotal > reviewChanges.length && <div style={{ color: '#64748b', fontSize: 12, marginTop: 4 }}>当前显示前 {reviewChanges.length} 项，其余项目将按系统建议处理。</div>}
                             <div style={{ maxHeight: 360, overflow: 'auto', marginTop: 8 }}>
                               <table className="data-grid"><thead><tr><th>行</th><th>来源字段</th><th>当前值</th><th>导入值</th><th>处理</th></tr></thead>
                                 <tbody>{reviewChanges.map(item => <tr key={item.id}>
                                   <td>{item.source_row}</td><td>{item.source_field_name}</td>
                                   <td>{item.current_value || '-'}</td><td>{item.candidate_value || item.raw_value || '-'}</td>
                                   <td><select className="form-input" value={reviewActions[item.id] || item.review_action} onChange={event => setReviewActions(current => ({ ...current, [item.id]: event.target.value as ImportReviewAction }))}>
                                     <option value="keep_existing">保留现有值</option>
                                     {item.field_resolution === 'mapped' && <option value="adopt">采用导入值</option>}
                                     {item.field_resolution === 'mapped' && <option value="fill_empty">仅填充空值</option>}
                                     <option value="ignore">忽略本单元格</option><option value="quarantine">隔离待处理</option>
                                   </select></td>
                                 </tr>)}</tbody>
                               </table>
                             </div>
                             <button className="btn btn-primary" style={{ marginTop: 10 }} disabled={reviewBusy} onClick={() => void applyReviewed(batch.id)}>确认并执行导入</button>
                           </div>}
                           {batch.errors && batch.errors.length > 0 && (
                             <div className="import-history-detail-errors">
                               <strong>{isSyncBatch ? '同步冲突' : '错误与字段提醒'}</strong>
                               <ul>
                                 {batch.errors.map((issue, index) => (
                                   <li key={index}>
                                     {typeof issue.row === 'number' ? `第 ${issue.row} 行` : '批次'}
                                     {typeof issue.field === 'string' ? ` · ${issue.field}` : ''}
                                     {'：'}{String(issue.reason || issue.error || '未记录具体原因')}
                                   </li>
                                 ))}
                               </ul>
                             </div>
                           )}
                         </div>
                       </td>
                     </tr>
                   )}
                   </Fragment>
                 )
              })}
            </tbody>
          </table>
        )}
      </div>
      </div>
      {resumeId && <ImportModal initialDraftId={resumeId} onClose={() => { setResumeId(null); void loadBatches() }} onSuccess={() => { setResumeId(null); void loadBatches() }} />}
    </div>
  )
}
