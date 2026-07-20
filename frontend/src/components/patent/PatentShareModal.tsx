import { useState, useEffect, useMemo } from 'react'
import { customFieldApi } from '../../api'
import type { Patent, CustomField } from '../../types'

interface PatentShareModalProps {
  patent: Patent
  onClose: () => void
}

/**
 * P2-4：单专利 wiki 分享页
 * - 以 Wiki 风格展示专利全部字段（系统字段 + 自定义字段 + AI 字段）
 * - 支持复制为 Markdown / 打印 / 浏览器另存为 PDF
 * - 不依赖后端新端点：直接复用 patent 对象与 customFieldApi
 */
export default function PatentShareModal({ patent, onClose }: PatentShareModalProps) {
  const [fields, setFields] = useState<CustomField[]>([])
  const [loading, setLoading] = useState(true)
  const [copied, setCopied] = useState(false)

  useEffect(() => {
    let mounted = true
    customFieldApi.list().then(list => {
      if (mounted) {
        setFields(list)
        setLoading(false)
      }
    }).catch(() => {
      if (mounted) setLoading(false)
    })
    return () => { mounted = false }
  }, [])

  // 系统字段分组（用于 wiki 风格展示）
  const sections = useMemo(() => {
    const aiFields = fields.filter(f => f.field_type === ('ai_field' as any) || (f.ai_config && (f.ai_config as any)?.ai_enabled))
    const customFieldsNonAi = fields.filter(f => !(f.field_type === ('ai_field' as any) || (f.ai_config && (f.ai_config as any)?.ai_enabled)))

    return [
      {
        title: '基础著录',
        items: [
          ['标题', patent.title],
          ['申请号', patent.application_number],
          ['公开号', patent.publication_number],
          ['授权号', patent.grant_number],
          ['申请日', formatDate(patent.filing_date)],
          ['公开日', formatDate(patent.publication_date)],
          ['授权日', formatDate(patent.grant_date)],
          ['优先权日', formatDate(patent.priority_date)],
          ['优先权号', patent.priority_number],
          ['优先权国家', patent.priority_country],
          ['国家', patent.country],
          ['专利类型', patent.patent_type],
          ['法律状态', patent.legal_status],
          ['申请人', patent.applicant],
          ['发明人', patent.inventor],
          ['专利权人', patent.assignee],
          ['代理机构', patent.agent],
        ].filter(([, v]) => v != null && v !== ''),
      },
      {
        title: '技术分类',
        items: [
          ['IPC 主分类', patent.ipc_main],
          ['全部 IPC', patent.ipc_all],
          ['CPC 主分类', patent.cpc_main],
          ['全部 CPC', patent.cpc_all],
          ['技术分类', patent.category],
          ['子分类', patent.subcategory],
        ].filter(([, v]) => v != null && v !== ''),
      },
      {
        title: '技术内容',
        items: [
          ['摘要', patent.abstract],
          ['技术问题', patent.technical_problem],
          ['技术方案', patent.technical_solution],
          ['技术效果', patent.technical_effect],
          ['功能模块', patent.module],
          ['权利要求', patent.claims],
        ].filter(([, v]) => v != null && v !== ''),
      },
      {
        title: '风险与应用',
        items: [
          ['是否有风险', patent.has_risk ? '是' : '否'],
          ['风险等级', patent.risk_level],
          ['风险描述', patent.risk_description],
          ['应用状态', patent.application_status],
          ['保护范围', patent.scope_description],
          ['备注', patent.notes],
        ].filter(([, v]) => v != null && v !== ''),
      },
      ...(customFieldsNonAi.length > 0 ? [{
        title: '自定义字段',
        items: customFieldsNonAi.map(f => [f.name, (patent.custom_fields || {})[f.key] ?? '']) as [string, any][],
      }] : []),
      ...(aiFields.length > 0 ? [{
        title: 'AI 抽取字段',
        items: aiFields.map(f => [f.name, (patent.ai_fields || {})[f.key] ?? '']) as [string, any][],
      }] : []),
    ].filter(s => s.items.length > 0)
  }, [patent, fields])

  const markdown = useMemo(() => {
    const lines: string[] = []
    lines.push(`# ${patent.title || '未命名专利'}`)
    lines.push('')
    lines.push(`> 申请号：${patent.application_number || '-'} · 公开号：${patent.publication_number || '-'} · 申请日：${formatDate(patent.filing_date) || '-'}`)
    lines.push('')
    for (const sec of sections) {
      lines.push(`## ${sec.title}`)
      lines.push('')
      for (const [k, v] of sec.items) {
        const value = typeof v === 'string' ? v : String(v ?? '')
        if (value.includes('\n') || value.length > 100) {
          lines.push(`**${k}**：`)
          lines.push('')
          lines.push(value)
          lines.push('')
        } else {
          lines.push(`- **${k}**：${value}`)
        }
      }
      lines.push('')
    }
    return lines.join('\n')
  }, [patent, sections])

  const handleCopy = async () => {
    try {
      await navigator.clipboard.writeText(markdown)
      setCopied(true)
      setTimeout(() => setCopied(false), 2000)
    } catch {
      alert('复制失败，请手动选择文本复制')
    }
  }

  const handlePrint = () => {
    const printWindow = window.open('', '_blank', 'width=900,height=700')
    if (!printWindow) {
      alert('请允许弹窗以使用打印功能')
      return
    }
    printWindow.document.write(`
<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<title>${escapeHtml(patent.title || '专利分享')}</title>
<style>
  body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', 'Microsoft YaHei', sans-serif; line-height: 1.7; color: #1f2937; max-width: 800px; margin: 40px auto; padding: 0 24px; }
  h1 { font-size: 24px; border-bottom: 2px solid #1e40af; padding-bottom: 8px; color: #1e40af; }
  h2 { font-size: 17px; margin-top: 24px; color: #1e40af; border-left: 3px solid #1e40af; padding-left: 8px; }
  .meta { color: #64748b; font-size: 13px; margin: 8px 0 16px; }
  .item { display: flex; padding: 4px 0; border-bottom: 1px dashed #e5e7eb; font-size: 14px; }
  .item-key { width: 140px; color: #64748b; flex-shrink: 0; font-weight: 500; }
  .item-val { flex: 1; word-break: break-all; white-space: pre-wrap; }
  .long-val { padding: 8px 12px; background: #f8fafc; border-left: 3px solid #cbd5e1; margin: 4px 0; font-size: 13px; white-space: pre-wrap; }
  @media print { body { margin: 0; padding: 16px; } }
</style>
</head>
<body>
  <h1>${escapeHtml(patent.title || '未命名专利')}</h1>
  <div class="meta">申请号：${escapeHtml(patent.application_number || '-')} · 公开号：${escapeHtml(patent.publication_number || '-')} · 申请日：${escapeHtml(formatDate(patent.filing_date) || '-')}</div>
  ${sections.map(sec => `
    <h2>${escapeHtml(sec.title)}</h2>
    ${sec.items.map(([k, v]) => {
      const keyStr = String(k ?? '')
      const value = typeof v === 'string' ? v : String(v ?? '')
      if (value.includes('\n') || value.length > 100) {
        return `<div class="item"><div class="item-key">${escapeHtml(keyStr)}</div><div class="item-val"><div class="long-val">${escapeHtml(value)}</div></div></div>`
      }
      return `<div class="item"><div class="item-key">${escapeHtml(keyStr)}</div><div class="item-val">${escapeHtml(value || '-')}</div></div>`
    }).join('')}
  `).join('')}
</body>
</html>
    `)
    printWindow.document.close()
    printWindow.focus()
    setTimeout(() => printWindow.print(), 300)
  }

  return (
    <div
      onClick={(e) => { if (e.target === e.currentTarget) onClose() }}
      style={{
        position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.5)',
        display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 100,
      }}
    >
      <div style={{
        background: 'white', borderRadius: 12, width: '90%', maxWidth: 900, maxHeight: '90vh',
        display: 'flex', flexDirection: 'column', boxShadow: '0 25px 50px -12px rgba(0,0,0,0.25)',
      }}>
        <div style={{ padding: '16px 20px', borderBottom: '1px solid #e2e8f0', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <div>
            <h3 style={{ margin: 0, fontSize: 16, fontWeight: 600 }}>Wiki 风格分享</h3>
            <p style={{ margin: '4px 0 0 0', fontSize: 12, color: '#64748b' }}>
              可复制 Markdown、打印或另存为 PDF
            </p>
          </div>
          <div style={{ display: 'flex', gap: 8 }}>
            <button className="btn btn-secondary" onClick={handleCopy} disabled={loading}>
              {copied ? '✓ 已复制' : '复制 Markdown'}
            </button>
            <button className="btn btn-primary" onClick={handlePrint} disabled={loading}>打印 / PDF</button>
            <button onClick={onClose} style={{ background: 'none', border: 'none', fontSize: 20, cursor: 'pointer', color: '#94a3b8', marginLeft: 4 }}>×</button>
          </div>
        </div>

        <div style={{ flex: 1, overflow: 'auto', padding: 24, background: '#fafbfc' }}>
          {loading ? (
            <div style={{ textAlign: 'center', padding: 40, color: '#94a3b8' }}>加载字段中...</div>
          ) : (
            <div style={{ background: 'white', padding: 32, borderRadius: 8, border: '1px solid #e2e8f0', maxWidth: 720, margin: '0 auto' }}>
              {/* Wiki 风格内容预览 */}
              <h1 style={{ fontSize: 24, margin: '0 0 8px 0', color: '#1e40af', borderBottom: '2px solid #1e40af', paddingBottom: 8 }}>
                {patent.title || '未命名专利'}
              </h1>
              <div style={{ color: '#64748b', fontSize: 13, margin: '8px 0 16px' }}>
                申请号：{patent.application_number || '-'} · 公开号：{patent.publication_number || '-'} · 申请日：{formatDate(patent.filing_date) || '-'}
              </div>
              {sections.map((sec, i) => (
                <div key={i} style={{ marginTop: 20 }}>
                  <h2 style={{
                    fontSize: 16, margin: '0 0 8px 0', color: '#1e40af',
                    borderLeft: '3px solid #1e40af', paddingLeft: 8,
                  }}>{sec.title}</h2>
                  {sec.items.map(([k, v], j) => {
                    const value = typeof v === 'string' ? v : String(v ?? '')
                    const isLong = value.includes('\n') || value.length > 100
                    return (
                      <div key={j} style={{ display: 'flex', padding: '4px 0', borderBottom: '1px dashed #e5e7eb', fontSize: 13 }}>
                        <div style={{ width: 140, color: '#64748b', flexShrink: 0, fontWeight: 500 }}>{k}</div>
                        <div style={{ flex: 1, wordBreak: 'break-all', whiteSpace: 'pre-wrap', color: '#1f2937' }}>
                          {isLong ? (
                            <div style={{
                              padding: '8px 12px', background: '#f8fafc',
                              borderLeft: '3px solid #cbd5e1', margin: '4px 0',
                              fontSize: 12,
                            }}>{value || '-'}</div>
                          ) : (value || '-')}
                        </div>
                      </div>
                    )
                  })}
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  )
}

function formatDate(d: any): string {
  if (!d) return ''
  if (typeof d === 'string') return d.split('T')[0]
  try {
    return new Date(d).toISOString().split('T')[0]
  } catch {
    return String(d)
  }
}

function escapeHtml(s: string): string {
  if (s == null) return ''
  return String(s)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;')
}
