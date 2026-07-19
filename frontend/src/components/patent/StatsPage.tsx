import { useState, useEffect } from 'react'
import { statsApi } from '../../api'
import type { Stats } from '../../types'

export default function StatsPage() {
  const [stats, setStats] = useState<Stats | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    loadStats()
  }, [])

  const loadStats = async () => {
    try {
      const data = await statsApi.get()
      setStats(data)
    } catch (e) {
      console.error('Failed to load stats:', e)
    } finally {
      setLoading(false)
    }
  }

  if (loading) {
    return (
      <div className="loading-spinner">
        <div className="spinner"></div>
        加载统计数据中...
      </div>
    )
  }

  if (!stats) {
    return <div className="empty-state"><p>加载统计数据失败</p></div>
  }

  const statusMap: Record<string, string> = {
    granted: '授权', examining: '实审中', published: '公开',
    rejected: '驳回', withdrawn: '撤回', deemed_withdrawn: '视撤',
    expired: '终止', abandoned: '放弃', pending: '待审', unknown: '未知',
  }

  const riskMap: Record<string, string> = {
    none: '无风险', low: '低风险', medium: '中风险', high: '高风险', critical: '极高风险',
  }

  return (
    <div>
      <div className="page-header">
        <h2 className="page-title">数据看板</h2>
        <p className="page-subtitle">专利数据概览</p>
      </div>

      <div className="stats-cards">
        <div className="stat-card">
          <div className="stat-value">{stats.total_patents}</div>
          <div className="stat-label">专利总数</div>
        </div>
        <div className="stat-card">
          <div className="stat-value" style={{ color: '#16a34a' }}>
            {stats.by_legal_status.granted || 0}
          </div>
          <div className="stat-label">已授权</div>
        </div>
        <div className="stat-card">
          <div className="stat-value" style={{ color: '#ca8a04' }}>
            {stats.by_legal_status.examining || 0}
          </div>
          <div className="stat-label">实审中</div>
        </div>
        <div className="stat-card">
          <div className="stat-value" style={{ color: '#dc2626' }}>
            {Object.entries(stats.by_risk_level)
              .filter(([k]) => k === 'high' || k === 'critical')
              .reduce((sum, [, v]) => sum + v, 0)}
          </div>
          <div className="stat-label">高风险专利</div>
        </div>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 20, marginBottom: 20 }}>
        <div className="table-container">
          <div style={{ padding: '12px 16px', borderBottom: '1px solid #e2e8f0', fontWeight: 600 }}>
            按法律状态分布
          </div>
          <div style={{ padding: 16 }}>
            {Object.entries(stats.by_legal_status).map(([status, count]) => (
              <div key={status} style={{ display: 'flex', alignItems: 'center', marginBottom: 8 }}>
                <span style={{ width: 100, fontSize: 13, color: '#475569' }}>
                  {statusMap[status] || status}
                </span>
                <div style={{ flex: 1, height: 20, background: '#f1f5f9', borderRadius: 4, margin: '0 12px', overflow: 'hidden' }}>
                  <div
                    style={{
                      height: '100%',
                      width: `${stats.total_patents ? (count / stats.total_patents * 100) : 0}%`,
                      background: status === 'granted' ? '#16a34a' :
                                 status === 'examining' ? '#ca8a04' :
                                 status === 'rejected' ? '#dc2626' : '#64748b',
                      borderRadius: 4,
                    }}
                  />
                </div>
                <span style={{ width: 50, textAlign: 'right', fontSize: 13, fontWeight: 500 }}>{count}</span>
              </div>
            ))}
          </div>
        </div>

        <div className="table-container">
          <div style={{ padding: '12px 16px', borderBottom: '1px solid #e2e8f0', fontWeight: 600 }}>
            按风险等级分布
          </div>
          <div style={{ padding: 16 }}>
            {Object.entries(stats.by_risk_level).map(([level, count]) => (
              <div key={level} style={{ display: 'flex', alignItems: 'center', marginBottom: 8 }}>
                <span style={{ width: 100, fontSize: 13, color: '#475569' }}>
                  {riskMap[level] || level}
                </span>
                <div style={{ flex: 1, height: 20, background: '#f1f5f9', borderRadius: 4, margin: '0 12px', overflow: 'hidden' }}>
                  <div
                    style={{
                      height: '100%',
                      width: `${stats.total_patents ? (count / stats.total_patents * 100) : 0}%`,
                      background: level === 'high' || level === 'critical' ? '#dc2626' :
                                 level === 'medium' ? '#ca8a04' :
                                 level === 'low' ? '#2563eb' : '#94a3b8',
                      borderRadius: 4,
                    }}
                  />
                </div>
                <span style={{ width: 50, textAlign: 'right', fontSize: 13, fontWeight: 500 }}>{count}</span>
              </div>
            ))}
          </div>
        </div>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 20 }}>
        <div className="table-container">
          <div style={{ padding: '12px 16px', borderBottom: '1px solid #e2e8f0', fontWeight: 600 }}>
            Top 10 申请人
          </div>
          <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13 }}>
            <tbody>
              {stats.top_applicants.slice(0, 10).map((a, i) => (
                <tr key={i} style={{ borderBottom: '1px solid #f1f5f9' }}>
                  <td style={{ padding: '8px 16px', width: 30, color: '#94a3b8' }}>{i + 1}</td>
                  <td style={{ padding: '8px 0' }}>{a.name}</td>
                  <td style={{ padding: '8px 16px', textAlign: 'right', fontWeight: 500 }}>{a.count}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        <div className="table-container">
          <div style={{ padding: '12px 16px', borderBottom: '1px solid #e2e8f0', fontWeight: 600 }}>
            Top 10 发明人
          </div>
          <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13 }}>
            <tbody>
              {stats.top_inventors.slice(0, 10).map((inv, i) => (
                <tr key={i} style={{ borderBottom: '1px solid #f1f5f9' }}>
                  <td style={{ padding: '8px 16px', width: 30, color: '#94a3b8' }}>{i + 1}</td>
                  <td style={{ padding: '8px 0' }}>{inv.name}</td>
                  <td style={{ padding: '8px 16px', textAlign: 'right', fontWeight: 500 }}>{inv.count}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  )
}
