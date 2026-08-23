import { useCallback, useEffect, useState } from 'react'
import { importApi } from '../../api'
import type { ImportBatch } from '../../types'
import { getErrorMessage } from '../../lib/errors'

const STATUS_LABELS: Record<string, string> = {
  pending: '等待中',
  processing: '处理中',
  completed: '已完成',
  failed: '失败',
  rolled_back: '已回滚',
}

function formatDate(value?: string) {
  if (!value) return '-'
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString('zh-CN')
}

function formatCount(value: number | undefined) {
  return value ?? 0
}

export default function ImportHistoryPage() {
  const [batches, setBatches] = useState<ImportBatch[]>([])
  const [statusFilter, setStatusFilter] = useState('')
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

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
        limit: 100,
      })
      setBatches(result)
    } catch (requestError: unknown) {
      setError(getErrorMessage(requestError, '导入历史加载失败'))
    } finally {
      setLoading(false)
    }
  }, [statusFilter])

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
          <p className="page-subtitle">查看每次导入的处理结果与失败行数</p>
        </div>
        <div className="workspace-page-actions">
          <select className="form-input" value={statusFilter} onChange={event => setStatusFilter(event.target.value)}>
            <option value="">全部状态</option>
            {Object.entries(STATUS_LABELS).map(([value, label]) => <option key={value} value={value}>{label}</option>)}
          </select>
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

      <div className="table-container import-history-table-wrap">
        {loading ? (
          <div className="loading-state" style={{ minHeight: 180 }}>加载中...</div>
        ) : batches.length === 0 ? (
          <div className="empty-state" style={{ minHeight: 180 }}>暂无导入记录</div>
        ) : (
          <table className="data-grid import-history-table">
            <thead>
              <tr>
                <th>文件</th>
                <th>状态</th>
                <th>总行数</th>
                <th>新增</th>
                <th>更新</th>
                <th>跳过</th>
                <th>错误</th>
                <th>开始时间</th>
                <th>完成时间</th>
              </tr>
            </thead>
            <tbody>
              {batches.map(batch => {
                const statusKey = batch.status.toLowerCase()
                return (
                  <tr key={batch.id}>
                    <td className="import-file-cell" title={batch.filename}>
                      <strong>{batch.filename}</strong>
                      <span>{batch.source_table_title || '未命名来源表'}{batch.worksheet_name ? ` · ${batch.worksheet_name}` : ''}</span>
                    </td>
                    <td>
                      <span className={`status-badge status-${statusKey}`}>
                        {STATUS_LABELS[statusKey] || batch.status}
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
                )
              })}
            </tbody>
          </table>
        )}
      </div>
      </div>
    </div>
  )
}
