import { useCallback, useEffect, useMemo, useState } from 'react'
import { projectRiskService } from '../../services'
import type { Patent, Project, ProjectSolutionVersion, RiskCase } from '../../types'
import { getErrorMessage } from '../../lib/errors'

const STAGES = ['TR1', 'TR2', 'TR3', 'TR4', 'TR5']

interface Props {
  patent: Patent
  projects: Project[]
}

interface SolutionForm {
  projectId: string
  name: string
  stage: string
  sourceType: string
  sourceDescription: string
  changeSummary: string
  featureName: string
  afterDescription: string
  impactDescription: string
  regions: string
}

interface RiskForm {
  title: string
  triggerReason: string
  currentGate: string
  solutionVersionId: string
  regions: string
}

interface AssessmentForm {
  stage: string
  solutionVersionId: string
  jurisdiction: string
  preliminary: string
  analysis: string
  discussion: string
  leadership: string
  decision: string
  level: string
  gateImpact: string
  basis: string
  mitigation: string
  assessedBy: string
  confirmedBy: string
  decidedBy: string
}

const emptySolutionForm = (projectId = ''): SolutionForm => ({
  projectId,
  name: '',
  stage: 'TR1',
  sourceType: 'manual',
  sourceDescription: '',
  changeSummary: '',
  featureName: '',
  afterDescription: '',
  impactDescription: '',
  regions: '',
})

const emptyRiskForm: RiskForm = {
  title: '',
  triggerReason: '',
  currentGate: 'TR1',
  solutionVersionId: '',
  regions: '',
}

const emptyAssessmentForm: AssessmentForm = {
  stage: 'TR1',
  solutionVersionId: '',
  jurisdiction: 'US',
  preliminary: '',
  analysis: '',
  discussion: '',
  leadership: '',
  decision: 'pending',
  level: 'none',
  gateImpact: 'unknown',
  basis: '',
  mitigation: '',
  assessedBy: '',
  confirmedBy: '',
  decidedBy: '',
}

function parseRegions(value: string) {
  return value
    .split(/[,，;；\n]/)
    .map(item => item.trim())
    .filter(Boolean)
    .map(region => ({ region_code: region, region_name: region }))
}

function dateTime(value?: string | null) {
  return value ? new Date(value).toLocaleString('zh-CN') : '-'
}

