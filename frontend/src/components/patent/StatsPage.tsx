import { useState, useEffect } from 'react'
import { statsApi } from '../../api'
import { useAppStore } from '../../store'
import type { Stats } from '../../types'

export default function StatsPage() {
  const { currentDatabaseId, currentProductId, databases, products } = useAppStore()
  const [stats, setStats] = useState<Stats | null>(null)
  const [loading, setLoading] = useState(true)
  const [filterDbId, setFilterDbId] = useState<number | ''>('')
  const [filterProdId, setFilterProdId] = useState<number | ''>('')

  useEffect(() => {
    // 初始化筛选条件为当前库/产品
    setFilterDbId(currentDatabaseId ?? '')
    setFilterProdId(currentProductId ?? '')
  }, [])  // 仅初始化一次

  const loadStats = async () => {
    setLoading(true)
    try {
      const params: Record<string, any> = {}
      if (filterDbId !== '') params.database_id = filterDbId
      if (filterProdId !== '') params.product_id = filterProdId
      const data = await statsApi.get(params)
      setStats(data)
    } catch (e) {
      console.error('Failed to load stats:', e)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    loadStats()
  }, [filterDbId, filterProdId])

  const statusMap: Record<string, string> = {
    granted: '授权', examining: '实审中', published: '公开',
    rejected: '驳回', withdrawn: '撤回', deemed_withdrawn: '视撤',
    expired: '终止', abandoned: '放弃', pending: '待审', unknown: '未知',
  }
  const statusColors: Record<string, string> = {
    granted: '#16a34a', examining: '#ca8a04', published: '#0ea5e9',
    rejected: '#dc2626', withdrawn: '#6b7280', deemed_withdrawn: '#9ca3af',
    expired: '#6b7280', abandoned: '#9ca3af', pending: '#f59e0b', unknown: '#94a3b8',
  }
  const riskMap: Record<string, string> = {
    none: '无风险', low: '低风险', medium: '中风险', high: '高风险', critical: '极高风险',
  }
  const riskColors: Record<string, string> = {
    none: '#94a3b8', low: '#3b82f6', medium: '#ca8a04', high: '#dc2626', critical: '#7c2d12',
  }
  const typeMap: Record<string, string> = {
    invention: '发明专利', utility_model: '实用新型', design: '外观设计', unknown: '未知',
  }

  if (loading && !stats) {
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

  const highRiskCount = Object.entries(stats.by_risk_level)
    .filter(([k]) => k === 'high' || k === 'critical')
    .reduce((sum, [, v]) => sum + v, 0)

  // 本年新增
  const currentYear = new Date().getFullYear().toString()
  const thisYearCount = stats.filing_trend.find(f => f.year === currentYear)?.count || 0

  // 近 3 年申请趋势合计
  const recent3Years = stats.filing_trend.slice(-3).reduce((s, f) => s + f.count, 0)

  return (
    <div>
      <div className="page-header" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', flexWrap: 'wrap', gap: 12 }}>
        <div>
          <h2 className="page-title">数据看板</h2>
          <p className="page-subtitle">专利数据多维概览 · 可按库 / 产品筛选</p>
        </div>
        <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
          <select
            className="form-input"
            value={filterDbId}
            onChange={(e) => { setFilterDbId(e.target.value === '' ? '' : Number(e.target.value)); setFilterProdId('') }}
            style={{ height: 32, fontSize: 13, minWidth: 140 }}
          >
            <option value="">全部库</option>
            {databases.map(d => <option key={d.id} value={d.id}>{d.name}</option>)}
          </select>
          <select
            className="form-input"
            value={filterProdId}
            onChange={(e) => setFilterProdId(e.target.value === '' ? '' : Number(e.target.value))}
            style={{ height: 32, fontSize: 13, minWidth: 140 }}
          >
            <option value="">全部产品</option>
            {products.map(p => <option key={p.id} value={p.id}>{p.name}</option>)}
          </select>
          <button className="btn btn-sm btn-secondary" onClick={loadStats}>刷新</button>
        </div>
      </div>

      {/* KPI 卡片（6 个） */}
      <div className="stats-cards" style={{ gridTemplateColumns: 'repeat(6, 1fr)' }}>
        <KpiCard label="专利总数" value={stats.total_patents} color="#1e40af" />
        <KpiCard label="已授权" value={stats.by_legal_status.granted || 0} color="#16a34a" />
        <KpiCard label="实审中" value={stats.by_legal_status.examining || 0} color="#ca8a04" />
        <KpiCard label="高风险" value={highRiskCount} color="#dc2626" />
        <KpiCard label={`${currentYear}年新增`} value={thisYearCount} color="#0ea5e9" />
        <KpiCard label="近3年申请" value={recent3Years} color="#7c3aed" />
      </div>

      {/* 申请趋势柱状图 */}
      <Card title="📅 申请趋势（按年份）" subtitle={`共 ${stats.filing_trend.length} 年数据`}>
        {stats.filing_trend.length > 0 ? (
          <BarChartTrend data={stats.filing_trend} />
        ) : (
          <Empty text="无申请日期数据" />
        )}
      </Card>

      {/* 法律状态分布 + 专利类型分布 */}
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16, marginBottom: 16 }}>
        <Card title="⚖️ 法律状态分布">
          <DonutChart
            data={Object.entries(stats.by_legal_status).map(([k, v]) => ({
              label: statusMap[k] || k, value: v, color: statusColors[k] || '#94a3b8',
            }))}
            total={stats.total_patents}
          />
        </Card>
        <Card title="📋 专利类型分布">
          <BarList
            data={Object.entries(stats.by_patent_type).map(([k, v]) => ({
              label: typeMap[k] || k, value: v, color: '#0ea5e9',
            }))}
            total={stats.total_patents}
          />
        </Card>
      </div>

      {/* 风险等级 + 国别分布 */}
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16, marginBottom: 16 }}>
        <Card title="⚠️ 风险等级分布">
          <BarList
            data={Object.entries(stats.by_risk_level).map(([k, v]) => ({
              label: riskMap[k] || k, value: v, color: riskColors[k] || '#94a3b8',
            }))}
            total={stats.total_patents}
          />
        </Card>
        <Card title="🌍 国别分布">
          <BarList
            data={Object.entries(stats.by_country || {}).map(([k, v]) => ({
              label: k, value: v, color: '#10b981',
            }))}
            total={stats.total_patents}
          />
        </Card>
      </div>

      {/* 按产品分布 + 按分类分布 */}
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16, marginBottom: 16 }}>
        <Card title="📦 按产品分布（Top 10）">
          <BarList
            data={stats.by_product.slice(0, 10).map(p => ({
              label: p.name || '(未命名)', value: p.count, color: '#7c3aed',
            }))}
            total={stats.total_patents}
          />
        </Card>
        <Card title="🏷️ 按业务分类分布">
          {Object.keys(stats.by_category).length > 0 ? (
            <BarList
              data={Object.entries(stats.by_category).map(([k, v]) => ({
                label: k, value: v, color: '#f59e0b',
              }))}
              total={stats.total_patents}
            />
          ) : (
            <Empty text="暂无分类数据" />
          )}
        </Card>
      </div>

      {/* Top IPC + Top 申请人 */}
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16, marginBottom: 16 }}>
        <Card title="🔩 Top 15 IPC 主分类">
          {stats.top_ipcs && stats.top_ipcs.length > 0 ? (
            <RankList
              data={stats.top_ipcs.map(i => ({ name: i.code, count: i.count }))}
            />
          ) : (
            <Empty text="暂无 IPC 数据" />
          )}
        </Card>
        <Card title="🏢 Top 10 申请人">
          {stats.top_applicants.length > 0 ? (
            <RankList data={stats.top_applicants.slice(0, 10).map(a => ({ name: a.name, count: a.count }))} />
          ) : (
            <Empty text="暂无申请人数据" />
          )}
        </Card>
      </div>

      {/* Top 10 发明人 */}
      <Card title="👤 Top 10 发明人">
        {stats.top_inventors.length > 0 ? (
          <RankList data={stats.top_inventors.slice(0, 10).map(a => ({ name: a.name, count: a.count }))} />
        ) : (
          <Empty text="暂无发明人数据" />
        )}
      </Card>
    </div>
  )
}

