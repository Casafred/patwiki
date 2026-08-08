import { useCallback, useEffect, useState } from 'react'
import { patentShareApi } from '../../api'
import type { PublicPatent, PublicPatentShare } from '../../types'
import { getErrorMessage } from '../../lib/errors'

interface PublicPatentSharePageProps {
  token: string
}

const statusLabels: Record<string, string> = {
  unknown: '未知', pending: '待审', published: '已公开', examining: '实审中',
  granted: '已授权', rejected: '驳回', withdrawn: '撤回', deemed_withdrawn: '视撤',
  expired: '终止', abandoned: '放弃',
}

const typeLabels: Record<string, string> = {
  invention: '发明', utility_model: '实用新型', design: '外观设计', pct: 'PCT',
}

function readableDate(value?: string | null): string {
  return value ? new Date(value).toLocaleDateString('zh-CN') : '-'
}

function readableValue(value?: string | null): string {
  return value || '-'
}

function InfoItem({ label, value, mono = false }: { label: string; value?: string | null; mono?: boolean }) {
  return (
    <div style={{ padding: '10px 0', borderBottom: '1px solid #e2e8f0' }}>
      <div style={{ color: '#94a3b8', fontSize: 11, marginBottom: 4 }}>{label}</div>
      <div style={{ color: '#334155', fontSize: 13, wordBreak: 'break-word', fontFamily: mono ? 'ui-monospace, SFMono-Regular, Menlo, monospace' : undefined }}>
        {readableValue(value)}
      </div>
    </div>
  )
}

function TopicSection({ title, value }: { title: string; value?: string | null }) {
  if (!value) return null
  return (
    <section style={{ padding: '22px 0', borderBottom: '1px solid #e2e8f0' }}>
      <h2 style={{ margin: '0 0 10px', color: '#0f172a', fontSize: 17, fontWeight: 650 }}>{title}</h2>
      <div style={{ color: '#334155', fontSize: 14, lineHeight: 1.85, whiteSpace: 'pre-wrap' }}>{value}</div>
    </section>
  )
}

export default function PublicPatentSharePage({ token }: PublicPatentSharePageProps) {
  const [data, setData] = useState<PublicPatentShare | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const loadShare = useCallback(async () => {
    setLoading(true)
    try {
      setData(await patentShareApi.getPublic(token))
      setError(null)
    } catch (reason: unknown) {
      setError(getErrorMessage(reason, '分享链接无效或已失效'))
    } finally {
      setLoading(false)
    }
  }, [token])

  useEffect(() => {
    // The callback synchronizes the public page with the remote share payload.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    void loadShare()
  }, [loadShare])

  if (loading) {
    return <div className="public-share-page"><div className="public-share-state">加载技术主题...</div></div>
  }

  if (error || !data) {
    return (
      <div className="public-share-page">
        <div className="public-share-state">
          <div style={{ color: '#0f172a', fontSize: 20, fontWeight: 650 }}>无法打开分享页面</div>
          <div style={{ marginTop: 8, color: '#64748b', fontSize: 13 }}>{error || '页面不存在'}</div>
        </div>
      </div>
    )
  }

  const patent: PublicPatent = data.patent
  const metadata = [
    { label: '申请号', value: patent.application_number, mono: true },
    { label: '公开号', value: patent.publication_number, mono: true },
    { label: '授权号', value: patent.grant_number, mono: true },
    { label: '申请人', value: patent.applicant },
    { label: '发明人', value: patent.inventor },
    { label: '申请日', value: readableDate(patent.filing_date) },
    { label: '公开日', value: readableDate(patent.publication_date) },
    { label: '法律状态', value: statusLabels[patent.legal_status || ''] || patent.legal_status },
    { label: '专利类型', value: typeLabels[patent.patent_type || ''] || patent.patent_type },
    { label: '主 IPC', value: patent.ipc_main, mono: true },
  ]

  return (
    <div className="public-share-page">
      <header className="public-share-header">
        <div className="public-share-brand">PatWiki <span>技术主题</span></div>
        <div style={{ color: '#94a3b8', fontSize: 12 }}>只读分享 · 访问 {data.share.access_count} 次</div>
      </header>
      <main className="public-share-layout">
        <article className="public-share-main">
          <div style={{ paddingBottom: 24, borderBottom: '1px solid #cbd5e1' }}>
            <div style={{ color: '#2563eb', fontSize: 12, fontWeight: 650, letterSpacing: '0.04em' }}>PATENT TECHNOLOGY BRIEF</div>
            <h1 style={{ margin: '10px 0 12px', color: '#0f172a', fontSize: 'clamp(26px, 4vw, 42px)', lineHeight: 1.22, fontWeight: 700 }}>
              {patent.title}
            </h1>
            <div style={{ color: '#64748b', fontSize: 13 }}>
              {patent.category || patent.subcategory || patent.module || '专利技术主题'}
            </div>
          </div>

          <TopicSection title="摘要" value={patent.abstract} />
          <TopicSection title="技术问题" value={patent.technical_problem} />
          <TopicSection title="技术方案" value={patent.technical_solution} />
          <TopicSection title="技术效果" value={patent.technical_effect} />
          <TopicSection title="保护范围" value={patent.scope_description} />
          <TopicSection title="权利要求" value={patent.claims} />

          {!patent.abstract && !patent.technical_problem && !patent.technical_solution && !patent.technical_effect && !patent.scope_description && !patent.claims && (
            <div style={{ padding: '40px 0', color: '#64748b', fontSize: 14 }}>这条专利还没有可分享的技术主题内容。</div>
          )}
        </article>

        <aside className="public-share-sidebar">
          <section>
            <h2 style={{ margin: '0 0 4px', color: '#0f172a', fontSize: 15 }}>著录信息</h2>
            {metadata.map(item => <InfoItem key={item.label} {...item} />)}
          </section>
          {(patent.projects.length > 0 || patent.tags.length > 0) && (
            <section style={{ marginTop: 28 }}>
              <h2 style={{ margin: '0 0 12px', color: '#0f172a', fontSize: 15 }}>关联主题</h2>
              {patent.projects.length > 0 && (
                <div style={{ marginBottom: 12 }}>
                  <div style={{ color: '#94a3b8', fontSize: 11, marginBottom: 6 }}>项目</div>
                  <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>
                    {patent.projects.map(project => <span key={project.id} className="public-share-chip">{project.name}</span>)}
                  </div>
                </div>
              )}
              {patent.tags.length > 0 && (
                <div>
                  <div style={{ color: '#94a3b8', fontSize: 11, marginBottom: 6 }}>标签</div>
                  <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>
                    {patent.tags.map(tag => <span key={tag.id} className="public-share-chip" style={{ borderColor: tag.color || '#cbd5e1' }}>{tag.name}</span>)}
                  </div>
                </div>
              )}
            </section>
          )}
        </aside>
      </main>
    </div>
  )
}
