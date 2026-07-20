import { useEffect, useState, useCallback, useMemo } from 'react'
import { patentApi } from '../../api'
import type { GraphNode, GraphEdge, PatentGraph } from '../../types'

interface PatentGraphTabProps {
  patentId: number
  /** 点击节点时跳转到该专利详情 */
  onNavigatePatent?: (patentId: number) => void
}

/**
 * P2-7：专利引用 / 同族关系图谱
 *
 * - 中心节点 = 当前专利（大圆 + 蓝色）
 * - 同族（family）= 同色（青绿）放在右上方扇区，边为虚线
 * - 被引用（citing，引用本专利的）= 橙色，放在左侧扇区，箭头指向中心
 * - 引用了（cited，本专利引用的）= 紫色，放在右侧扇区，箭头从中心指向该节点
 * - 节点支持点击跳转，hover 显示卡片
 * - 二度展开（depth=2）时，节点显示淡色描边表示间接关系
 */
export default function PatentGraphTab({ patentId, onNavigatePatent }: PatentGraphTabProps) {
  const [graph, setGraph] = useState<PatentGraph | null>(null)
  const [loading, setLoading] = useState(false)
  const [depth, setDepth] = useState<1 | 2>(1)
  const [error, setError] = useState<string | null>(null)
  const [hoverNode, setHoverNode] = useState<GraphNode | null>(null)
  const [addCitationId, setAddCitationId] = useState<string>('')
  const [addingCitation, setAddingCitation] = useState(false)
  const [addCitationError, setAddCitationError] = useState<string | null>(null)

  const loadGraph = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const g = await patentApi.getGraph(patentId, depth)
      setGraph(g)
    } catch (e: any) {
      setError(e?.message || '加载图谱失败')
      setGraph(null)
    } finally {
      setLoading(false)
    }
  }, [patentId, depth])

  useEffect(() => {
    loadGraph()
  }, [loadGraph])

  // 计算节点位置（径向布局：3 个扇区，每扇区按节点数等分）
  const layout = useMemo(() => {
    if (!graph) return { positions: new Map<number, { x: number; y: number }>(), edges: [] as (GraphEdge & { x1: number; y1: number; x2: number; y2: number })[] }
    const W = 820
    const H = 480
    const cx = W / 2
    const cy = H / 2

    const citingNodes = graph.nodes.filter(n => n.relation === 'citing')
    const citedNodes = graph.nodes.filter(n => n.relation === 'cited')
    const familyNodes = graph.nodes.filter(n => n.relation === 'family')

    const positions = new Map<number, { x: number; y: number }>()
    positions.set(graph.center_id, { x: cx, y: cy })

    // 扇区角度范围：
    // citing (左): 135° ~ 225° (跨 90°)
    // cited  (右): -45° ~ 45° (跨 90°)
    // family (上): 45° ~ 135° (跨 90°)
    const radius1 = 180
    const radius2 = 280

    const placeArc = (nodes: GraphNode[], startDeg: number, endDeg: number) => {
      if (nodes.length === 0) return
      const span = endDeg - startDeg
      const step = nodes.length === 1 ? 0 : span / (nodes.length - 1)
      nodes.forEach((n, i) => {
        const angleDeg = startDeg + step * i
        const angleRad = (angleDeg * Math.PI) / 180
        const r = n.distance === 1 ? radius1 : radius2
        const x = cx + r * Math.cos(angleRad)
        const y = cy + r * Math.sin(angleRad)
        positions.set(n.id, { x, y })
      })
    }

    placeArc(citingNodes, 135, 225)
    placeArc(citedNodes, -45, 45)
    placeArc(familyNodes, 45, 135)

    // 边坐标
    const edges = graph.edges.map(e => {
      const a = positions.get(e.source)
      const b = positions.get(e.target)
      if (!a || !b) return null
      return { ...e, x1: a.x, y1: a.y, x2: b.x, y2: b.y }
    }).filter(Boolean) as (GraphEdge & { x1: number; y1: number; x2: number; y2: number })[]

    return { positions, edges, W, H, cx, cy }
  }, [graph])

  const handleAddCitation = async () => {
    const idStr = addCitationId.trim()
    if (!idStr) return
    const targetId = parseInt(idStr, 10)
    if (!Number.isFinite(targetId) || targetId <= 0) {
      setAddCitationError('请输入有效的专利 ID')
      return
    }
    if (targetId === patentId) {
      setAddCitationError('不能引用自身')
      return
    }
    setAddingCitation(true)
    setAddCitationError(null)
    try {
      const r = await patentApi.addCitation(patentId, targetId)
      if (r.already_exists) {
        setAddCitationError('该引用关系已存在')
      } else {
        setAddCitationId('')
        await loadGraph()
      }
    } catch (e: any) {
      const detail = e?.response?.data?.detail
      setAddCitationError(detail || e?.message || '添加失败')
    } finally {
      setAddingCitation(false)
    }
  }

  const handleRemoveCitation = async (citedPatentId: number) => {
    if (!confirm('确认删除该引用关系？')) return
    try {
      await patentApi.removeCitation(patentId, citedPatentId)
      await loadGraph()
    } catch (e: any) {
      const detail = e?.response?.data?.detail
      alert(detail || e?.message || '删除失败')
    }
  }

  // 节点配色
  const colorOf = (n: GraphNode): string => {
    if (n.is_center) return '#2563eb'
    if (n.relation === 'family') return '#10b981'
    if (n.relation === 'citing') return '#f59e0b'
    if (n.relation === 'cited') return '#8b5cf6'
    return '#6b7280'
  }

  const nodeRadius = (n: GraphNode): number => {
    if (n.is_center) return 30
    if (n.distance === 1) return 22
    return 16
  }

  if (loading && !graph) {
    return <div style={{ padding: 24, textAlign: 'center', color: '#64748b' }}>加载关系图谱...</div>
  }
  if (error) {
    return (
      <div style={{ padding: 24 }}>
        <div style={{ color: '#dc2626', marginBottom: 12 }}>{error}</div>
        <button className="btn btn-secondary btn-sm" onClick={loadGraph}>重试</button>
      </div>
    )
  }
  if (!graph) return null

  return (
    <div>
      {/* 工具栏 */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 12, flexWrap: 'wrap' }}>
        <div style={{ fontSize: 13, color: '#475569' }}>
          共 {graph.stats.total_nodes} 节点 / {graph.stats.total_edges} 边 ·
          <span style={{ color: '#10b981', marginLeft: 4 }}>同族 {graph.stats.family_count}</span> ·
          <span style={{ color: '#f59e0b', marginLeft: 4 }}>被引 {graph.stats.citing_count}</span> ·
          <span style={{ color: '#8b5cf6', marginLeft: 4 }}>引用 {graph.stats.cited_count}</span>
        </div>
        <div style={{ display: 'flex', gap: 4, padding: 2, background: '#f1f5f9', borderRadius: 6 }}>
          <button
            className={`btn btn-sm ${depth === 1 ? 'btn-primary' : 'btn-secondary'}`}
            style={{ padding: '3px 10px', fontSize: 12 }}
            onClick={() => setDepth(1)}
          >1 度</button>
          <button
            className={`btn btn-sm ${depth === 2 ? 'btn-primary' : 'btn-secondary'}`}
            style={{ padding: '3px 10px', fontSize: 12 }}
            onClick={() => setDepth(2)}
          >2 度</button>
        </div>
        <button className="btn btn-sm btn-secondary" onClick={loadGraph} disabled={loading}>
          {loading ? '刷新中...' : '刷新'}
        </button>

        {/* 添加引用 */}
        <div style={{ display: 'flex', gap: 4, alignItems: 'center', marginLeft: 'auto' }}>
          <input
            type="number"
            className="form-input"
            style={{ width: 120, height: 30, fontSize: 13 }}
            placeholder="引用专利 ID"
            value={addCitationId}
            onChange={e => setAddCitationId(e.target.value)}
            onKeyDown={e => { if (e.key === 'Enter') { e.preventDefault(); handleAddCitation() } }}
          />
          <button
            className="btn btn-sm btn-primary"
            onClick={handleAddCitation}
            disabled={addingCitation || !addCitationId.trim()}
          >添加引用</button>
        </div>
      </div>
      {addCitationError && (
        <div style={{ fontSize: 12, color: '#dc2626', marginBottom: 8 }}>{addCitationError}</div>
      )}

      {/* 图例 */}
      <div style={{ display: 'flex', gap: 16, fontSize: 12, color: '#475569', marginBottom: 8 }}>
        <LegendDot color="#2563eb" label="当前专利" />
        <LegendDot color="#10b981" label="同族" />
        <LegendDot color="#f59e0b" label="被引用（他引我）" />
        <LegendDot color="#8b5cf6" label="引用了（我引他）" />
        <span style={{ color: '#94a3b8' }}>· 实线 = 引用 · 虚线 = 同族</span>
      </div>

      {/* SVG 图谱 */}
      <div style={{ border: '1px solid #e2e8f0', borderRadius: 8, background: '#fafbfc', overflow: 'hidden', position: 'relative' }}>
        <svg width={layout.W} height={layout.H} style={{ display: 'block' }}>
          <defs>
            {/* 箭头：橙色（被引 → 中心）和紫色（中心 → 引用） */}
            <marker id="arrow-citation" viewBox="0 0 10 10" refX="9" refY="5"
              markerWidth="6" markerHeight="6" orient="auto-start-reverse">
              <path d="M 0 0 L 10 5 L 0 10 z" fill="#64748b" />
            </marker>
          </defs>

          {/* 边 */}
          {layout.edges.map((e, idx) => {
            const isFamily = e.type === 'family'
            return (
              <line
                key={`edge-${idx}`}
                x1={e.x1} y1={e.y1} x2={e.x2} y2={e.y2}
                stroke={isFamily ? '#10b981' : '#64748b'}
                strokeWidth={1.5}
                strokeDasharray={isFamily ? '5,4' : 'none'}
                markerEnd={isFamily ? undefined : 'url(#arrow-citation)'}
                opacity={0.65}
              />
            )
          })}

          {/* 节点 */}
          {graph.nodes.map(n => {
            const pos = layout.positions.get(n.id)
            if (!pos) return null
            const r = nodeRadius(n)
            const fill = colorOf(n)
            const titleShort = (n.title || '').length > 14 ? (n.title || '').slice(0, 14) + '...' : (n.title || '')
            return (
              <g
                key={`node-${n.id}`}
                transform={`translate(${pos.x}, ${pos.y})`}
                style={{ cursor: onNavigatePatent ? 'pointer' : 'default' }}
                onMouseEnter={() => setHoverNode(n)}
                onMouseLeave={() => setHoverNode(null)}
                onClick={() => {
                  if (n.is_center) return
                  onNavigatePatent?.(n.id)
                }}
              >
                <circle
                  r={r}
                  fill={fill}
                  fillOpacity={n.distance === 2 ? 0.55 : 0.85}
                  stroke="#fff"
                  strokeWidth={2}
                />
                {n.is_center && (
                  <circle r={r + 4} fill="none" stroke={fill} strokeWidth={1.5} strokeDasharray="3,2" opacity={0.6} />
                )}
                <text
                  textAnchor="middle"
                  y={r + 12}
                  fontSize={11}
                  fill="#1e293b"
                  fontWeight={n.is_center ? 600 : 400}
                >{titleShort}</text>
                <text
                  textAnchor="middle"
                  y={r + 25}
                  fontSize={9.5}
                  fill="#94a3b8"
                >{n.application_number || `#${n.id}`}</text>
              </g>
            )
          })}
        </svg>

        {/* 悬浮卡片 */}
        {hoverNode && (() => {
          const pos = layout.positions.get(hoverNode.id)
          if (!pos) return null
          const cardX = pos.x + 20
          const cardY = pos.y - 60
          return (
            <div style={{
              position: 'absolute',
              left: cardX,
              top: cardY,
              width: 240,
              background: '#fff',
              border: '1px solid #e2e8f0',
              borderRadius: 6,
              boxShadow: '0 8px 24px rgba(0,0,0,0.12)',
              padding: 10,
              fontSize: 12,
              pointerEvents: 'none',
              zIndex: 5,
            }}>
              <div style={{ fontWeight: 600, color: '#0f172a', marginBottom: 4, lineHeight: 1.4 }}>
                {hoverNode.title || `#${hoverNode.id}`}
              </div>
              <div style={{ color: '#64748b', marginBottom: 2 }}>
                申请号: {hoverNode.application_number || '-'}
              </div>
              <div style={{ color: '#64748b', marginBottom: 2 }}>
                申请人: {hoverNode.applicant || '-'}
              </div>
              <div style={{ color: '#64748b', marginBottom: 2 }}>
                申请日: {hoverNode.filing_date || '-'}
              </div>
              <div style={{ color: '#64748b', marginBottom: 2 }}>
                国别: {hoverNode.country || '-'} · 类型: {hoverNode.patent_type || '-'} · 状态: {hoverNode.legal_status || '-'}
              </div>
              <div style={{ color: '#94a3b8', marginTop: 4 }}>
                关系: {hoverNode.is_center ? '中心' : hoverNode.relation === 'family' ? '同族' : hoverNode.relation === 'citing' ? '被该专利引用' : '该专利引用了'}
                {hoverNode.distance > 0 && ` · ${hoverNode.distance}度`}
              </div>
            </div>
          )
        })()}
      </div>

      {/* 引用列表（可删除） */}
      {graph.nodes.filter(n => n.relation === 'cited').length > 0 && (
        <div style={{ marginTop: 16 }}>
          <div style={{ fontSize: 13, fontWeight: 600, color: '#475569', marginBottom: 6 }}>
            本专利引用了（共 {graph.stats.cited_count} 件，可删除）
          </div>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(280px, 1fr))', gap: 6 }}>
            {graph.nodes.filter(n => n.relation === 'cited').map(n => (
              <div key={`cited-${n.id}`} style={{
                padding: '8px 10px',
                border: '1px solid #e2e8f0',
                borderRadius: 6,
                background: '#fff',
                fontSize: 12,
                display: 'flex',
                alignItems: 'center',
                gap: 8,
              }}>
                <span style={{ display: 'inline-block', width: 8, height: 8, borderRadius: '50%', background: '#8b5cf6', flexShrink: 0 }} />
                <div style={{ flex: 1, overflow: 'hidden' }}>
                  <div style={{ color: '#1e293b', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
                    {n.title || `#${n.id}`}
                  </div>
                  <div style={{ color: '#94a3b8', fontSize: 11 }}>{n.application_number || ''}</div>
                </div>
                {onNavigatePatent && (
                  <button
                    className="btn btn-sm btn-secondary"
                    style={{ padding: '2px 8px', fontSize: 11 }}
                    onClick={() => onNavigatePatent(n.id)}
                  >查看</button>
                )}
                <button
                  className="btn btn-sm"
                  style={{ padding: '2px 8px', fontSize: 11, color: '#dc2626', background: '#fef2f2', border: '1px solid #fecaca' }}
                  onClick={() => handleRemoveCitation(n.id)}
                >删除</button>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* 被引列表（只读） */}
      {graph.nodes.filter(n => n.relation === 'citing').length > 0 && (
        <div style={{ marginTop: 12 }}>
          <div style={{ fontSize: 13, fontWeight: 600, color: '#475569', marginBottom: 6 }}>
            引用了本专利（共 {graph.stats.citing_count} 件）
          </div>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(280px, 1fr))', gap: 6 }}>
            {graph.nodes.filter(n => n.relation === 'citing').map(n => (
              <div key={`citing-${n.id}`} style={{
                padding: '8px 10px',
                border: '1px solid #e2e8f0',
                borderRadius: 6,
                background: '#fff',
                fontSize: 12,
                display: 'flex',
                alignItems: 'center',
                gap: 8,
              }}>
                <span style={{ display: 'inline-block', width: 8, height: 8, borderRadius: '50%', background: '#f59e0b', flexShrink: 0 }} />
                <div style={{ flex: 1, overflow: 'hidden' }}>
                  <div style={{ color: '#1e293b', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
                    {n.title || `#${n.id}`}
                  </div>
                  <div style={{ color: '#94a3b8', fontSize: 11 }}>{n.application_number || ''}</div>
                </div>
                {onNavigatePatent && (
                  <button
                    className="btn btn-sm btn-secondary"
                    style={{ padding: '2px 8px', fontSize: 11 }}
                    onClick={() => onNavigatePatent(n.id)}
                  >查看</button>
                )}
              </div>
            ))}
          </div>
        </div>
      )}

      {/* 同族列表 */}
      {graph.nodes.filter(n => n.relation === 'family').length > 0 && (
        <div style={{ marginTop: 12 }}>
          <div style={{ fontSize: 13, fontWeight: 600, color: '#475569', marginBottom: 6 }}>
            同族专利（共 {graph.stats.family_count} 件）
          </div>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(280px, 1fr))', gap: 6 }}>
            {graph.nodes.filter(n => n.relation === 'family').map(n => (
              <div key={`family-${n.id}`} style={{
                padding: '8px 10px',
                border: '1px solid #e2e8f0',
                borderRadius: 6,
                background: '#fff',
                fontSize: 12,
                display: 'flex',
                alignItems: 'center',
                gap: 8,
              }}>
                <span style={{ display: 'inline-block', width: 8, height: 8, borderRadius: '50%', background: '#10b981', flexShrink: 0 }} />
                <div style={{ flex: 1, overflow: 'hidden' }}>
                  <div style={{ color: '#1e293b', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
                    {n.title || `#${n.id}`}
                  </div>
                  <div style={{ color: '#94a3b8', fontSize: 11 }}>{n.application_number || ''}</div>
                </div>
                {onNavigatePatent && (
                  <button
                    className="btn btn-sm btn-secondary"
                    style={{ padding: '2px 8px', fontSize: 11 }}
                    onClick={() => onNavigatePatent(n.id)}
                  >查看</button>
                )}
              </div>
            ))}
          </div>
        </div>
      )}

      {graph.stats.total_nodes === 1 && (
        <div style={{ marginTop: 16, padding: 16, background: '#f8fafc', borderRadius: 6, color: '#64748b', fontSize: 13, textAlign: 'center' }}>
          当前专利暂无引用与同族关系。
          <br />
          可通过上方"添加引用"输入其他专利 ID 建立引用关系；同族关系由导入时的 priority_number 自动归并。
        </div>
      )}
    </div>
  )
}

function LegendDot({ color, label }: { color: string; label: string }) {
  return (
    <span style={{ display: 'inline-flex', alignItems: 'center', gap: 4 }}>
      <span style={{ display: 'inline-block', width: 10, height: 10, borderRadius: '50%', background: color }} />
      {label}
    </span>
  )
}
