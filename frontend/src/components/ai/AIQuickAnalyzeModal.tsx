import { useState, useMemo } from 'react'
import { aiApi } from '../../api'
import type { AITask, CustomField, FieldMeta } from '../../types'
import Icon from '../common/Icon'
import { getErrorMessage } from '../../lib/errors'

interface ExtractionTarget {
  id: string
  name: string
  mode: 'existing' | 'new'
  target_field_key: string
  new_field_name: string
  new_field_type: string
  templateKey?: string
}

interface AIQuickAnalyzeModalProps {
  patentIds: number[]
  fields: FieldMeta[]
  customFields: CustomField[]
  onClose: () => void
  onStarted: (task: AITask) => void
}

const FIELD_TYPE_OPTIONS = [
  { value: 'text', label: '文本' },
  { value: 'textarea', label: '长文本' },
  { value: 'number', label: '数字' },
  { value: 'date', label: '日期' },
  { value: 'select', label: '单选' },
  { value: 'boolean', label: '复选' },
]

const DEFAULT_PROMPT = '请分析以下专利，提取关键信息。'

function isAITemplate(field: CustomField): boolean {
  return field.field_type === 'ai_field' || !!(
    field.ai_config?.ai_enabled || field.ai_config?.prompt_template?.trim()
  )
}

let extractionIdCounter = 0