export default function ProjectRiskContextPanel({ patent, projects }: Props) {
  const linkedProjectIds = useMemo(() => new Set((patent.projects || []).map(project => project.id)), [patent.projects])
  const linkedProjects = useMemo(() => projects.filter(project => linkedProjectIds.has(project.id)), [linkedProjectIds, projects])
  const [versionsByProject, setVersionsByProject] = useState<Record<number, ProjectSolutionVersion[]>>({})
  const [riskCases, setRiskCases] = useState<RiskCase[]>([])
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [showSolutionForm, setShowSolutionForm] = useState(false)
  const [showRiskForm, setShowRiskForm] = useState(false)
  const [assessmentCaseId, setAssessmentCaseId] = useState<number | null>(null)
  const [reviewCaseId, setReviewCaseId] = useState<number | null>(null)
  const [solutionForm, setSolutionForm] = useState<SolutionForm>(emptySolutionForm())
  const [riskForm, setRiskForm] = useState<RiskForm>(emptyRiskForm)
  const [assessmentForm, setAssessmentForm] = useState<AssessmentForm>(emptyAssessmentForm)

  const allVersions = useMemo(
    () => Object.values(versionsByProject).flat().sort((a, b) => b.id - a.id),
    [versionsByProject],
  )

  const load = useCallback(async () => {
    if (!patent.database_id) {
      setLoading(false)
      return
    }
    setLoading(true)
    setError(null)
    try {
      const [versionEntries, cases] = await Promise.all([
        Promise.all(linkedProjects.map(async project => [project.id, await projectRiskService.listSolutionVersions(project.id, patent.database_id)] as const)),
        projectRiskService.listRiskCases(patent.database_id, patent.id),
      ])
      setVersionsByProject(Object.fromEntries(versionEntries))
      setRiskCases(cases)
    } catch (cause: unknown) {
      setError(getErrorMessage(cause, '项目方案或风险信息加载失败'))
    } finally {
      setLoading(false)
    }
  }, [linkedProjects, patent.database_id, patent.id])

  // Loading is an external request triggered by the current patent context.
  // eslint-disable-next-line react-hooks/set-state-in-effect
  useEffect(() => { void load() }, [load])

  const submitSolution = async () => {
    if (!patent.database_id || !solutionForm.projectId || !solutionForm.name.trim()) return
    setSaving(true)
    setError(null)
    try {
      await projectRiskService.createSolutionVersion(Number(solutionForm.projectId), {
        database_id: patent.database_id,
        name: solutionForm.name.trim(),
        project_stage: solutionForm.stage,
        source_type: solutionForm.sourceType,
        source_description: solutionForm.sourceDescription.trim() || undefined,
        change_summary: solutionForm.changeSummary.trim() || undefined,
        changes: solutionForm.featureName.trim() ? [{
          feature_name: solutionForm.featureName.trim(),
          after_description: solutionForm.afterDescription.trim() || undefined,
          impact_description: solutionForm.impactDescription.trim() || undefined,
        }] : [],
        regions: parseRegions(solutionForm.regions),
      })
      setSolutionForm(emptySolutionForm(solutionForm.projectId))
      setShowSolutionForm(false)
      await load()
    } catch (cause: unknown) {
      setError(getErrorMessage(cause, '方案版本保存失败'))
    } finally {
      setSaving(false)
    }
  }

  const submitRisk = async () => {
    if (!patent.database_id || !riskForm.title.trim() || !riskForm.triggerReason.trim()) return
    setSaving(true)
    setError(null)
    try {
      await projectRiskService.createRiskCase({
        database_id: patent.database_id,
        title: riskForm.title.trim(),
        trigger_reason: riskForm.triggerReason.trim(),
        current_gate: riskForm.currentGate || undefined,
        patent_links: [{ patent_id: patent.id }],
        solution_links: riskForm.solutionVersionId ? [{ solution_version_id: Number(riskForm.solutionVersionId) }] : [],
        regions: parseRegions(riskForm.regions),
      })
      setRiskForm(emptyRiskForm)
      setShowRiskForm(false)
      await load()
    } catch (cause: unknown) {
      setError(getErrorMessage(cause, '风险案例保存失败'))
    } finally {
      setSaving(false)
    }
  }

  const submitAssessment = async (riskCaseId: number) => {
    setSaving(true)
    setError(null)
    try {
      await projectRiskService.addAssessment(riskCaseId, {
        assessment_stage: assessmentForm.stage,
        solution_version_id: assessmentForm.solutionVersionId ? Number(assessmentForm.solutionVersionId) : undefined,
        jurisdiction_code: assessmentForm.jurisdiction.trim() || undefined,
        preliminary_assessment: assessmentForm.preliminary.trim() || undefined,
        analysis_confirmation: assessmentForm.analysis.trim() || undefined,
        discussion_conclusion: assessmentForm.discussion.trim() || undefined,
        leadership_confirmation: assessmentForm.leadership.trim() || undefined,
        decision: assessmentForm.decision,
        risk_level: assessmentForm.level,
        gate_impact: assessmentForm.gateImpact,
        decision_basis: assessmentForm.basis.trim() || undefined,
        mitigation_summary: assessmentForm.mitigation.trim() || undefined,
        assessed_by: assessmentForm.assessedBy.trim() || undefined,
        confirmed_by: assessmentForm.confirmedBy.trim() || undefined,
        decided_by: assessmentForm.decidedBy.trim() || undefined,
      })
      setAssessmentCaseId(null)
      setAssessmentForm(emptyAssessmentForm)
      await load()
    } catch (cause: unknown) {
      setError(getErrorMessage(cause, '风险评估保存失败'))
    } finally {
      setSaving(false)
    }
  }

  if (!patent.database_id) return <div className="empty-state">当前专利尚未归属数据库，无法建立项目风险上下文。</div>

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 20 }}>
      {error && <div style={{ padding: 10, color: '#991b1b', background: '#fef2f2', border: '1px solid #fecaca', borderRadius: 6 }}>{error}</div>}
      {loading ? <div className="loading-spinner"><div className="spinner" />加载项目和风险信息...</div> : (
        <>
          <section className="identity-section">
            <div className="identity-section-heading">
              <div><h3>项目方案版本</h3><p>方案变化以新版本保存，已确认版本不会被覆盖。</p></div>
              <button className="btn btn-primary" onClick={() => { setSolutionForm(emptySolutionForm(linkedProjects[0]?.id ? String(linkedProjects[0].id) : '')); setShowSolutionForm(value => !value) }} disabled={linkedProjects.length === 0}>
                {showSolutionForm ? '收起' : '新增方案版本'}
              </button>
            </div>
            {linkedProjects.length === 0 && <div className="empty-state-desc">请先在“关联关系”中关联项目。</div>}
            {showSolutionForm && <div style={{ display: 'grid', gap: 10, padding: 14, background: '#f8fafc', border: '1px solid #e2e8f0', borderRadius: 6 }}>
              <div className="detail-grid">
                <Field label="项目"><select className="form-input" value={solutionForm.projectId} onChange={event => setSolutionForm({ ...solutionForm, projectId: event.target.value })}>{linkedProjects.map(project => <option key={project.id} value={project.id}>{project.name}</option>)}</select></Field>
                <Field label="版本名称"><input className="form-input" value={solutionForm.name} onChange={event => setSolutionForm({ ...solutionForm, name: event.target.value })} placeholder="如：美国项目下模前结构方案" /></Field>
                <Field label="项目阶段"><select className="form-input" value={solutionForm.stage} onChange={event => setSolutionForm({ ...solutionForm, stage: event.target.value })}>{STAGES.map(stage => <option key={stage}>{stage}</option>)}</select></Field>
                <Field label="来源类型"><select className="form-input" value={solutionForm.sourceType} onChange={event => setSolutionForm({ ...solutionForm, sourceType: event.target.value })}><option value="manual">检索师人工录入</option><option value="研发描述">研发描述</option><option value="meeting">会议</option><option value="email">邮件</option><option value="other">其他</option></select></Field>
                <Field label="方案变更概述" full><textarea className="form-input" rows={2} value={solutionForm.changeSummary} onChange={event => setSolutionForm({ ...solutionForm, changeSummary: event.target.value })} /></Field>
                <Field label="变化特征"><input className="form-input" value={solutionForm.featureName} onChange={event => setSolutionForm({ ...solutionForm, featureName: event.target.value })} placeholder="如：散热结构" /></Field>
                <Field label="变更后描述"><input className="form-input" value={solutionForm.afterDescription} onChange={event => setSolutionForm({ ...solutionForm, afterDescription: event.target.value })} /></Field>
                <Field label="对产品影响"><input className="form-input" value={solutionForm.impactDescription} onChange={event => setSolutionForm({ ...solutionForm, impactDescription: event.target.value })} /></Field>
                <Field label="适用国家/地区"><input className="form-input" value={solutionForm.regions} onChange={event => setSolutionForm({ ...solutionForm, regions: event.target.value })} placeholder="如 US, CN" /></Field>
                <Field label="来源描述" full><textarea className="form-input" rows={2} value={solutionForm.sourceDescription} onChange={event => setSolutionForm({ ...solutionForm, sourceDescription: event.target.value })} placeholder="研发描述、会议纪要、邮件主题或其他来源" /></Field>
              </div>
              <div><button className="btn btn-primary" onClick={() => void submitSolution()} disabled={saving || !solutionForm.name.trim() || !solutionForm.projectId}>{saving ? '保存中...' : '保存方案版本'}</button></div>
            </div>}
            {allVersions.length === 0 ? <div className="empty-state-desc">暂无方案版本。</div> : <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>{allVersions.map(version => {
              const project = projects.find(item => item.id === version.project_id)
              return <div key={version.id} style={{ padding: 12, border: '1px solid #e2e8f0', borderRadius: 6, background: '#fff' }}><div style={{ display: 'flex', justifyContent: 'space-between', gap: 8, flexWrap: 'wrap' }}><strong>{version.version_no} · {version.name}</strong><span className="status-badge">{version.status} · {version.project_stage || '未填阶段'}</span></div><div style={{ color: '#64748b', fontSize: 12, marginTop: 5 }}>{project?.name || `项目 #${version.project_id}`} · 来源：{version.source_type || '未填写'} · {version.confirmed_at ? `确认于 ${dateTime(version.confirmed_at)}` : '待确认'}</div><div style={{ marginTop: 8, whiteSpace: 'pre-wrap', fontSize: 13 }}>{version.change_summary || version.changes.map(change => `${change.feature_name}${change.after_description ? `：${change.after_description}` : ''}`).join('；') || '未填写变化描述'}</div><div style={{ marginTop: 6, color: '#64748b', fontSize: 12 }}>适用地区：{version.regions.map(region => region.region_code).join('、') || '未填写'} · 来源：{version.source_description || '未填写'}</div>{version.status !== 'confirmed' && <button className="btn btn-secondary" style={{ marginTop: 8 }} disabled={saving} onClick={() => void projectRiskService.confirmSolutionVersion(version.id, 'local-user').then(load).catch(cause => setError(getErrorMessage(cause, '方案确认失败')))}>确认此版本</button>}</div>
            })}</div>}
          </section>

          <section className="identity-section">
            <div className="identity-section-heading"><div><h3>风险案例</h3><p>风险判断、会议决定和后续复核按版本持续记录。</p></div><button className="btn btn-primary" onClick={() => setShowRiskForm(value => !value)}>{showRiskForm ? '收起' : '新建风险案例'}</button></div>
            {showRiskForm && <div style={{ display: 'grid', gap: 10, padding: 14, background: '#f8fafc', border: '1px solid #e2e8f0', borderRadius: 6 }}><div className="detail-grid"><Field label="风险标题"><input className="form-input" value={riskForm.title} onChange={event => setRiskForm({ ...riskForm, title: event.target.value })} placeholder="如：美国专利涉及当前产品方案" /></Field><Field label="当前 Gate"><select className="form-input" value={riskForm.currentGate} onChange={event => setRiskForm({ ...riskForm, currentGate: event.target.value })}>{STAGES.map(stage => <option key={stage}>{stage}</option>)}</select></Field><Field label="触发原因" full><textarea className="form-input" rows={3} value={riskForm.triggerReason} onChange={event => setRiskForm({ ...riskForm, triggerReason: event.target.value })} placeholder="如：月度竞对新公开专利跟踪发现涉及某方案特征" /></Field><Field label="关联方案版本"><select className="form-input" value={riskForm.solutionVersionId} onChange={event => setRiskForm({ ...riskForm, solutionVersionId: event.target.value })}><option value="">暂不关联</option>{allVersions.map(version => <option key={version.id} value={version.id}>{version.version_no} · {version.name}</option>)}</select></Field><Field label="涉及国家/地区"><input className="form-input" value={riskForm.regions} onChange={event => setRiskForm({ ...riskForm, regions: event.target.value })} placeholder="如 US" /></Field></div><button className="btn btn-primary" onClick={() => void submitRisk()} disabled={saving || !riskForm.title.trim() || !riskForm.triggerReason.trim()}>{saving ? '保存中...' : '保存风险案例'}</button></div>}
            {riskCases.length === 0 ? <div className="empty-state-desc">当前专利暂无结构化风险案例。旧风险字段仍保留在兼容区域。</div> : <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>{riskCases.map(riskCase => <RiskCaseCard key={riskCase.id} riskCase={riskCase} assessmentCaseId={assessmentCaseId} setAssessmentCaseId={setAssessmentCaseId} assessmentForm={assessmentForm} setAssessmentForm={setAssessmentForm} onSubmitAssessment={submitAssessment} reviewCaseId={reviewCaseId} setReviewCaseId={setReviewCaseId} onReload={load} saving={saving} setError={setError} />)}</div>}
          </section>
        </>
      )}
    </div>
  )
}

