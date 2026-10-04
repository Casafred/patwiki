import { useState } from 'react'
import SemanticSearchManagement from '../management/SemanticSearchManagement'
import SettingsPage from '../settings/SettingsPage'
import AITaskMonitor from './AITaskMonitor'
import FieldSettingsPage from '../settings/FieldSettingsPage'
import ExternalSyncPage from '../settings/ExternalSyncPage'

type CenterTab = 'models' | 'fields' | 'semantic' | 'mcp' | 'tasks'

export default function AICapabilityCenter({ initialTab = 'models' }: { initialTab?: CenterTab }) {
  const [tab, setTab] = useState<CenterTab>(initialTab)
  const [fieldTab, setFieldTab] = useState<'fields' | 'tasks'>(initialTab === 'tasks' ? 'tasks' : 'fields')
  const [semanticTab, setSemanticTab] = useState<'overview' | 'models'>('overview')
  return <div className="workspace-page ai-capability-center"><div className="workspace-page-shell">
    <div className="ai-center-hero"><div><span className="ai-center-eyebrow">AI PLATFORM</span><h2 className="page-title">AI 能力管理中心</h2><p className="page-subtitle">统一管理常规 LLM、JEV、Embedding、Rerank 供应商和 AI 任务。</p></div><div className="ai-center-health"><span className="ai-center-health-dot" />能力配置集中管理</div></div>
    <nav className="ai-center-tabs" aria-label="AI 能力模块"><button className={tab === 'models' ? 'active' : ''} onClick={() => setTab('models')}>模型与供应商</button><button className={tab === 'fields' || tab === 'tasks' ? 'active' : ''} onClick={() => setTab('fields')}>自定义字段与AI抽取</button><button className={tab === 'semantic' ? 'active' : ''} onClick={() => setTab('semantic')}>语义检索工作台</button><button className={tab === 'mcp' ? 'active' : ''} onClick={() => setTab('mcp')}>MCP 与外部更新</button></nav>
    <div className="ai-center-content">{tab === 'models' && <SettingsPage onSemanticModels={() => { setSemanticTab('models'); setTab('semantic') }} />}{(tab === 'fields' || tab === 'tasks') && <><nav className="workspace-subtabs" aria-label="字段与抽取"><button className={fieldTab === 'fields' ? 'active' : ''} onClick={() => setFieldTab('fields')}>自定义字段</button><button className={fieldTab === 'tasks' ? 'active' : ''} onClick={() => setFieldTab('tasks')}>AI抽取任务记录</button></nav>{fieldTab === 'fields' ? <FieldSettingsPage /> : <AITaskMonitor />}</>}{tab === 'semantic' && <SemanticSearchManagement initialTab={semanticTab} />}{tab === 'mcp' && <ExternalSyncPage />}</div>
  </div></div>
}