export default function AIQuickAnalyzeModal({
  patentIds,
  fields,
  customFields,
  onClose,
  onStarted,
}: AIQuickAnalyzeModalProps) {
  const aiTemplates = useMemo(() => customFields.filter(isAITemplate), [customFields])
  const [selectedTemplateKeys, setSelectedTemplateKeys] = useState<Set<string>>(new Set())
  // 默认选中标题和摘要作为输入列
  const [selectedInputs, setSelectedInputs] = useState<Set<string>>(
    () => new Set(['title', 'abstract'].filter(k => fields.some(f => f.key === k)))
  )
  const [prompt, setPrompt] = useState(DEFAULT_PROMPT)
  const [rangeMode, setRangeMode] = useState<'all' | 'range'>('all')
  const [rangeStart, setRangeStart] = useState(1)
  const [rangeEnd, setRangeEnd] = useState(Math.max(1, patentIds.length))
  const [extractions, setExtractions] = useState<ExtractionTarget[]>([
    {
      id: `ext_${++extractionIdCounter}`,
      name: '',
      mode: 'new',
      target_field_key: '',
      new_field_name: '',
      new_field_type: 'text',
    },
  ])
  const [running, setRunning] = useState(false)
  const [error, setError] = useState('')

  const selectedTemplates = useMemo(
    () => aiTemplates.filter(template => selectedTemplateKeys.has(template.key)),
    [aiTemplates, selectedTemplateKeys],
  )

  const targetPatentIds = useMemo(() => {
    if (rangeMode === 'all') return patentIds
    const start = Math.min(Math.max(1, rangeStart), Math.max(1, patentIds.length)) - 1
    const end = Math.min(Math.max(start + 1, rangeEnd), patentIds.length)
    return patentIds.slice(start, end)
  }, [patentIds, rangeEnd, rangeMode, rangeStart])

  const requestPrompt = useMemo(() => {
    const templatePrompts = selectedTemplates
      .map(template => {
        const templatePrompt = template.ai_config?.prompt_template?.trim()
        return templatePrompt ? `【AI 模板：${template.name}】\n${templatePrompt}` : ''
      })
      .filter(Boolean)
    return [...templatePrompts, prompt.trim()].filter(Boolean).join('\n\n')
  }, [prompt, selectedTemplates])

  // 所有可用字段（系统字段 + 自定义字段），用于"写入已有字段"下拉
  const allWritableFields = useMemo(() => {
    // AI 草稿只能写入已注册的自定义字段；系统事实字段仍需人工确认，
    // 避免快速抽取绕过来源和字段类型治理。
    return customFields.filter(f => !['formula', 'attachment', 'link', 'lookup', 'rollup'].includes(f.field_type))
  }, [customFields])

  const toggleInput = (key: string) => {
    setSelectedInputs(prev => {
      const next = new Set(prev)
      if (next.has(key)) next.delete(key)
      else next.add(key)
      return next
    })
  }

  const insertVariable = (key: string) => {
    setPrompt(prev => prev + `{${key}}`)
  }

  const toggleTemplate = (template: CustomField) => {
    const wasSelected = selectedTemplateKeys.has(template.key)
    setSelectedTemplateKeys(previous => {
      const next = new Set(previous)
      if (wasSelected) next.delete(template.key)
      else next.add(template.key)
      return next
    })

    if (!wasSelected) {
      const templateInputs = template.ai_config?.input_fields || []
      setSelectedInputs(previous => new Set([...previous, ...templateInputs]))
      setExtractions(previous => {
        if (previous.some(item => item.target_field_key === template.key)) return previous
        const empty = previous.find(item => !item.name.trim() && !item.target_field_key)
        const target: ExtractionTarget = {
          id: `ext_${++extractionIdCounter}`,
          name: template.name,
          mode: 'existing',
          target_field_key: template.key,
          new_field_name: '',
          new_field_type: 'text',
          templateKey: template.key,
        }
        return empty ? previous.map(item => item.id === empty.id ? target : item) : [...previous, target]
      })
    } else {
      setExtractions(previous => previous.filter(item => item.templateKey !== template.key))
    }
  }

  const updateExtraction = (id: string, patch: Partial<ExtractionTarget>) => {
    setExtractions(prev => prev.map(e => e.id === id ? { ...e, ...patch } : e))
  }

  const addExtraction = () => {
    setExtractions(prev => [...prev, {
      id: `ext_${++extractionIdCounter}`,
      name: '',
      mode: 'new',
      target_field_key: '',
      new_field_name: '',
      new_field_type: 'text',
    }])
  }

  const removeExtraction = (id: string) => {
    setExtractions(prev => prev.length > 1 ? prev.filter(e => e.id !== id) : prev)
  }

  const handleRun = async () => {
    setError('')

    if (targetPatentIds.length === 0) {
      setError('当前没有可分析的专利记录')
      return
    }
    if (selectedInputs.size === 0) {
      setError('请至少选择一个输入列')
      return
    }
    if (!requestPrompt) {
      setError('请填写分析提示词')
      return
    }

    const validExtractions = extractions.filter(e => e.name.trim())
    if (validExtractions.length === 0) {
      setError('请至少配置一个抽取目标（填写抽取名称）')
      return
    }

    // 校验每个抽取目标
    for (const ext of validExtractions) {
      if (ext.mode === 'existing' && !ext.target_field_key) {
        setError(`抽取目标"${ext.name}"未选择目标字段`)
        return
      }
      if (ext.mode === 'new' && !ext.new_field_name.trim()) {
        setError(`抽取目标"${ext.name}"未填写新字段名称`)
        return
      }
    }

    setRunning(true)
    try {
      const task = await aiApi.quickAnalyze({
        patent_ids: targetPatentIds,
        input_fields: Array.from(selectedInputs),
        prompt: requestPrompt,
        extractions: validExtractions.map(e => ({
          name: e.name.trim(),
          target_field_key: e.mode === 'existing' ? e.target_field_key : undefined,
          new_field_name: e.mode === 'new' ? e.new_field_name.trim() : undefined,
          new_field_type: e.mode === 'new' ? e.new_field_type : undefined,
        })),
      })
      onStarted(task)
    } catch (err: unknown) {
      setError(getErrorMessage(err, '启动 AI 分析失败'))
    } finally {
      setRunning(false)
    }
  }

  return (
    <div
      style={{
        position: 'fixed', top: 0, left: 0, right: 0, bottom: 0,
        background: 'rgba(0,0,0,0.45)', display: 'flex',
        alignItems: 'center', justifyContent: 'center', zIndex: 1000,
      }}
      onClick={onClose}
    >
      <div
        style={{
          background: '#fff', borderRadius: 12, width: 760, maxHeight: '90vh',
          overflow: 'auto', boxShadow: '0 20px 60px rgba(0,0,0,0.15)',
          display: 'flex', flexDirection: 'column',
        }}
        onClick={e => e.stopPropagation()}
      >
        {/* Header */}
        <div style={{
          padding: '16px 20px', borderBottom: '1px solid #e5e7eb',
          display: 'flex', justifyContent: 'space-between', alignItems: 'center',
        }}>
          <h3 style={{ fontSize: 17, fontWeight: 700, display: 'flex', alignItems: 'center', gap: 8 }}>
            <Icon name="sparkles" size={18} /> AI 快速分析
          </h3>
          <button onClick={onClose} style={{ border: 'none', background: 'none', cursor: 'pointer', fontSize: 20, color: '#9ca3af' }}>×</button>
        </div>

        <div style={{ padding: '16px 20px', display: 'flex', flexDirection: 'column', gap: 16 }}>
          {/* 1. 处理范围 */}
          <div>
            <label style={{ fontSize: 14, fontWeight: 600, marginBottom: 8, display: 'block' }}>
              ① 分析记录范围
            </label>
            <div style={{ padding: '8px 12px', background: '#eff6ff', borderRadius: 8, fontSize: 13, color: '#1e40af', marginBottom: 8 }}>
              当前可处理候选记录 <strong>{patentIds.length}</strong> 条，结果会自动回填到所选目标字段。
            </div>
            <div style={{ display: 'flex', gap: 8, alignItems: 'center', flexWrap: 'wrap' }}>
              <label style={{ display: 'inline-flex', alignItems: 'center', gap: 5, fontSize: 13, cursor: 'pointer' }}>
                <input type="radio" checked={rangeMode === 'all'} onChange={() => setRangeMode('all')} />
                全部候选记录
              </label>
              <label style={{ display: 'inline-flex', alignItems: 'center', gap: 5, fontSize: 13, cursor: 'pointer' }}>
                <input type="radio" checked={rangeMode === 'range'} onChange={() => setRangeMode('range')} />
                指定条数范围
              </label>
              {rangeMode === 'range' && (
                <div style={{ display: 'inline-flex', alignItems: 'center', gap: 5, fontSize: 12, color: '#475569' }}>
                  第
                  <input className="form-input" type="number" min={1} max={Math.max(1, patentIds.length)} value={rangeStart} onChange={event => setRangeStart(Number(event.target.value) || 1)} style={{ width: 68, padding: '4px 6px' }} />
                  条至
                  <input className="form-input" type="number" min={1} max={Math.max(1, patentIds.length)} value={rangeEnd} onChange={event => setRangeEnd(Number(event.target.value) || 1)} style={{ width: 68, padding: '4px 6px' }} />
                  条
                </div>
              )}
              <span style={{ fontSize: 12, color: '#64748b' }}>本次将分析 {targetPatentIds.length} 条</span>
            </div>
          </div>

          {/* 2. AI 模板 */}
          <div>
            <label style={{ fontSize: 14, fontWeight: 600, marginBottom: 8, display: 'block' }}>
              ② 选择 AI 模板 <span style={{ color: '#6b7280', fontWeight: 400 }}>（可多选，自动带出抽取目标、提示词和输入列）</span>
            </label>
            {aiTemplates.length === 0 ? (
              <div style={{ padding: '10px 12px', border: '1px dashed #cbd5e1', borderRadius: 8, color: '#64748b', fontSize: 12 }}>
                暂无可复用模板。你仍可以直接配置抽取目标；需要长期复用时，请到 AI 预置字段管理创建模板。
              </div>
            ) : (
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))', gap: 8, maxHeight: 180, overflowY: 'auto' }}>
                {aiTemplates.map(template => {
                  const checked = selectedTemplateKeys.has(template.key)
                  return (
                    <label key={template.key} style={{ display: 'flex', gap: 8, alignItems: 'flex-start', padding: '9px 10px', border: `1px solid ${checked ? '#0f766e' : '#e2e8f0'}`, borderRadius: 8, background: checked ? '#f0fdfa' : '#fff', cursor: 'pointer' }}>
                      <input type="checkbox" checked={checked} onChange={() => toggleTemplate(template)} style={{ marginTop: 2 }} />
                      <span style={{ minWidth: 0 }}>
                        <strong style={{ display: 'block', fontSize: 13, color: '#1f2937' }}>{template.name}</strong>
                        <span style={{ display: 'block', marginTop: 2, fontSize: 11, color: '#64748b', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                          {template.description || template.ai_config?.input_fields?.join('、') || '按模板配置执行'}
                        </span>
                      </span>
                    </label>
                  )
                })}
              </div>
            )}
          </div>

          {/* 3. 输入列选择 */}
          <div>
            <label style={{ fontSize: 14, fontWeight: 600, marginBottom: 8, display: 'block' }}>
              ③ 选择输入列 <span style={{ color: '#6b7280', fontWeight: 400 }}>（勾选要传给 AI 的列内容，模板会自动勾选其配置范围）</span>
            </label>
            <div style={{
              maxHeight: 120, overflow: 'auto', border: '1px solid #e5e7eb',
              borderRadius: 8, padding: 8,
            }}>
              {fields.map(f => (
                <label key={f.key} style={{
                  display: 'inline-flex', alignItems: 'center', gap: 4,
                  marginRight: 8, marginBottom: 4, fontSize: 13, cursor: 'pointer',
                }}>
                  <input
                    type="checkbox"
                    checked={selectedInputs.has(f.key)}
                    onChange={() => toggleInput(f.key)}
                    style={{ margin: 0 }}
                  />
                  {f.name}
                </label>
              ))}
            </div>
          </div>

          {/* 4. 提示词 */}
          <div>
            <label style={{ fontSize: 14, fontWeight: 600, marginBottom: 8, display: 'block' }}>
              ④ 补充提示词 <span style={{ color: '#dc2626' }}>*</span>
            </label>
            <div style={{ marginBottom: 6, fontSize: 12, color: '#6b7280' }}>
              模板提示词会自动合并发送；这里填写本次分析的补充要求，也可点击列名插入变量：
            </div>
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: 4, marginBottom: 8 }}>
              {fields.filter(f => f.key !== 'id').slice(0, 12).map(f => (
                <button
                  key={f.key}
                  type="button"
                  className="btn btn-xs btn-ghost"
                  style={{ fontSize: 11, padding: '2px 8px' }}
                  onClick={() => insertVariable(f.key)}
                >
                  {`{${f.key}}`}
                </button>
              ))}
            </div>
            <textarea
              className="form-input"
              style={{ minHeight: 100, fontFamily: 'monospace', fontSize: 13 }}
              value={prompt}
              onChange={e => setPrompt(e.target.value)}
              placeholder="例如：请分析以下专利的技术方案和风险等级。&#10;标题：{title}&#10;摘要：{abstract}"
            />
            {selectedTemplates.length > 0 && (
              <details style={{ marginTop: 6, fontSize: 11, color: '#64748b' }}>
                <summary style={{ cursor: 'pointer' }}>查看已合并的模板提示词（{selectedTemplates.length} 个）</summary>
                <pre style={{ margin: '6px 0 0', padding: 8, background: '#f8fafc', border: '1px solid #e2e8f0', borderRadius: 6, whiteSpace: 'pre-wrap', maxHeight: 140, overflow: 'auto' }}>{requestPrompt}</pre>
              </details>
            )}
          </div>

          {/* 5. 抽取目标 */}
          <div>
            <label style={{ fontSize: 14, fontWeight: 600, marginBottom: 8, display: 'block' }}>
              ⑤ 抽取目标 <span style={{ color: '#6b7280', fontWeight: 400 }}>（定义要抽取几个内容，以及填到哪些字段）</span>
            </label>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
              {extractions.map((ext, idx) => (
                <div key={ext.id} style={{
                  border: '1px solid #e5e7eb', borderRadius: 8, padding: 10,
                  display: 'flex', flexDirection: 'column', gap: 8,
                }}>
                  <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
                    <span style={{ fontSize: 12, color: '#9ca3af', minWidth: 20 }}>{idx + 1}.</span>
                    <input
                      className="form-input"
                      style={{ flex: 1, fontSize: 13 }}
                      placeholder="抽取名称（如：技术问题、关键词、风险等级）"
                      value={ext.name}
                      onChange={e => updateExtraction(ext.id, { name: e.target.value })}
                    />
                    <button
                      type="button"
                      className="btn btn-xs btn-ghost"
                      onClick={() => removeExtraction(ext.id)}
                      disabled={extractions.length <= 1}
                      style={{ color: '#dc2626', opacity: extractions.length <= 1 ? 0.4 : 1 }}
                    >
                      删除
                    </button>
                  </div>
                  <div style={{ display: 'flex', gap: 8, alignItems: 'center', paddingLeft: 28 }}>
                    <select
                      className="form-input"
                      style={{ width: 'auto', fontSize: 12 }}
                      value={ext.mode}
                      onChange={e => updateExtraction(ext.id, { mode: e.target.value as 'existing' | 'new' })}
                    >
                      <option value="new">新建字段</option>
                      <option value="existing">写入已有字段</option>
                    </select>
                    {ext.mode === 'existing' ? (
                      <select
                        className="form-input"
                        style={{ flex: 1, fontSize: 12 }}
                        value={ext.target_field_key}
                        onChange={e => updateExtraction(ext.id, { target_field_key: e.target.value })}
                      >
                        <option value="">选择字段...</option>
                        {allWritableFields.map(f => (
                          <option key={f.key} value={f.key}>{f.name} ({f.key})</option>
                        ))}
                      </select>
                    ) : (
                      <div style={{ display: 'flex', gap: 8, flex: 1 }}>
                        <input
                          className="form-input"
                          style={{ flex: 1, fontSize: 12 }}
                          placeholder="新字段名称"
                          value={ext.new_field_name}
                          onChange={e => updateExtraction(ext.id, { new_field_name: e.target.value })}
                        />
                        <select
                          className="form-input"
                          style={{ width: 'auto', fontSize: 12 }}
                          value={ext.new_field_type}
                          onChange={e => updateExtraction(ext.id, { new_field_type: e.target.value })}
                        >
                          {FIELD_TYPE_OPTIONS.map(o => (
                            <option key={o.value} value={o.value}>{o.label}</option>
                          ))}
                        </select>
                      </div>
                    )}
                  </div>
                </div>
              ))}
              <button
                type="button"
                className="btn btn-sm btn-ghost"
                onClick={addExtraction}
                style={{ alignSelf: 'flex-start', color: '#2563eb' }}
              >
                + 添加抽取目标
              </button>
            </div>
          </div>

          {/* Error */}
          {error && (
            <div style={{ padding: '8px 12px', background: '#fef2f2', borderRadius: 8, fontSize: 13, color: '#dc2626' }}>
              {error}
            </div>
          )}
        </div>

        {/* Footer */}
        <div style={{
          padding: '12px 20px', borderTop: '1px solid #e5e7eb',
          display: 'flex', justifyContent: 'flex-end', gap: 8,
        }}>
          <button className="btn btn-ghost" onClick={onClose}>取消</button>
          <button
            className="btn btn-primary"
            onClick={() => void handleRun()}
            disabled={running}
          >
            <Icon name="play" size={14} /> {running ? '启动中...' : `运行 AI 分析（${targetPatentIds.length} 条）`}
          </button>
        </div>
      </div>
    </div>
  )
}
