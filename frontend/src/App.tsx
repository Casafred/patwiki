import { useCallback, useEffect, useMemo, useState } from 'react'
import { Navigate, Route, Routes, useLocation, useNavigate, useParams } from 'react-router-dom'
import Sidebar from './components/layout/Sidebar'
import PatentListPage from './components/patent/PatentListPage'
import PatentDetailPage from './components/patent/PatentDetailPage'
import StatsPage from './components/patent/StatsPage'
import SettingsPage from './components/settings/SettingsPage'
import FieldSettingsPage from './components/settings/FieldSettingsPage'
import SharingPage from './components/settings/SharingPage'
import AgentAnalysisPage from './components/analytics/AgentAnalysisPage'
import DashboardPage from './components/analytics/DashboardPage'
import AutomationPage from './components/settings/AutomationPage'
import ImportModal from './components/import/ImportModal'
import ImportHistoryPage from './components/import/ImportHistoryPage'
import AITaskMonitor from './components/ai/AITaskMonitor'
import ManagementPage from './components/management/ManagementPage'
import PublicPatentSharePage from './components/patent/PublicPatentSharePage'
import { SharedFormView } from './components/views/FormView'
import { productApi, customFieldApi, tagApi, projectApi, databaseApi, viewApi } from './api'
import { useAppStore } from './store'
import './index.css'

export type Page = 'patents' | 'stats' | 'dashboard' | 'automation' | 'settings' | 'fields' | 'management' | 'ai-tasks' | 'agent-analysis' | 'sharing' | 'import-history'

const pagePaths: Record<Page, string> = {
  patents: '/patents',
  stats: '/stats',
  dashboard: '/dashboard',
  automation: '/automation',
  settings: '/settings',
  fields: '/fields',
  management: '/management',
  'ai-tasks': '/ai-tasks',
  'agent-analysis': '/agent-analysis',
  sharing: '/sharing',
  'import-history': '/import-history',
}

function getPageFromPath(pathname: string): Page {
  if (pathname.startsWith('/stats')) return 'stats'
  if (pathname.startsWith('/dashboard')) return 'dashboard'
  if (pathname.startsWith('/automation')) return 'automation'
  if (pathname.startsWith('/settings')) return 'settings'
  if (pathname.startsWith('/fields')) return 'fields'
  if (pathname.startsWith('/management')) return 'management'
  if (pathname.startsWith('/ai-tasks')) return 'ai-tasks'
  if (pathname.startsWith('/agent-analysis')) return 'agent-analysis'
  if (pathname.startsWith('/sharing')) return 'sharing'
  if (pathname.startsWith('/import-history')) return 'import-history'
  return 'patents'
}

function PatentDetailRoute() {
  const navigate = useNavigate()
  const { patentId } = useParams<{ patentId: string }>()
  const parsedPatentId = Number(patentId)

  if (!Number.isInteger(parsedPatentId) || parsedPatentId <= 0) {
    return <Navigate to="/patents" replace />
  }

  return <PatentDetailPage patentId={parsedPatentId} onBack={() => navigate('/patents')} />
}

function PublicPatentShareRoute() {
  const { token } = useParams<{ token: string }>()
  return <PublicPatentSharePage token={token || ''} />
}

function SharedFormRoute() {
  const { token } = useParams<{ token: string }>()
  return <SharedFormView token={token || ''} />
}

