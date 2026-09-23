import { useState } from 'react'
import SemanticSearchManagement from '../management/SemanticSearchManagement'
import SettingsPage from '../settings/SettingsPage'
import AITaskMonitor from './AITaskMonitor'

type CenterTab = 'models' | 'semantic' | 'tasks'

export default function AICapabilityCenter() {
  const [tab, setTab] = useState<CenterTab>('models')
  return <div className="workspace-page ai-capability-center"><div className="workspace-page-shell">
    <div className="ai-center-hero"><div><span className="ai-center-eyebrow">AI PLATFORM</span><h2 className="page-title">AI 能力管理中心</h2><p className="page-subtitle">统一管理常规 LLM、JEV、Embedding、Rerank 供应商和 AI 任务。</p></div><div className="ai-center-health"><span className="ai-center-health-dot" />能力配置集中管理</div></div>
    <nav className="ai-center-tabs" aria-label="AI 能力模块"><button className={tab === 'models' ? 'active' : ''} onClick={() => setTab('models')}>模型与供应商</button><button className={tab === 'semantic' ? 'active' : ''} onClick={() => setTab('semantic')}>语义检索工作台</button><button className={tab === 'tasks' ? 'active' : ''} onClick={() => setTab('tasks')}>任务与运行记录</button></nav>
    <div className="ai-center-content">{tab === 'models' && <SettingsPage />}{tab === 'semantic' && <SemanticSearchManagement />}{tab === 'tasks' && <AITaskMonitor />}</div>
  </div></div>
}
