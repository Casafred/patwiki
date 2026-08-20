import type { EdgeData, Graph, NodeData } from '@antv/g6'
import { useCallback, useEffect, useRef, useState } from 'react'
import { patentApi } from '../../api'
import type { PatentGraphNode, PatentGraphResponse } from '../../types'
import { getErrorMessage } from '../../lib/errors'

interface PatentGraphProps {
  patentId: number
  onPatentNavigate?: (patentId: number) => void
}

function nodeKind(data: NodeData): string {
  return String(data.data?.kind || '')
}

function edgeRelation(data: EdgeData): string {
  return String(data.data?.relation || '')
}

export default function PatentGraph({ patentId, onPatentNavigate }: PatentGraphProps) {
  const containerRef = useRef<HTMLDivElement | null>(null)
  const graphRef = useRef<Graph | null>(null)
  const [graphData, setGraphData] = useState<PatentGraphResponse | null>(null)
  const [depth, setDepth] = useState(1)
  const [includeFamily, setIncludeFamily] = useState(true)
  const [includeCitations, setIncludeCitations] = useState(true)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [selectedNode, setSelectedNode] = useState<PatentGraphNode | null>(null)

  const loadGraph = useCallback(async () => {
    setLoading(true)
    try {
      const result = await patentApi.getGraph(patentId, {
        depth,
        include_family: includeFamily,
        include_citations: includeCitations,
      })
      setGraphData(result)
      setSelectedNode(null)
      setError(null)
    } catch (reason: unknown) {
      setError(getErrorMessage(reason, '加载关系图谱失败'))
      setGraphData(null)
    } finally {
      setLoading(false)
    }
  }, [depth, includeCitations, includeFamily, patentId])

  useEffect(() => {
    // The graph panel synchronizes its canvas data with the selected patent.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    void loadGraph()
  }, [loadGraph])

  useEffect(() => {
    const container = containerRef.current
    if (!container || !graphData) return

    let graph: Graph | null = null
    let cancelled = false
    const renderGraph = async () => {
      // G6 is only needed when the relations tab is opened, so keep it out of the initial bundle.
      const { Graph: G6Graph } = await import('@antv/g6')
      if (cancelled || !containerRef.current) return
      graph = new G6Graph({
        container,
        autoResize: true,
        height: 390,
        padding: 24,
        animation: false,
        data: {
          nodes: graphData.nodes.map(node => ({ id: node.id, data: { ...node } })),
          edges: graphData.edges.map(edge => ({
            id: edge.id,
            source: edge.source,
            target: edge.target,
            data: { ...edge },
          })),
        },
        layout: {
          type: 'force',
          preventOverlap: true,
          nodeSize: 46,
          linkDistance: 150,
          edgeStrength: 0.5,
        },
        node: {
          type: 'circle',
          style: {
            size: 44,
            fill: (data: NodeData) => {
              const kind = nodeKind(data)
              return kind === 'root' ? '#2563eb' : kind === 'family' ? '#0f766e' : '#64748b'
            },
            stroke: '#ffffff',
            lineWidth: 2,
            labelText: (data: NodeData) => String(data.data?.label || ''),
            labelPlacement: 'bottom',
            labelFill: '#334155',
            labelFontSize: 11,
            labelMaxLines: 2,
            labelWordWrap: true,
            labelWordWrapWidth: 150,
          },
        },
        edge: {
          type: 'line',
          style: {
            stroke: (data: EdgeData) => edgeRelation(data) === 'family' ? '#0f766e' : '#94a3b8',
            lineDash: (data: EdgeData) => edgeRelation(data) === 'family' ? [5, 4] : undefined,
            lineWidth: 1.5,
            endArrow: (data: EdgeData) => edgeRelation(data) === 'citation',
            labelText: (data: EdgeData) => String(data.data?.label || ''),
            labelFill: '#64748b',
            labelFontSize: 10,
          },
        },
        behaviors: ['drag-canvas', 'zoom-canvas', 'drag-element'],
      })
      if (cancelled) {
        graph.destroy()
        return
      }
      graphRef.current = graph
      graph.on('node:click', (event: unknown) => {
        if (!event || typeof event !== 'object') return
        const target = (event as { target?: { id?: string } }).target
        const node = graphData.nodes.find(item => item.id === target?.id)
        if (node) setSelectedNode(node)
      })
      void graph.render()
    }
    void renderGraph()

    return () => {
      cancelled = true
      graph?.destroy()
      graphRef.current = null
    }
  }, [graphData])

  return (
    <section className="patent-graph-panel">
      <div className="patent-graph-toolbar">
        <div>
          <h3 style={{ margin: 0, color: '#0f172a', fontSize: 15 }}>关系图谱</h3>
          {graphData && (
            <div style={{ marginTop: 4, color: '#94a3b8', fontSize: 11 }}>
              {graphData.counts.nodes} 个节点 · {graphData.counts.citation_edges} 条引用 · {graphData.counts.family_edges} 条同族
            </div>
          )}
        </div>
        <div style={{ display: 'flex', flexWrap: 'wrap', alignItems: 'center', gap: 8 }}>
          <label className="patent-graph-control">
            深度
            <select value={depth} onChange={event => setDepth(Number(event.target.value))}>
              <option value={1}>1 层</option>
              <option value={2}>2 层</option>
            </select>
          </label>
          <label className="patent-graph-check">
            <input type="checkbox" checked={includeFamily} onChange={event => setIncludeFamily(event.target.checked)} />
            同族
          </label>
          <label className="patent-graph-check">
            <input type="checkbox" checked={includeCitations} onChange={event => setIncludeCitations(event.target.checked)} />
            引用
          </label>
          <button className="btn btn-xs btn-secondary" onClick={() => void loadGraph()} disabled={loading}>
            {loading ? '加载中...' : '刷新'}
          </button>
        </div>
      </div>

      {error && <div className="patent-graph-message error">{error}</div>}
      {selectedNode && (
        <div className="patent-graph-selection">
          <strong>{selectedNode.title}</strong>
          <span>{selectedNode.number}</span>
          <span>{selectedNode.kind === 'family' ? '同族专利' : selectedNode.kind === 'citation' ? '引用关系节点' : '当前专利'}</span>
          {selectedNode.patent_id !== patentId && onPatentNavigate && (
            <button
              className="btn btn-xs btn-primary"
              type="button"
              onClick={() => onPatentNavigate(selectedNode.patent_id)}
            >
              打开专利详情
            </button>
          )}
        </div>
      )}
      {!error && graphData && graphData.nodes.length === 1 && (
        <div className="patent-graph-message">当前专利还没有已入库的同族或引用关系。</div>
      )}
      <div ref={containerRef} className="patent-graph-canvas" aria-label="专利引用与同族关系图谱" />
      <div className="patent-graph-legend">
        <span><i className="patent-graph-dot root" />当前专利</span>
        <span><i className="patent-graph-dot family" />同族专利</span>
        <span><i className="patent-graph-dot citation" />引用关系</span>
      </div>
    </section>
  )
}