// ============ 子组件 ============

function KpiCard({ label, value, color }: { label: string; value: number; color: string }) {
  return (
    <div className="stat-card" style={{ borderLeft: `3px solid ${color}` }}>
      <div className="stat-value" style={{ color }}>{value}</div>
      <div className="stat-label">{label}</div>
    </div>
  )
}

function Card({ title, subtitle, children }: { title: string; subtitle?: string; children: React.ReactNode }) {
  return (
    <div className="table-container" style={{ marginBottom: 16 }}>
      <div style={{ padding: '10px 16px', borderBottom: '1px solid #e2e8f0', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <span style={{ fontWeight: 600, fontSize: 14, color: '#1f2937' }}>{title}</span>
        {subtitle && <span style={{ fontSize: 11, color: '#9ca3af' }}>{subtitle}</span>}
      </div>
      <div style={{ padding: 16 }}>{children}</div>
    </div>
  )
}

function Empty({ text }: { text: string }) {
  return <div style={{ textAlign: 'center', padding: 20, color: '#9ca3af', fontSize: 13 }}>{text}</div>
}

// 横向条形列表
function BarList({ data, total }: { data: { label: string; value: number; color: string }[]; total: number }) {
  if (data.length === 0) return <Empty text="无数据" />
  const sorted = [...data].sort((a, b) => b.value - a.value)
  return (
    <div>
      {sorted.map((item, i) => (
        <div key={i} style={{ display: 'flex', alignItems: 'center', marginBottom: 6, fontSize: 12 }}>
          <span style={{ width: 110, color: '#475569', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }} title={item.label}>
            {item.label}
          </span>
          <div style={{ flex: 1, height: 18, background: '#f1f5f9', borderRadius: 3, margin: '0 10px', overflow: 'hidden' }}>
            <div style={{
              height: '100%',
              width: `${total ? (item.value / total * 100) : 0}%`,
              background: item.color,
              borderRadius: 3,
              transition: 'width 0.3s',
            }} />
          </div>
          <span style={{ width: 60, textAlign: 'right', fontWeight: 500, color: '#1f2937' }}>
            {item.value}
            <span style={{ color: '#9ca3af', fontWeight: 400, marginLeft: 4, fontSize: 11 }}>
              {total ? `(${(item.value / total * 100).toFixed(1)}%)` : ''}
            </span>
          </span>
        </div>
      ))}
    </div>
  )
}

// 排名列表
function RankList({ data }: { data: { name: string; count: number }[] }) {
  const max = data[0]?.count || 1
  return (
    <div>
      {data.map((item, i) => (
        <div key={i} style={{ display: 'flex', alignItems: 'center', padding: '6px 0', borderBottom: '1px solid #f1f5f9', fontSize: 13 }}>
          <span style={{
            width: 24, height: 24, borderRadius: '50%', background: i < 3 ? ['#f59e0b', '#94a3b8', '#d97706'][i] : '#e5e7eb',
            color: i < 3 ? '#fff' : '#6b7280', display: 'inline-flex', alignItems: 'center', justifyContent: 'center',
            fontSize: 11, fontWeight: 600, marginRight: 10,
          }}>{i + 1}</span>
          <span style={{ flex: 1, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', color: '#1f2937' }} title={item.name}>
            {item.name}
          </span>
          <div style={{ width: 80, height: 6, background: '#f1f5f9', borderRadius: 3, margin: '0 8px', overflow: 'hidden' }}>
            <div style={{ width: `${(item.count / max * 100)}%`, height: '100%', background: '#3b82f6', borderRadius: 3 }} />
          </div>
          <span style={{ width: 40, textAlign: 'right', fontWeight: 500 }}>{item.count}</span>
        </div>
      ))}
    </div>
  )
}

// 申请趋势柱状图（SVG）
function BarChartTrend({ data }: { data: { year: string; count: number }[] }) {
  const width = 900
  const height = 200
  const padding = { top: 20, right: 20, bottom: 30, left: 40 }
  const innerW = width - padding.left - padding.right
  const innerH = height - padding.top - padding.bottom
  const max = Math.max(...data.map(d => d.count), 1)
  const barW = innerW / data.length * 0.7
  const gap = innerW / data.length * 0.3

  return (
    <div style={{ overflowX: 'auto' }}>
      <svg width={Math.max(width, data.length * 35)} height={height} style={{ display: 'block' }}>
        {/* Y 轴刻度 */}
        {[0, 0.25, 0.5, 0.75, 1].map((p, i) => {
          const y = padding.top + innerH * (1 - p)
          return (
            <g key={i}>
              <line x1={padding.left} y1={y} x2={Math.max(width, data.length * 35) - padding.right} y2={y} stroke="#e5e7eb" strokeWidth="1" />
              <text x={padding.left - 6} y={y + 4} textAnchor="end" fontSize="10" fill="#9ca3af">{Math.round(max * p)}</text>
            </g>
          )
        })}
        {/* 柱子 */}
        {data.map((d, i) => {
          const x = padding.left + i * (barW + gap) + gap / 2
          const h = (d.count / max) * innerH
          const y = padding.top + innerH - h
          return (
            <g key={i}>
              <rect x={x} y={y} width={barW} height={h} fill="#3b82f6" rx="2">
                <title>{`${d.year}: ${d.count}`}</title>
              </rect>
              <text x={x + barW / 2} y={y - 4} textAnchor="middle" fontSize="10" fill="#1f2937" fontWeight="500">{d.count}</text>
              <text x={x + barW / 2} y={height - 8} textAnchor="middle" fontSize="10" fill="#6b7280">{d.year}</text>
            </g>
          )
        })}
      </svg>
    </div>
  )
}

// 环形图（SVG）
function DonutChart({ data, total }: { data: { label: string; value: number; color: string }[]; total: number }) {
  const size = 180
  const cx = size / 2
  const cy = size / 2
  const r = 70
  const innerR = 45
  const filtered = data.filter(d => d.value > 0)
  const sum = filtered.reduce((s, d) => s + d.value, 0) || 1

  let cumulative = 0
  const arcs = filtered.map(d => {
    const startAngle = (cumulative / sum) * Math.PI * 2 - Math.PI / 2
    cumulative += d.value
    const endAngle = (cumulative / sum) * Math.PI * 2 - Math.PI / 2
    const x1 = cx + r * Math.cos(startAngle)
    const y1 = cy + r * Math.sin(startAngle)
    const x2 = cx + r * Math.cos(endAngle)
    const y2 = cy + r * Math.sin(endAngle)
    const x1i = cx + innerR * Math.cos(startAngle)
    const y1i = cy + innerR * Math.sin(startAngle)
    const x2i = cx + innerR * Math.cos(endAngle)
    const y2i = cy + innerR * Math.sin(endAngle)
    const largeArc = (endAngle - startAngle) > Math.PI ? 1 : 0
    const path = `M ${x1} ${y1} A ${r} ${r} 0 ${largeArc} 1 ${x2} ${y2} L ${x2i} ${y2i} A ${innerR} ${innerR} 0 ${largeArc} 0 ${x1i} ${y1i} Z`
    return { path, color: d.color, label: d.label, value: d.value }
  })

  return (
    <div style={{ display: 'flex', gap: 16, alignItems: 'center', flexWrap: 'wrap' }}>
      <svg width={size} height={size}>
        {arcs.map((a, i) => (
          <path key={i} d={a.path} fill={a.color}>
            <title>{`${a.label}: ${a.value} (${(a.value / sum * 100).toFixed(1)}%)`}</title>
          </path>
        ))}
        <text x={cx} y={cy - 4} textAnchor="middle" fontSize="20" fontWeight="700" fill="#1f2937">{total}</text>
        <text x={cx} y={cy + 14} textAnchor="middle" fontSize="10" fill="#6b7280">总数</text>
      </svg>
      <div style={{ flex: 1, minWidth: 180 }}>
        {filtered.map((d, i) => (
          <div key={i} style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 4, fontSize: 12 }}>
            <span style={{ width: 10, height: 10, background: d.color, borderRadius: 2 }} />
            <span style={{ flex: 1, color: '#475569' }}>{d.label}</span>
            <span style={{ fontWeight: 500, color: '#1f2937' }}>{d.value}</span>
            <span style={{ color: '#9ca3af', width: 40, textAlign: 'right' }}>
              {((d.value / sum) * 100).toFixed(1)}%
            </span>
          </div>
        ))}
      </div>
    </div>
  )
}
