import { useCallback, useEffect, useMemo, useState } from 'react'
import { semanticSearchService } from '../../services'
import { getErrorMessage } from '../../lib/errors'
import { useAppStore } from '../../store'
import Icon from '../common/Icon'
import type { SemanticEvaluationCase, SemanticEvaluationDataset, SemanticEvaluationRun, SemanticIndex, SemanticJob, SemanticProfile, SemanticProvider, SemanticStatus } from '../../types'

const inputStyle = { width: '100%', boxSizing: 'border-box' as const }

function dateText(value?: string | null): string {
  return value ? new Date(value).toLocaleString() : '-'
}

function StatusTile({ label, value, detail }: { label: string; value: string | number; detail?: string }) {
  return <div className="semantic-status-tile"><div className="semantic-status-label">{label}</div><strong>{value}</strong>{detail && <span>{detail}</span>}</div>
}

function numberList(value: string): number[] {
  return value.split(/[\s,，]+/).map(item => Number(item.trim())).filter(item => Number.isInteger(item) && item > 0)
}

function thresholdValue(value: string): number | undefined {
  if (!value.trim()) return undefined
  const parsed = Number(value)
  return Number.isFinite(parsed) && parsed >= 0 && parsed <= 1 ? parsed : undefined
}

// Provider presets mirror the unified model-config experience: a familiar
// vendor dropdown that fills Base URL / model, plus a plain API Key field.
const PROVIDER_PRESETS = [
  { key: 'openai', label: 'OpenAI', baseUrl: 'https://api.openai.com/v1', model: 'text-embedding-3-small' },
  { key: 'dashscope', label: '通义千问（DashScope 兼容）', baseUrl: 'https://dashscope.aliyuncs.com/compatible-mode/v1', model: 'text-embedding-v3' },
  { key: 'zhipu', label: '智谱 AI', baseUrl: 'https://open.bigmodel.cn/api/paas/v4', model: 'embedding-3' },
  { key: 'siliconflow', label: '硅基流动', baseUrl: 'https://api.siliconflow.cn/v1', model: 'BAAI/bge-m3' },
  { key: 'local', label: '本地 / 自建（OpenAI 兼容）', baseUrl: 'http://localhost:1234/v1', model: '' },
  { key: 'custom', label: '自定义', baseUrl: '', model: '' },
] as const

