import { useState, useEffect, useCallback } from 'react'
import { importApi, viewApi } from '../../api'
import { useAppStore } from '../../store'
import type { ImportBatch, PatentView } from '../../types'

const STATUS_LABELS: Record<string, string> = {
  pending: '待处理',
  processing: '处理中',
  completed: '已完成',
  failed: '失败',
  rolled_back: '已回滚',
}

const STATUS_COLORS: Record<string, string> = {
  pending: '#94a3b8',
  processing: '#0ea5e9',
  completed: '#16a34a',
  failed: '#dc2626',
  rolled_back: '#6b7280',
}

export default function ImportHistoryPage() {
  const { currentDatabaseId, databases } = useAppStore()
  const [batches, setBatches] = useState<ImportBatch[]>([])
  const [total, setTotal] = useState(0)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  // 筛选条件：默认按当前库
  const [filterDbId, setFilterDbId] = useState<number | ''>('')
  const [filterStatus, setFilterStatus] = useState<string>('')
  // 详情抽屉
  const [selectedBatch, setSelectedBatch] = useState<(ImportBatch & { errors?: any[] }) | null>(null)
  const [detailLoading, setDetailLoading] = useState(false)
  // 视图名缓存（view_id -> 视图名）
  const [viewNameMap, setViewNameMap] = useState<Record<number, string>>({})

  useEffect(() => {
    setFilterDbId(currentDatabaseId ?? '')
  }, [currentDatabaseId])

  const loadBatches = useCallback(async () => {
    setLoading(true)
    setError('')
    try {
      const params: Record<string, any> = { limit: 200 }
      if (filterDbId !== '') params.database_id = filterDbId
      if (filterStatus) params.status = filterStatus
      const resp = await importApi.listBatches(params)
      setBatches(resp.items || [])
      setTotal(resp.total || 0)
      // 预取涉及到的视图名
      const viewIds = Array.from(new Set(
        (resp.items || []).map(b => b.view_id).filter((v): v is number => v != null)
      ))
      if (viewIds.length > 0) {
        const map: Record<number, string> = { ...viewNameMap }
        await Promise.all(viewIds.map(async vid => {
          if (map[vid]) return
          try {
            const v: PatentView = await viewApi.get(vid)
            if (v?.name) map[vid] = v.name
          } catch {
            // 视图可能已删除
          }
        }))
        setViewNameMap(map)
      }
    } catch (e: any) {
      setError(e?.response?.data?.detail || '加载导入历史失败')
    } finally {
      setLoading(false)
    }
  }, [filterDbId, filterStatus])

  useEffect(() => {
    loadBatches()
  }, [loadBatches])

  const openDetail = async (b: ImportBatch) => {
    setSelectedBatch(b)
    setDetailLoading(true)
    try {
      const detail = await importApi.getBatch(b.id)
      setSelectedBatch(detail)
    } catch (e) {
      // 详情加载失败时退回使用列表数据
    } finally {
      setDetailLoading(false)
    }
  }

  const formatTime = (iso?: string) => {
    if (!iso) return '-'
    try {
      return new Date(iso).toLocaleString('zh-CN', { hour12: false })
    } catch {
      return iso
    }
  }

  const formatDuration = (start?: string, end?: string) => {
    if (!start || !end) return '-'
    const ms = new Date(end).getTime() - new Date(start).getTime()
    if (isNaN(ms) || ms < 0) return '-'
    if (ms < 1000) return `${ms} ms`
    if (ms < 60000) return `${(ms / 1000).toFixed(1)} 秒`
    return `${Math.floor(ms / 60000)} 分 ${Math.floor((ms % 60000) / 1000)} 秒`
  }

  return (
    <div>
      <div className="page-header" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', flexWrap: 'wrap', gap: 12 }}>
        <div>
          <h2 className="page-title">导入历史</h2>
          <p className="page-subtitle">查看历次导入批次的状态与统计 · 共 {total} 条</p>
        </div>
        <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
          <select
            className="form-input"
            value={filterDbId}
            onChange={(e) => setFilterDbId(e.target.value === '' ? '' : Number(e.target.value))}
            style={{ height: 32, fontSize: 13, minWidth: 140 }}
          >
            <option value="">全部库</option>
            {databases.map(d => <option key={d.id} value={d.id}>{d.name}</option>)}
          </select>
          <select
            className="form-input"
            value={filterStatus}
            onChange={(e) => setFilterStatus(e.target.value)}
            style={{ height: 32, fontSize: 13, minWidth: 120 }}
          >
            <option value="">全部状态</option>
            {Object.entries(STATUS_LABELS).map(([k, v]) => (
              <option key={k} value={k}>{v}</option>
            ))}
          </select>
          <button className="btn btn-sm btn-secondary" onClick={loadBatches}>刷新</button>
        </div>
      </div>

      {error && (
        <div style={{ background: '#fef2f2', border: '1px solid #fecaca', color: '#dc2626', padding: 12, borderRadius: 6, marginBottom: 16, fontSize: 13 }}>
          {error}
        </div>
      )}

      {loading ? (
        <div className="loading-spinner"><div className="spinner"></div>加载中...</div>
      ) : batches.length === 0 ? (
        <div className="empty-state"><p>暂无导入历史</p></div>
      ) : (
        <div className="table-container">
          <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13 }}>
            <thead>
              <tr style={{ background: '#f8fafc', textAlign: 'left' }}>
                <th style={th}>批次 ID</th>
                <th style={th}>文件名</th>
                <th style={th}>状态</th>
                <th style={th}>库</th>
                <th style={th}>视图</th>
                <th style={th}>总行数</th>
                <th style={th}>新增</th>
                <th style={th}>更新</th>
                <th style={th}>跳过</th>
                <th style={th}>重复</th>
                <th style={th}>错误</th>
                <th style={th}>本地字段</th>
                <th style={th}>去重</th>
                <th style={th}>开始时间</th>
                <th style={th}>耗时</th>
                <th style={th}>操作</th>
              </tr>
            </thead>
            <tbody>
              {batches.map(b => {
                const dbName = databases.find(d => d.id === b.database_id)?.name || (b.database_id == null ? '全部' : `#${b.database_id}`)
                const vName = b.view_id != null ? (viewNameMap[b.view_id] || `#${b.view_id}`) : '-'
                return (
                  <tr key={b.id} style={{ borderBottom: '1px solid #f1f5f9' }}>
                    <td style={td}>#{b.id}</td>
                    <td style={{ ...td, maxWidth: 200, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }} title={b.filename}>{b.filename}</td>
                    <td style={td}>
                      <span style={{
                        padding: '2px 8px', borderRadius: 10, fontSize: 11, fontWeight: 500,
                        background: (STATUS_COLORS[b.status] || '#94a3b8') + '22',
                        color: STATUS_COLORS[b.status] || '#94a3b8',
                      }}>{STATUS_LABELS[b.status] || b.status}</span>
                    </td>
                    <td style={td}>{dbName}</td>
                    <td style={td}>{vName}</td>
                    <td style={td}>{b.total_rows}</td>
                    <td style={{ ...td, color: '#16a34a', fontWeight: 500 }}>{b.inserted_count}</td>
                    <td style={{ ...td, color: '#0ea5e9' }}>{b.updated_count}</td>
                    <td style={td}>{b.skipped_count}</td>
                    <td style={td}>{b.duplicate_count}</td>
                    <td style={{ ...td, color: b.error_count > 0 ? '#dc2626' : '#94a3b8' }}>{b.error_count}</td>
                    <td style={td}>{b.view_local_written || 0}</td>
                    <td style={td}>{b.dedupe_by || '-'}</td>
                    <td style={td}>{formatTime(b.started_at || b.created_at)}</td>
                    <td style={td}>{formatDuration(b.started_at, b.completed_at)}</td>
                    <td style={td}>
                      <button
                        onClick={() => openDetail(b)}
                        style={{
                          background: 'transparent', border: '1px solid #cbd5e1', borderRadius: 4,
                          padding: '2px 8px', fontSize: 12, cursor: 'pointer', color: '#475569',
                        }}
                      >详情</button>
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      )}

      {/* 详情抽屉 */}
      {selectedBatch && (
        <div
          onClick={(e) => { if (e.target === e.currentTarget) setSelectedBatch(null) }}
          style={{
            position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.4)',
            display: 'flex', justifyContent: 'flex-end', zIndex: 100,
          }}
        >
          <div style={{
            background: 'white', width: '480px', maxWidth: '90vw', height: '100vh',
            overflow: 'auto', boxShadow: '-8px 0 24px rgba(0,0,0,0.1)',
            display: 'flex', flexDirection: 'column',
          }}>
            <div style={{ padding: '16px 20px', borderBottom: '1px solid #e2e8f0', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <h3 style={{ margin: 0, fontSize: 16, fontWeight: 600 }}>批次 #{selectedBatch.id} 详情</h3>
              <button onClick={() => setSelectedBatch(null)} style={{ background: 'none', border: 'none', fontSize: 20, cursor: 'pointer', color: '#94a3b8' }}>×</button>
            </div>
            <div style={{ padding: 20, flex: 1 }}>
              {detailLoading ? (
                <div style={{ textAlign: 'center', padding: 20, color: '#94a3b8' }}>加载详情中...</div>
              ) : (
                <>
                  <DetailRow label="文件名" value={selectedBatch.filename} />
                  <DetailRow label="状态" value={STATUS_LABELS[selectedBatch.status] || selectedBatch.status} />
                  <DetailRow label="库" value={databases.find(d => d.id === selectedBatch.database_id)?.name || (selectedBatch.database_id == null ? '全部' : `#${selectedBatch.database_id}`)} />
                  <DetailRow label="视图" value={selectedBatch.view_id != null ? (viewNameMap[selectedBatch.view_id] || `#${selectedBatch.view_id}`) : '-'} />
                  <DetailRow label="总行数" value={String(selectedBatch.total_rows)} />
                  <DetailRow label="已处理" value={String(selectedBatch.processed_rows)} />
                  <DetailRow label="新增" value={String(selectedBatch.inserted_count)} />
                  <DetailRow label="更新" value={String(selectedBatch.updated_count)} />
                  <DetailRow label="跳过" value={String(selectedBatch.skipped_count)} />
                  <DetailRow label="重复" value={String(selectedBatch.duplicate_count)} />
                  <DetailRow label="错误" value={String(selectedBatch.error_count)} />
                  <DetailRow label="视图本地字段写入" value={String(selectedBatch.view_local_written || 0)} />
                  <DetailRow label="去重策略" value={selectedBatch.dedupe_by || '-'} />
                  <DetailRow label="开始时间" value={formatTime(selectedBatch.started_at)} />
                  <DetailRow label="完成时间" value={formatTime(selectedBatch.completed_at)} />
                  <DetailRow label="耗时" value={formatDuration(selectedBatch.started_at, selectedBatch.completed_at)} />
                  <DetailRow label="创建时间" value={formatTime(selectedBatch.created_at)} />

                  {selectedBatch.errors && selectedBatch.errors.length > 0 && (
                    <div style={{ marginTop: 16 }}>
                      <div style={{ fontSize: 12, color: '#64748b', marginBottom: 6, fontWeight: 500 }}>错误明细（最多 50 条）</div>
                      <div style={{
                        background: '#fef2f2', border: '1px solid #fecaca', borderRadius: 6,
                        padding: 10, maxHeight: 300, overflow: 'auto', fontSize: 12,
                      }}>
                        {selectedBatch.errors.map((e: any, i: number) => (
                          <div key={i} style={{ padding: '4px 0', borderBottom: i < selectedBatch.errors!.length - 1 ? '1px dashed #fecaca' : 'none' }}>
                            {e.row != null && <span style={{ color: '#dc2626', fontWeight: 500, marginRight: 8 }}>第 {e.row} 行:</span>}
                            <span style={{ color: '#7c2d12' }}>{e.error || JSON.stringify(e)}</span>
                          </div>
                        ))}
                      </div>
                    </div>
                  )}
                </>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

const th: React.CSSProperties = {
  padding: '10px 12px', fontSize: 12, color: '#475569', fontWeight: 600, borderBottom: '2px solid #e2e8f0', whiteSpace: 'nowrap',
}

const td: React.CSSProperties = {
  padding: '8px 12px', fontSize: 12, color: '#1f2937', whiteSpace: 'nowrap',
}

function DetailRow({ label, value }: { label: string; value: string }) {
  return (
    <div style={{ display: 'flex', padding: '6px 0', borderBottom: '1px solid #f1f5f9', fontSize: 13 }}>
      <span style={{ width: 140, color: '#64748b', flexShrink: 0 }}>{label}</span>
      <span style={{ flex: 1, color: '#1f2937', wordBreak: 'break-all' }}>{value}</span>
    </div>
  )
}
