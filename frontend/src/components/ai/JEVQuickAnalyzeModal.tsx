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

export default function JEVQuickAnalyzeModal({ patents, onClose }: Props) {
  const [questionsText, setQuestionsText] = useState(DEFAULT_QUESTIONS)
  const [running, setRunning] = useState(false)
  const [error, setError] = useState('')
  const [result, setResult] = useState<{ model: string; answers: JsonObject; usage?: JsonObject | null } | null>(null)
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

  return <div className="modal-overlay" onClick={onClose}>
    <div className="modal-content" style={{ width: 'min(920px, 94vw)' }} onClick={e => e.stopPropagation()}>
      <div className="modal-header"><div><h3><Icon name="sparkles" size={16} /> JEV 快速标引</h3><p className="modal-subtitle">对选中专利做分类、评分和是否判断；结果先预览，不直接覆盖正式字段。</p></div><button className="icon-button" onClick={onClose} title="关闭"><Icon name="x" /></button></div>
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16 }}>
        <label style={{ fontSize: 12, color: '#475569' }}>问题配置（JSON）<textarea className="form-input" rows={18} value={questionsText} onChange={e => setQuestionsText(e.target.value)} style={{ marginTop: 6, fontFamily: 'monospace', fontSize: 12 }} /></label>
        <div><div style={{ fontSize: 12, color: '#475569', marginBottom: 6 }}>判断结果</div><pre style={{ minHeight: 390, maxHeight: 520, overflow: 'auto', margin: 0, padding: 12, background: '#f8fafc', border: '1px solid #e2e8f0', borderRadius: 6, fontSize: 12 }}>{result ? JSON.stringify(result, null, 2) : '运行后显示 JEV 的 choice / score / noul、置信度和概率。'}</pre></div>
      </div>
      {error && <div style={{ color: '#b91c1c', background: '#fef2f2', padding: 10, marginTop: 12, borderRadius: 6 }}>{error}</div>}
      <div className="modal-footer"><button className="btn btn-secondary" onClick={onClose}>关闭</button><button className="btn btn-primary" onClick={() => void run()} disabled={running || patents.length === 0}><Icon name="play" size={14} /> {running ? '分析中...' : '运行 JEV 判断'}</button></div>
    </div>
  </div>
}
