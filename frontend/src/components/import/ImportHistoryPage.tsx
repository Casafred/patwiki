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

const STATUS_COLORS: Record<string, { background: string; color: string }> = {
  pending: { background: '#fef3c7', color: '#92400e' },
  processing: { background: '#dbeafe', color: '#1d4ed8' },
  completed: { background: '#dcfce7', color: '#166534' },
  failed: { background: '#fee2e2', color: '#b91c1c' },
  rolled_back: { background: '#f1f5f9', color: '#475569' },
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
    <div>
      <div className="page-header" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: 12, flexWrap: 'wrap' }}>
        <div>
          <h2 className="page-title">导入历史</h2>
          <p className="page-subtitle">查看每次导入的处理结果与失败行数</p>
        </div>
        <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
          <select className="form-input" value={statusFilter} onChange={event => setStatusFilter(event.target.value)} style={{ minWidth: 120, height: 32, fontSize: 13 }}>
            <option value="">全部状态</option>
            {Object.entries(STATUS_LABELS).map(([value, label]) => <option key={value} value={value}>{label}</option>)}
          </select>
          <button className="btn btn-secondary" onClick={() => void loadBatches()} disabled={loading}>刷新</button>
        </div>
      </div>

      {error && (
        <div style={{ marginBottom: 12, padding: '8px 12px', border: '1px solid #fecaca', background: '#fef2f2', color: '#b91c1c', borderRadius: 6, fontSize: 13 }}>
          {error}
        </div>
      )}

      <div className="table-container" style={{ overflowX: 'auto' }}>
        {loading ? (
          <div className="loading-state" style={{ minHeight: 180 }}>加载中...</div>
        ) : batches.length === 0 ? (
          <div className="empty-state" style={{ minHeight: 180 }}>暂无导入记录</div>
        ) : (
          <table className="data-grid" style={{ minWidth: 820 }}>
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
                const statusStyle = STATUS_COLORS[statusKey] || STATUS_COLORS.pending
                return (
                  <tr key={batch.id}>
                    <td style={{ maxWidth: 260, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }} title={batch.filename}>{batch.filename}</td>
                    <td>
                      <span style={{ display: 'inline-block', padding: '2px 7px', borderRadius: 4, background: statusStyle.background, color: statusStyle.color, fontSize: 12 }}>
                        {STATUS_LABELS[statusKey] || batch.status}
                      </span>
                    </td>
                    <td>{formatCount(batch.total_rows)}</td>
                    <td style={{ color: '#166534' }}>{formatCount(batch.inserted_count)}</td>
                    <td style={{ color: '#1d4ed8' }}>{formatCount(batch.updated_count)}</td>
                    <td>{formatCount(batch.skipped_count)}</td>
                    <td style={{ color: batch.error_count > 0 ? '#b91c1c' : '#475569' }}>{formatCount(batch.error_count)}</td>
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
  )
}