function RiskCaseCard({ riskCase, assessmentCaseId, setAssessmentCaseId, assessmentForm, setAssessmentForm, onSubmitAssessment, reviewCaseId, setReviewCaseId, onReload, saving, setError }: { riskCase: RiskCase; assessmentCaseId: number | null; setAssessmentCaseId: (id: number | null) => void; assessmentForm: AssessmentForm; setAssessmentForm: (form: AssessmentForm) => void; onSubmitAssessment: (id: number) => Promise<void>; reviewCaseId: number | null; setReviewCaseId: (id: number | null) => void; onReload: () => Promise<void>; saving: boolean; setError: (value: string) => void }) {
  const latest = riskCase.assessments[0]
  const [reviewOutcome, setReviewOutcome] = useState('')
  const [reviewTrigger, setReviewTrigger] = useState('')
  const submitReview = async () => {
    if (!reviewOutcome.trim()) return
    try {
      await projectRiskService.addReview(riskCase.id, { trigger_type: reviewTrigger || 'manual_review', review_outcome: reviewOutcome.trim(), reviewed_by: 'local-user' })
      setReviewOutcome('')
      setReviewTrigger('')
      setReviewCaseId(null)
      await onReload()
    } catch (cause: unknown) {
      setError(getErrorMessage(cause, '风险复核保存失败'))
    }
  }
  return <div style={{ padding: 14, border: '1px solid #cbd5e1', borderRadius: 6, background: '#fff' }}><div style={{ display: 'flex', justifyContent: 'space-between', gap: 8, flexWrap: 'wrap' }}><strong>{riskCase.title}</strong><span className="status-badge">{riskCase.status} · {riskCase.current_risk_level}</span></div><div style={{ color: '#64748b', fontSize: 12, marginTop: 5 }}>触发：{riskCase.trigger_reason} · Gate：{riskCase.current_gate || '未填写'} · 地区：{riskCase.regions.map(region => region.region_code).join('、') || '未填写'}</div>{latest && <div style={{ marginTop: 10, padding: 10, background: '#f8fafc', borderRadius: 5, fontSize: 13 }}><div><b>最新评估 v{latest.version_no}</b> · {latest.decision} · Gate 影响：{latest.gate_impact}</div>{latest.decision_basis && <div style={{ marginTop: 5, whiteSpace: 'pre-wrap' }}>{latest.decision_basis}</div>}{latest.decided_by && <div style={{ marginTop: 5, color: '#64748b', fontSize: 12 }}>决定人：{latest.decided_by}</div>}</div>}<div style={{ display: 'flex', gap: 8, marginTop: 10, flexWrap: 'wrap' }}><button className="btn btn-secondary" onClick={() => { setAssessmentCaseId(assessmentCaseId === riskCase.id ? null : riskCase.id); setReviewCaseId(null); if (assessmentCaseId !== riskCase.id) setAssessmentForm({ ...emptyAssessmentForm, solutionVersionId: String(riskCase.solution_links[0]?.solution_version_id || '') }) }}>追加风险评估</button><button className="btn btn-secondary" onClick={() => { setReviewCaseId(reviewCaseId === riskCase.id ? null : riskCase.id); setAssessmentCaseId(null) }}>记录复核</button><span style={{ color: '#64748b', fontSize: 12, alignSelf: 'center' }}>评估 {riskCase.assessments.length} 次 · 复核 {riskCase.reviews.length} 次</span></div>{assessmentCaseId === riskCase.id && <div style={{ marginTop: 12, padding: 12, background: '#f8fafc', borderRadius: 5 }}><div className="detail-grid"><Field label="阶段"><select className="form-input" value={assessmentForm.stage} onChange={event => setAssessmentForm({ ...assessmentForm, stage: event.target.value })}>{STAGES.map(stage => <option key={stage}>{stage}</option>)}</select></Field><Field label="方案版本"><select className="form-input" value={assessmentForm.solutionVersionId} onChange={event => setAssessmentForm({ ...assessmentForm, solutionVersionId: event.target.value })}><option value="">待关联</option>{riskCase.solution_links.map(link => <option key={link.solution_version_id} value={link.solution_version_id}>方案版本 #{link.solution_version_id}</option>)}</select></Field><Field label="法域"><input className="form-input" value={assessmentForm.jurisdiction} onChange={event => setAssessmentForm({ ...assessmentForm, jurisdiction: event.target.value })} placeholder="如 US" /></Field><Field label="风险等级"><select className="form-input" value={assessmentForm.level} onChange={event => setAssessmentForm({ ...assessmentForm, level: event.target.value })}><option value="none">无</option><option value="low">低</option><option value="medium">中</option><option value="high">高</option><option value="critical">严重</option></select></Field><Field label="决定"><select className="form-input" value={assessmentForm.decision} onChange={event => setAssessmentForm({ ...assessmentForm, decision: event.target.value })}><option value="pending">待确认草稿</option><option value="avoid">要求规避</option><option value="continue_with_risk">承担风险继续</option><option value="accepted">接受风险</option><option value="closed">关闭</option><option value="monitor">持续关注</option></select></Field><Field label="Gate 影响"><select className="form-input" value={assessmentForm.gateImpact} onChange={event => setAssessmentForm({ ...assessmentForm, gateImpact: event.target.value })}><option value="unknown">待判断</option><option value="none">不改变</option><option value="review_required">需要评审</option><option value="hold">暂缓 Gate</option><option value="continue_with_risk">带风险继续</option></select></Field><Field label="初步判断" full><textarea className="form-input" rows={2} value={assessmentForm.preliminary} onChange={event => setAssessmentForm({ ...assessmentForm, preliminary: event.target.value })} /></Field><Field label="分析师确认" full><textarea className="form-input" rows={2} value={assessmentForm.analysis} onChange={event => setAssessmentForm({ ...assessmentForm, analysis: event.target.value })} /></Field><Field label="会议/领导结论" full><textarea className="form-input" rows={2} value={assessmentForm.leadership} onChange={event => setAssessmentForm({ ...assessmentForm, leadership: event.target.value })} /></Field><Field label="结论依据" full><textarea className="form-input" rows={2} value={assessmentForm.basis} onChange={event => setAssessmentForm({ ...assessmentForm, basis: event.target.value })} /></Field><Field label="规避或预算说明" full><textarea className="form-input" rows={2} value={assessmentForm.mitigation} onChange={event => setAssessmentForm({ ...assessmentForm, mitigation: event.target.value })} /></Field><Field label="分析人"><input className="form-input" value={assessmentForm.assessedBy} onChange={event => setAssessmentForm({ ...assessmentForm, assessedBy: event.target.value })} /></Field><Field label="确认人"><input className="form-input" value={assessmentForm.confirmedBy} onChange={event => setAssessmentForm({ ...assessmentForm, confirmedBy: event.target.value })} /></Field><Field label="决定人"><input className="form-input" value={assessmentForm.decidedBy} onChange={event => setAssessmentForm({ ...assessmentForm, decidedBy: event.target.value })} /></Field></div><button className="btn btn-primary" disabled={saving} onClick={() => void onSubmitAssessment(riskCase.id)}>追加评估版本</button></div>}{reviewCaseId === riskCase.id && <div style={{ marginTop: 12, padding: 12, background: '#f8fafc', borderRadius: 5 }}><div className="detail-grid"><Field label="触发类型"><input className="form-input" value={reviewTrigger} onChange={event => setReviewTrigger(event.target.value)} placeholder="如：出货地变化" /></Field><Field label="复核结论" full><textarea className="form-input" rows={3} value={reviewOutcome} onChange={event => setReviewOutcome(event.target.value)} placeholder="记录本次复核结果和是否需要重新评估" /></Field></div><button className="btn btn-primary" disabled={saving || !reviewOutcome.trim()} onClick={() => void submitReview()}>保存复核记录</button></div>}</div>
}

function Field({ label, children, full }: { label: string; children: React.ReactNode; full?: boolean }) {
  return <div style={{ display: 'flex', flexDirection: 'column', gap: 4, gridColumn: full ? '1 / -1' : undefined }}><label style={{ fontSize: 12, color: '#64748b', fontWeight: 500 }}>{label}</label>{children}</div>
}
