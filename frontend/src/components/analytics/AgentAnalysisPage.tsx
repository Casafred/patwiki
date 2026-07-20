import { useState } from 'react'
import { analyticsApi, databaseApi, fieldApi } from '../../api'
import { useAppStore } from '../../store'
import type { PatentDatabase, FieldMeta } from '../../types'

const DIMENSION_LABELS: Record<string, string> = {
  legal_status: '法律状态',
  patent_type: '专利类型',
  country: '国家',
  category: '技术分类',
  risk_level: '风险等级',
  applicant: '申请人',
  inventor: '发明人',
  ipc_main: 'IPC主分类',
  application_number: '申请号',
  publication_number: '公开号',
  title: '标题',
  abstract: '摘要',
  module: '功能模块',
  product_id: '产品',
}

export default function AgentAnalysisPage() {
  const { currentDatabaseId } = useAppStore()
  const [requirement, setRequirement] = useState('')
  const [databases, setDatabases] = useState<PatentDatabase[]>([])
  const [fields, setFields] = useState<FieldMeta[]>([])
  const [selectedDb, setSelectedDb] = useState<number | ''>('')
  const [selectedDims, setSelectedDims] = useState<string[]>([
    'legal_status', 'patent_type', 'country', 'category', 'risk_level', 'applicant', 'inventor', 'ipc_main'
  ])
  const [loading, setLoading] = useState(false)
  const [result, setResult] = useState<any>(null)
  const [error, setError] = useState('')

  useState(() => {
    databaseApi.list().then(setDatabases).catch(() => {})
    fieldApi.list().then(setFields).catch(() => {})
    if (currentDatabaseId) setSelectedDb(currentDatabaseId)
  })

  const handleAnalyze = async () => {
    if (!requirement.trim()) {
      setError('请输入分析需求')
      return
    }
    setLoading(true)
    setError('')
    setResult(null)
    try {
      const res = await analyticsApi.agentAnalysis({
        requirement: requirement.trim(),
        database_id: selectedDb ? Number(selectedDb) : undefined,
        dimensions: selectedDims.length > 0 ? selectedDims : undefined,
      })
      setResult(res)
    } catch (e: any) {
      setError(e?.response?.data?.detail || e?.message || '分析失败')
    } finally {
      setLoading(false)
    }
  }

  const toggleDim = (key: string) => {
    setSelectedDims(prev => prev.includes(key) ? prev.filter(k => k !== key) : [...prev, key])
  }

  return (
    <div style={{ padding: '16px 20px', maxWidth: 1200 }}>
      <div style={{ marginBottom: 20 }}>
        <h2 className="page-title">AGENTAI 智能分析看板</h2>
        <p className="page-subtitle">输入分析需求，指定数据范围，系统会先做基层代码统计，再交给AI做多维分析</p>
      </div>

      {/* 分析需求输入区 */}
      <div style={{
        background: 'white', border: '1px solid #e2e8f0', borderRadius: 8, padding: 20, marginBottom: 20,
      }}>
        <div style={{ marginBottom: 12 }}>
          <label style={{ display: 'block', fontSize: 13, fontWeight: 600, color: '#0f172a', marginBottom: 6 }}>
            分析需求 <span style={{ color: '#dc2626' }}>*</span>
          </label>
          <textarea
            className="form-input"
            style={{ minHeight: 80, fontSize: 13, lineHeight: 1.5 }}
            value={requirement}
            onChange={e => setRequirement(e.target.value)}
            placeholder={'例如：\n1. 分析当前专利库的整体布局，找出技术空白点\n2. 按申请人和技术领域交叉分析，识别主要竞争对手的技术方向\n3. 评估风险专利的分布，给出规避建议'}
          />
        </div>

        <div style={{ display: 'flex', gap: 16, marginBottom: 12 }}>
          <div style={{ flex: 1 }}>
            <label style={{ display: 'block', fontSize: 12, color: '#475569', marginBottom: 4 }}>数据范围（库）</label>
            <select
              className="form-input"
              value={selectedDb}
              onChange={e => setSelectedDb(e.target.value ? Number(e.target.value) : '')}
            >
              <option value="">全部库</option>
              {databases.map(d => (
                <option key={d.id} value={d.id}>{d.name}</option>
              ))}
            </select>
          </div>
        </div>

        <div style={{ marginBottom: 12 }}>
          <label style={{ display: 'block', fontSize: 12, color: '#475569', marginBottom: 6 }}>
            统计维度（基层代码统计会按这些维度聚合，不选则使用默认维度）
          </label>
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>
            {fields.filter(f => !['id', 'abstract', 'claims', 'description_full', 'notes'].includes(f.key)).slice(0, 30).map(f => (
              <label
                key={f.key}
                style={{
                  display: 'flex', alignItems: 'center', gap: 4, fontSize: 12,
                  padding: '3px 8px', background: selectedDims.includes(f.key) ? '#dbeafe' : '#f8fafc',
                  border: `1px solid ${selectedDims.includes(f.key) ? '#93c5fd' : '#e2e8f0'}`,
                  borderRadius: 4, cursor: 'pointer', color: selectedDims.includes(f.key) ? '#1e40af' : '#475569',
                }}
              >
                <input
                  type="checkbox"
                  checked={selectedDims.includes(f.key)}
                  onChange={() => toggleDim(f.key)}
                  style={{ margin: 0 }}
                />
                {f.name}
              </label>
            ))}
          </div>
        </div>

        {error && (
          <div style={{ background: '#fef2f2', border: '1px solid #fecaca', color: '#dc2626', padding: 10, borderRadius: 6, marginBottom: 12, fontSize: 13 }}>
            {error}
          </div>
        )}

        <div style={{ display: 'flex', gap: 8 }}>
          <button className="btn btn-primary" onClick={handleAnalyze} disabled={loading}>
            {loading ? '分析中（基层统计+AI分析）...' : '🚀 开始智能分析'}
          </button>
          <button className="btn btn-secondary" onClick={() => { setRequirement(''); setResult(null); setError('') }}>
            清空
          </button>
        </div>
      </div>

      {/* 加载中提示 */}
      {loading && (
        <div style={{
          background: 'white', border: '1px solid #e2e8f0', borderRadius: 8, padding: 40,
          textAlign: 'center', marginBottom: 20,
        }}>
          <div className="spinner" style={{ width: 36, height: 36, margin: '0 auto 16px', borderWidth: 3 }}></div>
          <div style={{ fontSize: 14, color: '#475569', fontWeight: 500, marginBottom: 6 }}>正在进行两阶段分析</div>
          <div style={{ fontSize: 12, color: '#94a3b8' }}>
            第一阶段：基层代码统计（SQL聚合） → 第二阶段：AI多维分析（LLM生成报告）
          </div>
        </div>
      )}

      {/* 分析结果 */}
      {result && !loading && (
        <>
          {/* 第一阶段：基层统计 */}
          {result.base_stats && (
            <div style={{
              background: 'white', border: '1px solid #e2e8f0', borderRadius: 8, padding: 20, marginBottom: 20,
            }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 16 }}>
                <span style={{
                  padding: '2px 8px', background: '#f1f5f9', borderRadius: 4, fontSize: 11, fontWeight: 600, color: '#475569',
                }}>阶段1</span>
                <h3 style={{ fontSize: 15, fontWeight: 600, margin: 0 }}>基层代码统计</h3>
                <span style={{ fontSize: 12, color: '#94a3b8' }}>共 {result.base_stats.total} 条专利</span>
              </div>

              <div style={{
                padding: '10px 12px', background: '#f8fafc', borderRadius: 6, fontSize: 12, color: '#475569',
                marginBottom: 16, lineHeight: 1.6,
              }}>
                {result.base_stats.summary}
              </div>

              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(300px, 1fr))', gap: 16 }}>
                {Object.entries(result.base_stats.dimensions || {}).map(([dim, items]: [string, any]) => (
                  <div key={dim} style={{
                    border: '1px solid #e2e8f0', borderRadius: 6, padding: 12, background: '#fafbfc',
                  }}>
                    <div style={{ fontSize: 12, fontWeight: 600, color: '#0f172a', marginBottom: 8 }}>
                      {DIMENSION_LABELS[dim] || dim}（{items.length}）
                    </div>
                    <div style={{ display: 'flex', flexDirection: 'column', gap: 4, maxHeight: 200, overflowY: 'auto' }}>
                      {items.slice(0, 10).map((item: any, i: number) => (
                        <div key={i} style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: 11 }}>
                          <span style={{ flex: 1, color: '#475569', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                            {item.value}
                          </span>
                          <span style={{ fontFamily: 'monospace', color: '#2563eb', minWidth: 36, textAlign: 'right' }}>
                            {item.count}
                          </span>
                          <span style={{ color: '#94a3b8', minWidth: 36, textAlign: 'right' }}>
                            {item.percentage}%
                          </span>
                        </div>
                      ))}
                    </div>
                  </div>
                ))}
              </div>

              {result.base_stats.filing_trend && result.base_stats.filing_trend.length > 0 && (
                <div style={{ marginTop: 16, border: '1px solid #e2e8f0', borderRadius: 6, padding: 12, background: '#fafbfc' }}>
                  <div style={{ fontSize: 12, fontWeight: 600, color: '#0f172a', marginBottom: 8 }}>申请年份趋势</div>
                  <div style={{ display: 'flex', gap: 4, alignItems: 'flex-end', height: 80 }}>
                    {result.base_stats.filing_trend.map((t: any, i: number) => {
                      const max = Math.max(...result.base_stats.filing_trend.map((x: any) => x.count))
                      const h = max > 0 ? (t.count / max * 100) : 0
                      return (
                        <div key={i} style={{ flex: 1, minWidth: 30, display: 'flex', flexDirection: 'column', alignItems: 'center' }}>
                          <div style={{ fontSize: 10, color: '#64748b', marginBottom: 2 }}>{t.count}</div>
                          <div style={{
                            width: '100%', height: `${h}%`, minHeight: 2,
                            background: 'linear-gradient(180deg, #3b82f6, #60a5fa)',
                            borderRadius: '2px 2px 0 0',
                          }}></div>
                          <div style={{ fontSize: 10, color: '#94a3b8', marginTop: 2 }}>{t.year}</div>
                        </div>
                      )
                    })}
                  </div>
                </div>
              )}
            </div>
          )}

          {/* 第二阶段：AI分析 */}
          {result.ai_analysis && (
            <div style={{
              background: 'white', border: '1px solid #e2e8f0', borderRadius: 8, padding: 20, marginBottom: 20,
            }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 16 }}>
                <span style={{
                  padding: '2px 8px', background: '#dbeafe', borderRadius: 4, fontSize: 11, fontWeight: 600, color: '#1e40af',
                }}>阶段2</span>
                <h3 style={{ fontSize: 15, fontWeight: 600, margin: 0 }}>AI 多维分析</h3>
              </div>

              {result.ai_analysis.overview && (
                <div style={{
                  padding: 12, background: '#f0f9ff', borderRadius: 6, marginBottom: 16,
                  fontSize: 13, color: '#0c4a6e', lineHeight: 1.7,
                }}>
                  <strong>📊 总体概述：</strong>{result.ai_analysis.overview}
                </div>
              )}

              {result.ai_analysis.key_findings && result.ai_analysis.key_findings.length > 0 && (
                <div style={{ marginBottom: 16 }}>
                  <h4 style={{ fontSize: 13, fontWeight: 600, color: '#0f172a', marginBottom: 8 }}>🔍 关键发现</h4>
                  <ul style={{ margin: 0, paddingLeft: 20, fontSize: 13, color: '#334155', lineHeight: 1.8 }}>
                    {result.ai_analysis.key_findings.map((f: string, i: number) => (
                      <li key={i}>{f}</li>
                    ))}
                  </ul>
                </div>
              )}

              {result.ai_analysis.dimension_analysis && Object.keys(result.ai_analysis.dimension_analysis).length > 0 && (
                <div style={{ marginBottom: 16 }}>
                  <h4 style={{ fontSize: 13, fontWeight: 600, color: '#0f172a', marginBottom: 8 }}>📐 维度分析</h4>
                  <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
                    {Object.entries(result.ai_analysis.dimension_analysis).map(([dim, analysis]: [string, any]) => (
                      <div key={dim} style={{
                        padding: 10, background: '#f8fafc', borderRadius: 4, fontSize: 12, lineHeight: 1.6,
                      }}>
                        <strong style={{ color: '#1e40af' }}>{DIMENSION_LABELS[dim] || dim}：</strong>
                        <span style={{ color: '#475569' }}>{String(analysis)}</span>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {result.ai_analysis.anomalies && result.ai_analysis.anomalies.length > 0 && (
                <div style={{ marginBottom: 16 }}>
                  <h4 style={{ fontSize: 13, fontWeight: 600, color: '#dc2626', marginBottom: 8 }}>⚠️ 异常点</h4>
                  <ul style={{ margin: 0, paddingLeft: 20, fontSize: 13, color: '#7f1d1d', lineHeight: 1.8 }}>
                    {result.ai_analysis.anomalies.map((a: string, i: number) => (
                      <li key={i}>{a}</li>
                    ))}
                  </ul>
                </div>
              )}

              {result.ai_analysis.recommendations && result.ai_analysis.recommendations.length > 0 && (
                <div style={{ marginBottom: 16 }}>
                  <h4 style={{ fontSize: 13, fontWeight: 600, color: '#15803d', marginBottom: 8 }}>💡 建议</h4>
                  <ul style={{ margin: 0, paddingLeft: 20, fontSize: 13, color: '#14532d', lineHeight: 1.8 }}>
                    {result.ai_analysis.recommendations.map((r: string, i: number) => (
                      <li key={i}>{r}</li>
                    ))}
                  </ul>
                </div>
              )}

              {result.ai_analysis.risk_warnings && result.ai_analysis.risk_warnings.length > 0 && (
                <div>
                  <h4 style={{ fontSize: 13, fontWeight: 600, color: '#b45309', marginBottom: 8 }}>🚨 风险提示</h4>
                  <ul style={{ margin: 0, paddingLeft: 20, fontSize: 13, color: '#78350f', lineHeight: 1.8 }}>
                    {result.ai_analysis.risk_warnings.map((r: string, i: number) => (
                      <li key={i}>{r}</li>
                    ))}
                  </ul>
                </div>
              )}
            </div>
          )}
        </>
      )}
    </div>
  )
}