export default function SemanticSearchManagement({ initialTab = 'overview' }: { initialTab?: 'overview' | 'models' } = {}) {
  const [tab, setTab] = useState<'overview' | 'models' | 'indexes' | 'evaluation'>(initialTab)
  const { databases, currentDatabaseId } = useAppStore()
  const [profiles, setProfiles] = useState<SemanticProfile[]>([])
  const [providers, setProviders] = useState<SemanticProvider[]>([])
  const [indexes, setIndexes] = useState<SemanticIndex[]>([])
  const [jobs, setJobs] = useState<SemanticJob[]>([])
  const [datasets, setDatasets] = useState<SemanticEvaluationDataset[]>([])
  const [cases, setCases] = useState<SemanticEvaluationCase[]>([])
  const [casesDatasetId, setCasesDatasetId] = useState<number | null>(null)
  const [runs, setRuns] = useState<SemanticEvaluationRun[]>([])
  const [status, setStatus] = useState<SemanticStatus | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [message, setMessage] = useState('')

  const [editingProviderId, setEditingProviderId] = useState<number | null>(null)
  const [showProviderForm, setShowProviderForm] = useState(false)
  const [providerName, setProviderName] = useState('')
  const [providerKind, setProviderKind] = useState<'embedding' | 'rerank'>('embedding')
  const [providerEndpoint, setProviderEndpoint] = useState('')
  const [providerApiKey, setProviderApiKey] = useState('')
  const [providerModel, setProviderModel] = useState('')
  const [providerHasKey, setProviderHasKey] = useState(false)

  const [editingProfileId, setEditingProfileId] = useState<number | null>(null)
  const [profileRerankProviderId, setProfileRerankProviderId] = useState('')
  const [profileRerankModel, setProfileRerankModel] = useState('')
  const [profileRerankEnabled, setProfileRerankEnabled] = useState(false)
  const [profileRerankTopN, setProfileRerankTopN] = useState('20')
  const [profileQualityGateEnabled, setProfileQualityGateEnabled] = useState(false)
  const [profileThresholdRecall, setProfileThresholdRecall] = useState('')
  const [profileThresholdMrr, setProfileThresholdMrr] = useState('')
  const [profileThresholdNdcg, setProfileThresholdNdcg] = useState('')
  const [profileThresholdPrecision, setProfileThresholdPrecision] = useState('')
  const [profileEnabled, setProfileEnabled] = useState(true)
  const [showProfileForm, setShowProfileForm] = useState(false)
  const [profileName, setProfileName] = useState('')
  const [profileEmbeddingProviderId, setProfileEmbeddingProviderId] = useState('')
  const [profileEmbeddingModel, setProfileEmbeddingModel] = useState('text-embedding-3-small')
  const [profileEmbeddingDimensions, setProfileEmbeddingDimensions] = useState('')
  const [profileVectorBackend, setProfileVectorBackend] = useState('json_local')
  const [profileRetrievalMode, setProfileRetrievalMode] = useState<'keyword' | 'semantic' | 'hybrid'>('hybrid')
  const [indexScope, setIndexScope] = useState<'current' | 'global'>('current')

  const [showDatasetForm, setShowDatasetForm] = useState(false)
  const [datasetName, setDatasetName] = useState('中文专利检索集')
  const [datasetVersion, setDatasetVersion] = useState('v1')
  const [showCaseForm, setShowCaseForm] = useState(false)
  const [caseKey, setCaseKey] = useState('')
  const [caseQuery, setCaseQuery] = useState('')
  const [caseDatabaseId, setCaseDatabaseId] = useState('')
  const [caseRelevantIds, setCaseRelevantIds] = useState('')
  const [caseNotes, setCaseNotes] = useState('')

  const [selectedProfileId, setSelectedProfileId] = useState<number | null>(null)
  const [selectedDatasetId, setSelectedDatasetId] = useState<number | null>(null)
  const [selectedIndexId, setSelectedIndexId] = useState<number | null>(null)
  const [evaluationMode, setEvaluationMode] = useState<'keyword' | 'semantic' | 'hybrid'>('hybrid')

  const quickProfile = useMemo(
    () => profiles.find(profile => profile.id === selectedProfileId) || profiles.find(profile => profile.is_default) || profiles[0],
    [profiles, selectedProfileId],
  )
  const selectedIndexDatabaseId = indexScope === 'current' ? currentDatabaseId : null
  const quickProfileReady = Boolean(quickProfile?.enabled && quickProfile.embedding_dimensions && providers.some(provider => provider.id === quickProfile.embedding_provider_id && provider.enabled))
  const quickActiveIndex = useMemo(() => indexes.find(index => (
    index.profile_id === quickProfile?.id
      && index.is_active
      && (index.database_id === selectedIndexDatabaseId || (selectedIndexDatabaseId !== null && index.database_id == null))
  )), [indexes, quickProfile?.id, selectedIndexDatabaseId])
  const quickJob = useMemo(() => jobs.find(job => (
    job.profile_id === quickProfile?.id
      && ['pending', 'running', 'retry_wait'].includes(job.status)
  )), [jobs, quickProfile?.id])

  const load = useCallback(async () => {
    setError('')
    try {
      const [profileResult, providerResult, indexResult, jobResult, statusResult, datasetResult, runResult] = await Promise.all([
        semanticSearchService.profiles(), semanticSearchService.providers(), semanticSearchService.indexes(),
        semanticSearchService.jobs(), semanticSearchService.status(), semanticSearchService.datasets(), semanticSearchService.runs(),
      ])
      setProfiles(profileResult.items); setProviders(providerResult.items); setIndexes(indexResult.items)
      setJobs(jobResult.items); setStatus(statusResult); setDatasets(datasetResult.items); setRuns(runResult.items)
      setSelectedProfileId(current => current && profileResult.items.some(item => item.id === current) ? current : profileResult.items.find(item => item.is_default && item.enabled)?.id ?? profileResult.items[0]?.id ?? null)
      setSelectedDatasetId(current => current && datasetResult.items.some(item => item.id === current) ? current : datasetResult.items[0]?.id ?? null)
      setSelectedIndexId(current => current && indexResult.items.some(item => item.id === current) ? current : indexResult.items.find(item => item.status === 'validating')?.id ?? indexResult.items.find(item => item.is_active)?.id ?? null)
    } catch (loadError: unknown) {
      setError(getErrorMessage(loadError, '语义检索管理数据加载失败'))
    }
  }, [])

  // This effect owns synchronization with persisted semantic-search state.
  // eslint-disable-next-line react-hooks/set-state-in-effect
  useEffect(() => { void load() }, [load])

  useEffect(() => {
    if (!jobs.some(job => ['pending', 'running', 'retry_wait'].includes(job.status))) return
    const timer = window.setInterval(() => { void load() }, 3000)
    return () => window.clearInterval(timer)
  }, [jobs, load])

  // Cases are loaded separately so changing the selected dataset never shows stale labels.
  useEffect(() => {
    if (!selectedDatasetId) return
    const datasetId = selectedDatasetId
    void semanticSearchService.cases(datasetId).then(result => { setCases(result.items); setCasesDatasetId(datasetId) }).catch(loadError => setError(getErrorMessage(loadError, '评测 Case 加载失败')))
  }, [selectedDatasetId])

  const profileById = useMemo(() => new Map(profiles.map(item => [item.id, item])), [profiles])
  const rerankProviders = useMemo(() => providers.filter(provider => provider.provider_kind === 'rerank'), [providers])

  const runAction = async (action: () => Promise<unknown>, success: string) => {
    setBusy(true); setError(''); setMessage('')
    try { await action(); setMessage(success); await load() } catch (actionError: unknown) { setError(getErrorMessage(actionError, '操作失败')) } finally { setBusy(false) }
  }

  const resetProviderForm = () => {
    setEditingProviderId(null); setProviderName(''); setProviderKind('embedding'); setProviderEndpoint(''); setProviderApiKey(''); setProviderModel(''); setProviderHasKey(false)
  }

  const applyProviderPreset = (key: string) => {
    const preset = PROVIDER_PRESETS.find(item => item.key === key)
    if (!preset || preset.key === 'custom') return
    setProviderEndpoint(preset.baseUrl)
    if (providerKind === 'embedding' && preset.model) setProviderModel(preset.model)
  }

  const editProvider = (provider: SemanticProvider) => {
    setEditingProviderId(provider.id); setProviderName(provider.name); setProviderKind(provider.provider_kind)
    setProviderEndpoint(provider.endpoint || ''); setProviderApiKey('')
    setProviderHasKey(Boolean(provider.has_api_key || provider.credential_ref))
    setProviderModel(typeof provider.config_json.model === 'string' ? provider.config_json.model : '')
    setShowProviderForm(true)
  }

  const saveProvider = async () => {
    if (!providerName.trim()) { setError('供应商名称不能为空'); return }
    if (providerKind === 'rerank' && !providerEndpoint.trim()) { setError('Rerank 供应商必须填写 Base URL'); return }
    if (!editingProviderId && !providerApiKey.trim()) { setError('请填写 API Key'); return }
    await runAction(async () => {
      const data: Record<string, unknown> = { name: providerName.trim(), endpoint: providerEndpoint.trim() || null, config_json: providerModel.trim() ? { model: providerModel.trim() } : {} }
      if (providerApiKey.trim()) data.api_key = providerApiKey.trim()
      if (editingProviderId) await semanticSearchService.updateProvider(editingProviderId, data)
      else await semanticSearchService.createProvider({ ...data, provider_kind: providerKind, provider_type: providerKind === 'embedding' ? 'openai_compatible' : 'openai_compatible_rerank', enabled: true })
      resetProviderForm(); setShowProviderForm(false)
    }, editingProviderId ? '供应商已更新' : '供应商已保存')
  }

  const testProvider = (provider: SemanticProvider) => {
    const profile = profiles.find(item => item.embedding_provider_id === provider.id)
    return runAction(() => semanticSearchService.testProvider(provider.id, provider.provider_kind === 'embedding' && profile ? { profile_id: profile.id } : { model: typeof provider.config_json.model === 'string' ? provider.config_json.model : undefined }), '供应商测试完成')
  }
  const toggleProvider = (provider: SemanticProvider) => runAction(() => semanticSearchService.updateProvider(provider.id, { enabled: !provider.enabled }), provider.enabled ? '供应商已停用' : '供应商已启用')

  const editProfile = (profile: SemanticProfile) => {
    setEditingProfileId(profile.id); setProfileRerankProviderId(profile.rerank_provider_id ? String(profile.rerank_provider_id) : '')
    setProfileRerankModel(profile.rerank_model || ''); setProfileRerankEnabled(profile.rerank_enabled); setProfileRerankTopN(String(profile.rerank_top_n || 20))
    setProfileQualityGateEnabled(profile.quality_gate_enabled); setProfileEnabled(profile.enabled)
    setProfileThresholdRecall(profile.quality_thresholds.recall_at_k == null ? '' : String(profile.quality_thresholds.recall_at_k))
    setProfileThresholdMrr(profile.quality_thresholds.mrr == null ? '' : String(profile.quality_thresholds.mrr))
    setProfileThresholdNdcg(profile.quality_thresholds.ndcg_at_k == null ? '' : String(profile.quality_thresholds.ndcg_at_k))
    setProfileThresholdPrecision(profile.quality_thresholds.precision_at_k == null ? '' : String(profile.quality_thresholds.precision_at_k))
  }

  const saveProfile = async () => {
    if (!editingProfileId) return
    const thresholdInputs: Record<string, string> = { recall_at_k: profileThresholdRecall, mrr: profileThresholdMrr, ndcg_at_k: profileThresholdNdcg, precision_at_k: profileThresholdPrecision }
    const thresholds: Record<string, number> = {}
    for (const [key, value] of Object.entries(thresholdInputs)) {
      if (!value.trim()) continue
      const parsed = thresholdValue(value)
      if (parsed === undefined) { setError(`${key} 必须是 0 到 1 之间的数字`); return }
      thresholds[key] = parsed
    }
    const topN = Number(profileRerankTopN)
    if (!Number.isInteger(topN) || topN < 1 || topN > 100) { setError('Rerank 候选数必须是 1 到 100'); return }
    if (profileRerankEnabled && !profileRerankProviderId) { setError('启用 Rerank 时必须选择供应商'); return }
    await runAction(async () => {
      await semanticSearchService.updateProfile(editingProfileId, {
        enabled: profileEnabled, rerank_enabled: profileRerankEnabled, rerank_provider_id: profileRerankProviderId ? Number(profileRerankProviderId) : null,
        rerank_model: profileRerankModel.trim() || null, rerank_top_n: topN, quality_gate_enabled: profileQualityGateEnabled, quality_thresholds: thresholds,
      })
      setEditingProfileId(null)
    }, 'Profile 已更新')
  }

  const createProfile = async () => {
    if (!profileName.trim()) { setError('Profile 名称不能为空'); return }
    if (!profileEmbeddingProviderId) { setError('请先选择 Embedding 供应商，才能进行向量化'); return }
    const dimensions = profileEmbeddingDimensions.trim() ? Number(profileEmbeddingDimensions) : null
    if (dimensions !== null && (!Number.isInteger(dimensions) || dimensions < 1)) { setError('Embedding 维度必须是正整数'); return }
    await runAction(async () => {
      const created = await semanticSearchService.createProfile({
        name: profileName.trim(), embedding_provider_id: profileEmbeddingProviderId ? Number(profileEmbeddingProviderId) : null,
        embedding_model: profileEmbeddingModel.trim() || 'text-embedding-3-small', embedding_dimensions: dimensions,
        vector_backend: profileVectorBackend, retrieval_mode: profileRetrievalMode,
        is_default: !profiles.some(profile => profile.is_default && profile.enabled && profile.embedding_provider_id),
        indexed_field_allowlist: [],
      })
      setSelectedProfileId(created.id)
      setProfileName(''); setProfileEmbeddingProviderId(''); setProfileEmbeddingModel('text-embedding-3-small'); setProfileEmbeddingDimensions(''); setShowProfileForm(false)
    }, 'Profile 已创建')
  }

  const createDataset = async () => {
    if (!datasetName.trim() || !datasetVersion.trim()) { setError('评测集名称和版本不能为空'); return }
    await runAction(async () => {
      const created = await semanticSearchService.createDataset({ name: datasetName.trim(), version: datasetVersion.trim() })
      setSelectedDatasetId(created.id); setShowDatasetForm(false)
    }, '评测集已创建')
  }

  const createCase = async () => {
    const relevant = numberList(caseRelevantIds)
    if (!selectedDatasetId || !caseKey.trim() || !caseQuery.trim() || !relevant.length) { setError('Case Key、查询文本和至少一个相关专利 ID 不能为空'); return }
    const databaseId = caseDatabaseId.trim() ? Number(caseDatabaseId) : null
    if (databaseId !== null && (!Number.isInteger(databaseId) || databaseId < 1)) { setError('数据库 ID 必须是正整数'); return }
    await runAction(async () => {
      const created = await semanticSearchService.createCase(selectedDatasetId, { case_key: caseKey.trim(), query: caseQuery.trim(), database_id: databaseId, relevant_patent_ids: relevant, notes: caseNotes.trim() || undefined })
      setCases(current => [...current, created]); setCaseKey(''); setCaseQuery(''); setCaseDatabaseId(''); setCaseRelevantIds(''); setCaseNotes(''); setShowCaseForm(false)
    }, '评测 Case 已添加')
  }

  const toggleCase = (item: SemanticEvaluationCase) => runAction(async () => {
    const updated = await semanticSearchService.updateCase(item.id, { enabled: !item.enabled })
    setCases(current => current.map(caseItem => caseItem.id === updated.id ? updated : caseItem))
  }, item.enabled ? 'Case 已停用' : 'Case 已启用')

  const deleteCase = (item: SemanticEvaluationCase) => {
    if (!window.confirm(`确认删除评测 Case「${item.case_key}」吗？`)) return
    return runAction(async () => {
      await semanticSearchService.deleteCase(item.id); setCases(current => current.filter(caseItem => caseItem.id !== item.id))
    }, '评测 Case 已删除')
  }

  const rebuild = (profile: SemanticProfile) => {
    if (indexScope === 'current' && currentDatabaseId === null) {
      setError('当前没有选中的数据库，请先选择数据库，或把索引范围切换为全局')
      return Promise.resolve()
    }
    const databaseId = indexScope === 'current' ? currentDatabaseId : null
    return runAction(
      () => semanticSearchService.rebuild(profile.id, databaseId),
      `${indexScope === 'current' ? '当前数据库' : '全局'}向量化任务已创建，后台会自动处理`,
    )
  }
  const activate = (index: SemanticIndex) => {
    if (!window.confirm(`确认激活索引 ${index.index_version} 吗？`)) return Promise.resolve()
    return runAction(() => semanticSearchService.activate(index.id), '索引已激活')
  }
  const health = (profile: SemanticProfile) => runAction(() => semanticSearchService.profileHealth(profile.id), '供应商健康检查完成')
  const retryJob = (job: SemanticJob) => runAction(() => semanticSearchService.retryJob(job.id), '任务已重新排队')
  const runEvaluation = () => {
    if (!selectedProfileId || !selectedDatasetId) { setError('请先选择 Profile 和评测集'); return }
    if (casesDatasetId !== selectedDatasetId || !cases.some(item => item.enabled)) { setError('当前评测集没有启用的 Case，不能运行评测'); return }
    return runAction(() => semanticSearchService.runEvaluation({ dataset_id: selectedDatasetId, profile_id: selectedProfileId, mode: evaluationMode, top_k: 10, index_id: selectedIndexId }), '评测已完成')
  }

  return (
    <div className="semantic-management">
      <div className="semantic-workbench-header">
        <div className="semantic-workbench-title">
          <h2>语义检索</h2>
          <span>配置向量模型、构建索引并评测检索质量</span>
        </div>
        <nav className="workspace-subtabs" aria-label="语义检索模块">{([{ key: 'overview', label: '概览' }, { key: 'models', label: '模型配置' }, { key: 'indexes', label: '索引与任务' }, { key: 'evaluation', label: '质量评测' }] as const).map(item => <button key={item.key} className={tab === item.key ? 'active' : ''} onClick={() => setTab(item.key)}>{item.label}</button>)}</nav>
        <button className="btn btn-secondary" onClick={() => void load()} disabled={busy}><Icon name="refresh" />刷新</button>
      </div>
      {error && <div className="management-error">{error}</div>}
      {message && <div className="semantic-management-message">{message}</div>}
      <div className="semantic-overview-grid" hidden={tab !== 'overview'}>
        <section className="semantic-panel">
          <div className="semantic-panel-title"><strong>快速开始</strong><span>按顺序完成 4 步即可开启语义检索</span></div>
          <div className="semantic-scope-row">
            <label>检索配置
              <select className="form-input" value={quickProfile?.id ?? ''} onChange={event => setSelectedProfileId(Number(event.target.value) || null)}><option value="">选择检索配置</option>{profiles.map(profile => <option key={profile.id} value={profile.id}>{profile.name}</option>)}</select>
            </label>
            <label>索引范围
              <select className="form-input" value={indexScope} onChange={event => setIndexScope(event.target.value as 'current' | 'global')}>
                <option value="current">当前数据库{currentDatabaseId ? ` · ${databases.find(database => database.id === currentDatabaseId)?.name || currentDatabaseId}` : ' · 未选择'}</option>
                <option value="global">全部数据库</option>
              </select>
            </label>
          </div>
          <div className="semantic-step-list">
            <div className={`semantic-step-item ${providers.some(provider => provider.provider_kind === 'embedding' && provider.enabled) ? 'ready' : ''}`}>
              <span className="semantic-step-number">1</span>
              <div className="semantic-step-body"><strong>配置向量模型供应商</strong><span>{providers.some(provider => provider.provider_kind === 'embedding' && provider.enabled) ? '已配置' : '尚未配置，填写 Base URL 与 API Key 即可'}</span></div>
              <button type="button" className="btn btn-secondary" onClick={() => { setTab('models'); resetProviderForm(); setShowProviderForm(true) }}>去配置</button>
            </div>
            <div className={`semantic-step-item ${quickProfile?.embedding_provider_id ? 'ready' : ''}`}>
              <span className="semantic-step-number">2</span>
              <div className="semantic-step-body"><strong>选择检索配置</strong><span>{quickProfile ? quickProfile.name : '尚未创建'}</span></div>
              <button type="button" className="btn btn-secondary" onClick={() => { setTab('models'); setShowProfileForm(true) }}>新建</button>
            </div>
            <div className={`semantic-step-item ${quickProfile?.embedding_dimensions ? 'ready' : ''}`}>
              <span className="semantic-step-number">3</span>
              <div className="semantic-step-body"><strong>检测向量维度</strong><span>{quickProfile?.embedding_dimensions ? `${quickProfile.embedding_dimensions} 维` : '尚未检测'}</span></div>
              <button type="button" className="btn btn-secondary" disabled={!quickProfile?.embedding_provider_id || busy} onClick={() => quickProfile && void health(quickProfile)}>检测</button>
            </div>
            <div className={`semantic-step-item ${quickActiveIndex ? 'ready' : ''}`}>
              <span className="semantic-step-number">4</span>
              <div className="semantic-step-body"><strong>构建并启用索引</strong><span>{quickJob ? `构建中 · ${quickJob.processed_items}/${quickJob.total_items}` : quickActiveIndex ? '已启用，可以检索' : '尚未构建'}</span></div>
              <button type="button" className="btn btn-primary" disabled={!quickProfile || !quickProfileReady || busy || Boolean(quickJob)} onClick={() => quickProfile && void rebuild(quickProfile)}>开始构建</button>
            </div>
          </div>
        </section>
        <section className="semantic-panel">
          <div className="semantic-panel-title"><strong>运行状态</strong><span>实时概览</span></div>
          <div className="semantic-status-grid compact">
            <StatusTile label="可用检索配置" value={status?.configured_profiles ?? '-'} />
            <StatusTile label="生效索引" value={status?.active_indexes ?? '-'} />
            <StatusTile label="待处理任务" value={status?.pending_jobs ?? '-'} />
            <StatusTile label="索引覆盖率" value={status ? `${(status.coverage_rate * 100).toFixed(1)}%` : '-'} detail={status ? `已索引 ${status.document_indexed} · 待处理 ${status.document_pending}` : undefined} />
            <StatusTile label="失败任务" value={status ? `${status.job_failed + status.document_failed}` : '-'} detail={status ? `待重试 ${status.job_dead_letter + status.outbox_dead_letter + status.outbox_retry_wait}` : undefined} />
            <StatusTile label="关键词检索" value={status?.sparse_available ? 'FTS5 BM25' : 'ILIKE 回退'} detail={status?.sparse_available ? '中文 trigram' : '当前 SQLite 不支持 FTS5'} />
          </div>
          <button className="btn btn-secondary" onClick={() => setTab('indexes')}><Icon name="database" />管理索引与任务</button>
        </section>
      </div>

      <section className="semantic-management-section" hidden={tab !== 'models'}>
        <div className="management-section-title"><strong>检索配置</strong><button className="btn btn-primary" onClick={() => setShowProfileForm(current => !current)}><Icon name="plus" />{showProfileForm ? '关闭表单' : '新建配置'}</button></div>
        {showProfileForm && <div className="management-form compact"><div className="management-form-grid">
          <label>名称<input className="form-input" style={inputStyle} value={profileName} onChange={event => setProfileName(event.target.value)} placeholder="patent-semantic-v1" /></label>
          <label>Embedding 供应商<select className="form-input" style={inputStyle} value={profileEmbeddingProviderId} onChange={event => { setProfileEmbeddingProviderId(event.target.value); const provider = providers.find(item => item.id === Number(event.target.value)); if (typeof provider?.config_json.model === 'string') setProfileEmbeddingModel(provider.config_json.model); setProfileEmbeddingDimensions('') }}><option value="">选择供应商</option>{providers.filter(provider => provider.provider_kind === 'embedding' && provider.enabled).map(provider => <option key={provider.id} value={provider.id}>{provider.name}</option>)}</select></label>
          <label>Embedding 模型<input className="form-input" style={inputStyle} value={profileEmbeddingModel} onChange={event => setProfileEmbeddingModel(event.target.value)} /></label>
          <label>Embedding 维度<input className="form-input" style={inputStyle} type="number" min="1" value={profileEmbeddingDimensions} onChange={event => setProfileEmbeddingDimensions(event.target.value)} placeholder="由供应商返回时可留空" /></label>
          <label>向量后端<select className="form-input" style={inputStyle} value={profileVectorBackend} onChange={event => setProfileVectorBackend(event.target.value)}><option value="zvec">Zvec</option><option value="json_local">JSON Local</option></select></label>
          <label>检索模式<select className="form-input" style={inputStyle} value={profileRetrievalMode} onChange={event => setProfileRetrievalMode(event.target.value as 'keyword' | 'semantic' | 'hybrid')}><option value="hybrid">混合</option><option value="semantic">语义</option><option value="keyword">关键词</option></select></label>
        </div><div className="management-form-actions"><button className="btn btn-primary" disabled={busy} onClick={() => void createProfile()}>保存 Profile</button></div></div>}
        <div className="semantic-model-grid">{profiles.map(profile => <article className="semantic-model-card" key={profile.id}>
          <h3><Icon name="database" />{profile.name}{profile.is_default && <span className="semantic-pill">默认</span>}{!profile.enabled && <span className="semantic-pill">停用</span>}</h3>
          <dl><dt>供应商</dt><dd>{providers.find(provider => provider.id === profile.embedding_provider_id)?.name || '未配置'}</dd><dt>向量模型</dt><dd>{profile.embedding_model || '-'}</dd><dt>维度 / 后端</dt><dd>{profile.embedding_dimensions || '未检测'} · {profile.vector_backend}</dd><dt>重排模型</dt><dd>{profile.rerank_enabled ? `${profile.rerank_model || '已启用'} · Top ${profile.rerank_top_n}` : '关闭'}</dd><dt>质量门禁</dt><dd>{profile.quality_gate_enabled ? '启用' : '手动验收'}</dd></dl>
          <div className="semantic-model-actions"><button className="btn btn-secondary" disabled={busy} onClick={() => editProfile(profile)}><Icon name="edit" />编辑</button><button className="btn btn-secondary" disabled={busy || !profile.embedding_provider_id} onClick={() => void health(profile)}>检测维度</button><button className="btn btn-primary" disabled={busy || !profile.enabled} onClick={() => { setSelectedProfileId(profile.id); setTab('overview') }}><Icon name="play" />选择此配置</button></div>
        </article>)}</div>{profiles.length === 0 && <div className="semantic-empty">暂无检索配置</div>}
        {editingProfileId && <div className="management-form compact"><div className="management-section-title"><strong>编辑 Profile</strong><span>当前 Profile 的模型、模板和分块身份不能在 Active 后修改</span></div><div className="management-form-grid">
          <label>启用<select className="form-input" style={inputStyle} value={profileEnabled ? 'yes' : 'no'} onChange={event => setProfileEnabled(event.target.value === 'yes')}><option value="yes">启用</option><option value="no">停用</option></select></label>
          <label>Rerank<select className="form-input" style={inputStyle} value={profileRerankEnabled ? 'yes' : 'no'} onChange={event => setProfileRerankEnabled(event.target.value === 'yes')}><option value="no">关闭</option><option value="yes">启用</option></select></label>
          <label>Rerank 供应商<select className="form-input" style={inputStyle} value={profileRerankProviderId} onChange={event => setProfileRerankProviderId(event.target.value)}><option value="">选择供应商</option>{rerankProviders.map(provider => <option key={provider.id} value={provider.id}>{provider.name}</option>)}</select></label>
          <label>Rerank 模型<input className="form-input" style={inputStyle} value={profileRerankModel} onChange={event => setProfileRerankModel(event.target.value)} /></label>
          <label>候选数<input className="form-input" style={inputStyle} type="number" min="1" max="100" value={profileRerankTopN} onChange={event => setProfileRerankTopN(event.target.value)} /></label>
          <label>质量门禁<select className="form-input" style={inputStyle} value={profileQualityGateEnabled ? 'yes' : 'no'} onChange={event => setProfileQualityGateEnabled(event.target.value === 'yes')}><option value="no">关闭</option><option value="yes">启用</option></select></label>
          <label>Recall@K 阈值<input className="form-input" style={inputStyle} value={profileThresholdRecall} onChange={event => setProfileThresholdRecall(event.target.value)} placeholder="0 - 1，可留空" /></label>
          <label>MRR 阈值<input className="form-input" style={inputStyle} value={profileThresholdMrr} onChange={event => setProfileThresholdMrr(event.target.value)} placeholder="0 - 1，可留空" /></label>
          <label>NDCG@K 阈值<input className="form-input" style={inputStyle} value={profileThresholdNdcg} onChange={event => setProfileThresholdNdcg(event.target.value)} placeholder="0 - 1，可留空" /></label>
          <label>Precision@K 阈值<input className="form-input" style={inputStyle} value={profileThresholdPrecision} onChange={event => setProfileThresholdPrecision(event.target.value)} placeholder="0 - 1，可留空" /></label>
        </div><div className="management-form-actions"><button className="btn btn-secondary" onClick={() => setEditingProfileId(null)}>取消</button><button className="btn btn-primary" disabled={busy} onClick={() => void saveProfile()}>保存 Profile</button></div></div>}
      </section>

      <section className="semantic-management-section" hidden={tab !== 'models'}>
        <div className="management-section-title"><strong>供应商</strong><button className="btn btn-primary" onClick={() => { resetProviderForm(); setShowProviderForm(current => !current) }}>{showProviderForm ? '关闭表单' : '新增供应商'}</button></div>
        {showProviderForm && <div className="management-form compact"><div className="semantic-provider-form">
          <label>名称<input className="form-input" value={providerName} onChange={event => setProviderName(event.target.value)} placeholder="OpenAI Embedding" /></label>
          <label>类型<select className="form-input" value={providerKind} disabled={Boolean(editingProviderId)} onChange={event => setProviderKind(event.target.value as 'embedding' | 'rerank')}><option value="embedding">Embedding</option><option value="rerank">Rerank</option></select></label>
          <label>供应商<select className="form-input" value="custom" onChange={event => applyProviderPreset(event.target.value)}><option value="custom">手动填写</option>{PROVIDER_PRESETS.filter(preset => preset.key !== 'custom').map(preset => <option key={preset.key} value={preset.key}>{preset.label}</option>)}</select></label>
          <label>Base URL<input className="form-input" value={providerEndpoint} onChange={event => setProviderEndpoint(event.target.value)} placeholder="https://api.openai.com/v1" /></label>
          <label>API Key<input className="form-input" type="password" autoComplete="off" value={providerApiKey} onChange={event => setProviderApiKey(event.target.value)} placeholder={providerHasKey ? '已配置，留空则保持不变' : 'sk-...'} /></label>
          <label>模型<input className="form-input" value={providerModel} onChange={event => setProviderModel(event.target.value)} placeholder="text-embedding-3-small" /></label>
          <span className="semantic-field-hint semantic-provider-form-full">API Key 仅用于本机向量化调用；Rerank 供应商需填写完整的 Base URL。</span>
        </div><div className="management-form-actions"><button className="btn btn-secondary" onClick={() => { resetProviderForm(); setShowProviderForm(false) }}>取消</button><button className="btn btn-primary" disabled={busy} onClick={() => void saveProvider()}>{editingProviderId ? '更新供应商' : '保存供应商'}</button></div></div>}
        <div className="semantic-model-grid">{providers.map(provider => <article className="semantic-model-card" key={provider.id}>
          <h3><Icon name="settings" />{provider.name}<span className="semantic-pill">{provider.provider_kind === 'embedding' ? 'Embedding' : 'Rerank'}</span></h3>
          <dl><dt>模型</dt><dd>{typeof provider.config_json.model === 'string' ? provider.config_json.model : '由检索配置指定'}</dd><dt>Base URL</dt><dd>{provider.endpoint || '默认'}</dd><dt>API Key</dt><dd>{provider.has_api_key ? '已配置' : provider.credential_ref || '未配置'}</dd><dt>状态</dt><dd>{provider.enabled ? (provider.last_health_status || '未检查') : '已停用'}</dd></dl>
          <div className="semantic-model-actions"><button className="btn btn-secondary" disabled={busy} onClick={() => editProvider(provider)}><Icon name="edit" />编辑</button><button className="btn btn-secondary" disabled={busy || !provider.enabled} onClick={() => void testProvider(provider)}><Icon name="activity" />测试连接</button><button className="btn btn-secondary" disabled={busy} onClick={() => void toggleProvider(provider)}>{provider.enabled ? '停用' : '启用'}</button></div>
        </article>)}</div>{providers.length === 0 && <div className="semantic-empty">暂无模型供应商</div>}
      </section>

      <section className="semantic-management-section" hidden={tab !== 'indexes'}>
        <div className="management-section-title"><strong>索引与任务</strong><span>构建完成后手动启用；失败任务可重试。</span></div>
        <div className="management-table"><table><thead><tr><th>版本</th><th>Profile</th><th>范围</th><th>状态</th><th>文档 / 专利</th><th>操作</th></tr></thead><tbody>
          {indexes.map(index => <tr key={index.id}><td className="semantic-mono">{index.index_version}</td><td>{profileById.get(index.profile_id)?.name || index.profile_id}</td><td>{index.database_id ? `数据库 ${index.database_id}` : '全局'}</td><td><span className={index.is_active ? 'semantic-pill active' : 'semantic-pill'}>{index.is_active ? 'active' : index.status}</span></td><td>{index.document_count} / {index.patent_count}</td><td>{!index.is_active && index.status === 'validating' && <button className="btn btn-primary" disabled={busy} onClick={() => void activate(index)}>激活</button>}</td></tr>)}
        </tbody></table>{indexes.length === 0 && <div className="semantic-empty">尚未创建索引。</div>}</div>
        <div className="semantic-job-list">{jobs.slice(0, 8).map(job => <div className="semantic-job-row" key={job.id}><span>#{job.id} {job.job_type}</span><span>{profileById.get(job.profile_id)?.name || job.profile_id}</span><span>{job.status}</span><span>{job.processed_items}/{job.total_items}</span><span>{job.error_code || `尝试 ${job.attempt_count}/${job.max_attempts}`}</span>{['failed', 'retry_wait', 'dead_letter'].includes(job.status) && <button className="btn btn-secondary" disabled={busy} onClick={() => void retryJob(job)}>重试</button>}</div>)}</div>
      </section>

      <section className="semantic-management-section" hidden={tab !== 'evaluation'}>
        <div className="management-section-title"><strong>检索质量评测</strong><button className="btn btn-primary" onClick={() => setShowDatasetForm(current => !current)}>新建评测集</button></div>
        {showDatasetForm && <div className="management-form compact"><div className="management-form-grid"><label>名称<input className="form-input" style={inputStyle} value={datasetName} onChange={event => setDatasetName(event.target.value)} /></label><label>版本<input className="form-input" style={inputStyle} value={datasetVersion} onChange={event => setDatasetVersion(event.target.value)} /></label></div><div className="management-form-actions"><button className="btn btn-primary" disabled={busy} onClick={() => void createDataset()}>创建</button></div></div>}
        <div className="semantic-evaluation-controls"><select className="form-input" value={selectedDatasetId ?? ''} onChange={event => setSelectedDatasetId(Number(event.target.value) || null)}><option value="">选择评测集</option>{datasets.map(dataset => <option key={dataset.id} value={dataset.id}>{dataset.name} · {dataset.version} ({dataset.case_count ?? 0} 条)</option>)}</select><select className="form-input" value={selectedProfileId ?? ''} onChange={event => setSelectedProfileId(Number(event.target.value) || null)}><option value="">选择 Profile</option>{profiles.map(profile => <option key={profile.id} value={profile.id}>{profile.name}</option>)}</select><select className="form-input" value={selectedIndexId ?? ''} onChange={event => setSelectedIndexId(Number(event.target.value) || null)}><option value="">使用 Active 索引</option>{indexes.filter(index => !selectedProfileId || index.profile_id === selectedProfileId).map(index => <option key={index.id} value={index.id}>{index.index_version.slice(-17)} · {index.status}</option>)}</select><select className="form-input" value={evaluationMode} onChange={event => setEvaluationMode(event.target.value as 'keyword' | 'semantic' | 'hybrid')}><option value="keyword">关键词基线</option><option value="hybrid">混合</option><option value="semantic">语义</option></select><button className="btn btn-primary" disabled={busy || !selectedDatasetId || !selectedProfileId || casesDatasetId !== selectedDatasetId || !cases.some(item => item.enabled)} onClick={() => void runEvaluation()}>运行评测</button></div>
        <div className="management-section-title"><strong>评测样本</strong><span>{casesDatasetId === selectedDatasetId ? `${cases.filter(item => item.enabled).length} 个启用 / ${cases.length} 个总计` : '正在加载...'}</span><button className="btn btn-secondary" disabled={!selectedDatasetId} onClick={() => setShowCaseForm(current => !current)}>{showCaseForm ? '关闭' : '添加样本'}</button></div>
        {showCaseForm && <div className="management-form compact"><div className="management-form-grid"><label>Case Key<input className="form-input" style={inputStyle} value={caseKey} onChange={event => setCaseKey(event.target.value)} placeholder="battery-001" /></label><label>查询文本<input className="form-input" style={inputStyle} value={caseQuery} onChange={event => setCaseQuery(event.target.value)} /></label><label>数据库 ID<input className="form-input" style={inputStyle} value={caseDatabaseId} onChange={event => setCaseDatabaseId(event.target.value)} placeholder="可留空表示全局" /></label><label>相关专利 ID<input className="form-input" style={inputStyle} value={caseRelevantIds} onChange={event => setCaseRelevantIds(event.target.value)} placeholder="1, 2, 3" /></label><label>备注<input className="form-input" style={inputStyle} value={caseNotes} onChange={event => setCaseNotes(event.target.value)} /></label></div><div className="management-form-actions"><button className="btn btn-primary" disabled={busy} onClick={() => void createCase()}>保存 Case</button></div></div>}
        <div className="management-table"><table><thead><tr><th>Key</th><th>查询</th><th>相关专利</th><th>状态</th><th>操作</th></tr></thead><tbody>{cases.map(item => <tr key={item.id}><td className="semantic-mono">{item.case_key}</td><td>{item.query}{item.notes && <div className="semantic-muted">{item.notes}</div>}</td><td>{item.relevant_patent_ids.join(', ')}</td><td>{item.enabled ? '启用' : '已停用'}</td><td><button className="btn btn-secondary" disabled={busy} onClick={() => void toggleCase(item)}>{item.enabled ? '停用' : '启用'}</button> <button className="btn btn-secondary" disabled={busy} onClick={() => void deleteCase(item)}>删除</button></td></tr>)}</tbody></table>{cases.length === 0 && <div className="semantic-empty">请选择评测集并添加 Case。</div>}</div>
        <div className="management-table"><table><thead><tr><th>运行</th><th>Profile / 模式</th><th>状态</th><th>Recall@K</th><th>MRR</th><th>NDCG@K</th><th>时间</th></tr></thead><tbody>
          {runs.slice(0, 20).map(run => <tr key={run.id}><td>#{run.id}</td><td>{profileById.get(run.profile_id)?.name || run.profile_id} · {run.mode}</td><td>{run.status}</td><td>{Number(run.metrics.recall_at_k || 0).toFixed(3)}</td><td>{Number(run.metrics.mrr || 0).toFixed(3)}</td><td>{Number(run.metrics.ndcg_at_k || 0).toFixed(3)}</td><td>{dateText(run.completed_at)}</td></tr>)}
        </tbody></table>{runs.length === 0 && <div className="semantic-empty">还没有评测运行记录。</div>}</div>
      </section>
    </div>
  )
}