function WorkspaceApp() {
  const location = useLocation()
  const navigate = useNavigate()
  const currentPage = useMemo(() => getPageFromPath(location.pathname), [location.pathname])
  const [showImport, setShowImport] = useState(false)
  const {
    setProducts, setCustomFields, setTags, setProjects,
    setDatabases, setCurrentDatabaseId, currentDatabaseId,
    setViews, setCurrentViewId, currentViewId,
  } = useAppStore()

  useEffect(() => {
    if (currentDatabaseId === null) return
    const loadViews = async () => {
      try {
        let views = await viewApi.list(currentDatabaseId)
        if (views.length === 0) {
          views = [await viewApi.master(currentDatabaseId)]
        }
        setViews(views)
        const preferred = views.find(view => view.is_department_master) || views[0]
        setCurrentViewId(preferred?.id ?? null)
      } catch (e) {
        console.error('Failed to load views:', e)
        setViews([])
        setCurrentViewId(null)
      }
    }
    void loadViews()
  }, [currentDatabaseId, setCurrentViewId, setViews])

  const loadMeta = useCallback(async () => {
    try {
      const [products, fields, tags, projects, databases] = await Promise.all([
        productApi.list(),
        customFieldApi.list(),
        tagApi.list(),
        projectApi.list(),
        databaseApi.list(),
      ])
      setProducts(products)
      setCustomFields(fields)
      setTags(tags)
      setProjects(projects)
      setDatabases(databases)
      // 默认选中第一个库（优先 is_default）
      if (currentDatabaseId === null && databases.length > 0) {
        const def = databases.find(d => d.is_default) || databases[0]
        setCurrentDatabaseId(def.id)
      }
    } catch (e) {
      console.error('Failed to load meta data:', e)
    }
  }, [currentDatabaseId, setCustomFields, setCurrentDatabaseId, setDatabases, setProducts, setProjects, setTags])

  useEffect(() => {
    void loadMeta()
  }, [loadMeta])

  const handleImportSuccess = () => {
    setShowImport(false)
    if (currentPage === 'patents' && !location.pathname.includes('/patents/')) {
      window.location.reload()
    }
  }

  const handlePatentClick = (id: number) => {
    navigate(`/patents/${id}`)
  }

  const handleNavigate = (page: Page) => {
    navigate(pagePaths[page])
  }

  return (
    <div className="app-container">
      <Sidebar
        currentPage={currentPage}
        onNavigate={handleNavigate}
      />
      <div className="main-content">
        <header className="header">
          <div className="header-actions">
            <button className="btn btn-primary" onClick={() => setShowImport(true)}>
              导入Excel
            </button>
            <button
              className="btn btn-secondary"
              onClick={() => handleNavigate('ai-tasks')}
            >
              AI任务
            </button>
            <button
              className="btn btn-secondary"
              onClick={() => handleNavigate('stats')}
            >
              统计
            </button>
            <button
              className="btn btn-secondary"
              onClick={() => handleNavigate('settings')}
            >
              设置
            </button>
          </div>
        </header>
        <div className="content-area">
          <Routes>
            <Route index element={<Navigate to="/patents" replace />} />
            <Route path="patents" element={<PatentListPage onPatentClick={handlePatentClick} viewId={currentViewId} />} />
            <Route path="patents/:patentId" element={<PatentDetailRoute />} />
            <Route path="stats" element={<StatsPage />} />
            <Route path="dashboard" element={<DashboardPage />} />
            <Route path="automation" element={<AutomationPage />} />
            <Route path="settings" element={<SettingsPage />} />
            <Route path="fields" element={<FieldSettingsPage />} />
            <Route path="management" element={<ManagementPage />} />
            <Route path="sharing" element={<SharingPage />} />
            <Route path="import-history" element={<ImportHistoryPage />} />
            <Route path="ai-tasks" element={<AITaskMonitor />} />
            <Route path="agent-analysis" element={<AgentAnalysisPage />} />
            <Route path="*" element={<Navigate to="/patents" replace />} />
          </Routes>
        </div>
      </div>

      {showImport && (
        <ImportModal
          onClose={() => setShowImport(false)}
          onSuccess={handleImportSuccess}
        />
      )}
    </div>
  )
}

function App() {
  const location = useLocation()
  if (location.pathname.startsWith('/share/patents/')) {
    return (
      <Routes>
        <Route path="share/patents/:token" element={<PublicPatentShareRoute />} />
      </Routes>
    )
  }
  if (location.pathname.startsWith('/shared-form/')) {
    return (
      <Routes>
        <Route path="shared-form/:token" element={<SharedFormRoute />} />
      </Routes>
    )
  }
  return <WorkspaceApp />
}

export default App
