import { useMemo, useState } from 'react'
import type { JsonObject, Patent } from '../../types'
import { aiService } from '../../services'
import { getErrorMessage } from '../../lib/errors'
import Icon from '../common/Icon'

interface Props { patents: Patent[]; onClose: () => void }

const DEFAULT_QUESTIONS = JSON.stringify({
  technical_relevance: {
    type: 'choice', instructions: '请选择该专利最匹配的技术主题。',
    criteria: { target: '属于目标主题', related: '部分相关', other: '不相关' },
  },
  needs_review: { type: 'noul', instructions: '是否需要人工复核后再写入正式标引字段？' },
  priority: { type: 'score', instructions: '评估该专利的标引优先级。', criteria: ['低', '中', '高'] },
}, null, 2)

const PATENT_TRIAGE_QUESTIONS = JSON.stringify({
  ipc_theme: { type: 'choice', instructions: '根据摘要、权利要求和 IPC/CPC，选择最匹配的技术主题。', criteria: { core: '核心相关', adjacent: '相邻技术', irrelevant: '不相关' } },
  patent_type: { type: 'choice', instructions: '判断专利保护客体和研发阶段。', criteria: { invention: '发明', utility: '实用新型', design: '外观设计', unclear: '无法判断' } },
  novelty_risk: { type: 'score', instructions: '按新颖性/创造性线索评估复核优先级。', criteria: ['低', '中', '高'] },
  needs_review: { type: 'noul', instructions: '是否需要人工复核后再写入正式标注字段？' },
}, null, 2)

export default function JEVQuickAnalyzeModal({ patents, onClose }: Props) {
  const [questionsText, setQuestionsText] = useState(DEFAULT_QUESTIONS)
  const [running, setRunning] = useState(false)
  const [error, setError] = useState('')
  const [result, setResult] = useState<{ model: string; answers: JsonObject; usage?: JsonObject | null } | null>(null)
  const [template, setTemplate] = useState('general')
  const state = useMemo(() => ({
    records: patents.map(p => ({ id: p.id, title: p.title, abstract: p.abstract || '', claims: p.claims || '' })),
  }), [patents])

  const run = async () => {
    setError('')
    try {
      const questions = JSON.parse(questionsText) as JsonObject
      setRunning(true)
      setResult(await aiService.jevAnalyze({ state, questions }))
    } catch (e) {
      setError(getErrorMessage(e, 'JEV 分析失败，请检查问题 JSON 和 API 配置'))
    } finally { setRunning(false) }
  }

  const applyTemplate = (value: string) => {
    setTemplate(value)
    setQuestionsText(value === 'triage' ? PATENT_TRIAGE_QUESTIONS : DEFAULT_QUESTIONS)
  }

  return <div className="modal-overlay" onClick={onClose}>
    <div className="modal-content" style={{ width: 'min(920px, 94vw)' }} onClick={e => e.stopPropagation()}>
      <div className="modal-header"><div><h3><Icon name="sparkles" size={16} /> JEV 快速标引</h3><p className="modal-subtitle">对选中专利做分类、评分和是否判断；结果先预览，不直接覆盖正式字段。</p></div><button className="icon-button" onClick={onClose} title="关闭"><Icon name="x" /></button></div>
      <div style={{ display: 'grid', gridTemplateColumns: 'minmax(300px, .9fr) minmax(360px, 1.1fr)', gap: 16 }}>
        <div><label style={{ fontSize: 12, color: '#475569' }}>标注模板<select className="form-input" value={template} onChange={e => applyTemplate(e.target.value)} style={{ marginTop: 6, marginBottom: 10 }}><option value="general">通用专利初筛</option><option value="triage">IPC/专利类型/风险分流</option></select></label><label style={{ fontSize: 12, color: '#475569' }}>问题配置（JSON）<textarea className="form-input" rows={16} value={questionsText} onChange={e => { setTemplate('custom'); setQuestionsText(e.target.value) }} style={{ marginTop: 6, fontFamily: 'monospace', fontSize: 12 }} /></label><div style={{ marginTop: 8, color: '#64748b', fontSize: 11 }}>结果默认只做预览，确认后再由人工将标签、分类和复核状态写入正式字段。</div></div>
        <div><div style={{ fontSize: 12, color: '#475569', marginBottom: 6 }}>结构化判断结果</div>{result ? <div style={{ border: '1px solid #e2e8f0', borderRadius: 6, overflow: 'auto', maxHeight: 470 }}>{Object.entries(result.answers || {}).map(([key, value]) => <div key={key} style={{ display: 'grid', gridTemplateColumns: '150px 1fr', gap: 12, padding: '10px 12px', borderBottom: '1px solid #f1f5f9', fontSize: 12 }}><strong>{key}</strong><span>{typeof value === 'object' ? JSON.stringify(value) : String(value)}</span></div>)}</div> : <div style={{ minHeight: 390, padding: 16, background: '#f8fafc', border: '1px dashed #cbd5e1', borderRadius: 6, color: '#64748b', fontSize: 12 }}>运行后显示分类选择、评分、置信度和人工复核建议。</div>}</div>
      </div>
      {error && <div style={{ color: '#b91c1c', background: '#fef2f2', padding: 10, marginTop: 12, borderRadius: 6 }}>{error}</div>}
      <div className="modal-footer"><button className="btn btn-secondary" onClick={onClose}>关闭</button><button className="btn btn-primary" onClick={() => void run()} disabled={running || patents.length === 0}><Icon name="play" size={14} /> {running ? '分析中...' : '运行 JEV 判断'}</button></div>
    </div>
  </div>
}
