import { useCallback, useEffect, useMemo, useState, type ReactNode } from 'react'
import { Navigate, Route, Routes, useLocation, useNavigate, useParams, useSearchParams } from 'react-router-dom'
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

const pageSegments: Record<Page, string> = {
  patents: 'patents',
  stats: 'stats',
  dashboard: 'dashboard',
  automation: 'automation',
  settings: 'settings',
  fields: 'fields',
  management: 'management',
  'ai-tasks': 'ai-tasks',
  'agent-analysis': 'agent-analysis',
  sharing: 'sharing',
  'import-history': 'import-history',
}

function getPageFromPath(pathname: string): Page {
  const segment = pathname.match(/^\/db\/\d+\/([^/]+)/)?.[1] || pathname.split('/')[1]
  const page = Object.entries(pageSegments).find(([, value]) => value === segment)?.[0]
  if (page) return page as Page
  return 'patents'
}

function getDatabaseIdFromPath(pathname: string): number | null {
  const value = pathname.match(/^\/db\/(\d+)(?:\/|$)/)?.[1]
  const databaseId = value ? Number(value) : NaN
  return Number.isInteger(databaseId) && databaseId > 0 ? databaseId : null
}

function DatabaseRouteScope({ children }: { children: ReactNode }) {
  const { databaseId } = useParams<{ databaseId: string }>()
  const parsedDatabaseId = Number(databaseId)
  const { setCurrentDatabaseId, setCurrentViewId } = useAppStore()

  useEffect(() => {
    if (!Number.isInteger(parsedDatabaseId) || parsedDatabaseId <= 0) return
    setCurrentDatabaseId(parsedDatabaseId)
    setCurrentViewId(null)
  }, [parsedDatabaseId, setCurrentDatabaseId, setCurrentViewId])

  if (!Number.isInteger(parsedDatabaseId) || parsedDatabaseId <= 0) {
    return <Navigate to="/patents" replace />
  }
  return <>{children}</>
}

function PatentDetailRoute() {
  const navigate = useNavigate()
  const { patentId, databaseId } = useParams<{ patentId: string; databaseId?: string }>()
  const parsedPatentId = Number(patentId)

  if (!Number.isInteger(parsedPatentId) || parsedPatentId <= 0) {
    return <Navigate to={databaseId ? `/db/${databaseId}/patents` : '/patents'} replace />
  }

  return <PatentDetailPage patentId={parsedPatentId} onBack={() => navigate(databaseId ? `/db/${databaseId}/patents` : '/patents')} />
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
  const [searchParams, setSearchParams] = useSearchParams()
  const searchParamsString = searchParams.toString()
  const currentPage = useMemo(() => getPageFromPath(location.pathname), [location.pathname])
  const [showImport, setShowImport] = useState(false)
  const {
    setProducts, setCustomFields, setTags, setProjects,
    setDatabases, setCurrentDatabaseId, currentDatabaseId,
    setViews, setCurrentViewId, currentViewId,
  } = useAppStore()
  const routeDatabaseId = getDatabaseIdFromPath(location.pathname)
  const queryDatabaseId = Number(searchParams.get('db'))
  const requestedDatabaseId = routeDatabaseId || (Number.isInteger(queryDatabaseId) && queryDatabaseId > 0 ? queryDatabaseId : null)

  useEffect(() => {
    if (currentDatabaseId === null) return
    const loadViews = async () => {
      try {
        let views = await viewApi.list(currentDatabaseId)
        if (views.length === 0) {
          views = [await viewApi.master(currentDatabaseId)]
        }
        setViews(views)
        const requestedViewId = Number(new URLSearchParams(searchParamsString).get('view'))
        const preferred = views.find(view => view.id === requestedViewId)
          || views.find(view => view.is_department_master)
          || views[0]
        setCurrentViewId(preferred?.id ?? null)
      } catch (e) {
        console.error('Failed to load views:', e)
        setViews([])
        setCurrentViewId(null)
      }
    }
    void loadViews()
  }, [currentDatabaseId, searchParamsString, setCurrentViewId, setViews])

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
      const requestedDatabase = requestedDatabaseId !== null
        ? databases.find(database => database.id === requestedDatabaseId)
        : undefined
      // URL 中的库优先于本地默认库，保证刷新后仍停留在原工作区。
      if (requestedDatabase) {
        if (currentDatabaseId !== requestedDatabase.id) setCurrentDatabaseId(requestedDatabase.id)
      } else if (currentDatabaseId === null && databases.length > 0) {
        const def = databases.find(d => d.is_default) || databases[0]
        setCurrentDatabaseId(def.id)
      }
    } catch (e) {
      console.error('Failed to load meta data:', e)
    }
  }, [currentDatabaseId, requestedDatabaseId, setCustomFields, setCurrentDatabaseId, setDatabases, setProducts, setProjects, setTags])

  useEffect(() => {
    void loadMeta()
  }, [loadMeta])

  useEffect(() => {
    if (currentDatabaseId === null || currentViewId === null) return
    const next = new URLSearchParams(searchParams)
    if (!routeDatabaseId) next.set('db', String(currentDatabaseId))
    next.set('view', String(currentViewId))
    if (next.toString() !== searchParamsString) setSearchParams(next, { replace: true })
  }, [currentDatabaseId, currentViewId, routeDatabaseId, searchParams, searchParamsString, setSearchParams])

  const handleImportSuccess = () => {
    setShowImport(false)
    if (currentPage === 'patents' && !location.pathname.includes('/patents/')) {
      window.location.reload()
    }
  }

  const handlePatentClick = (id: number) => {
    navigate(currentDatabaseId ? `/db/${currentDatabaseId}/patents/${id}` : `/patents/${id}`)
  }

  const handleNavigate = (page: Page) => {
    navigate(currentDatabaseId ? `/db/${currentDatabaseId}/${pageSegments[page]}` : `/${pageSegments[page]}`)
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
            <Route index element={<Navigate to={currentDatabaseId ? `/db/${currentDatabaseId}/patents` : '/patents'} replace />} />
            <Route path="db/:databaseId/patents" element={<DatabaseRouteScope><PatentListPage onPatentClick={handlePatentClick} viewId={currentViewId} /></DatabaseRouteScope>} />
            <Route path="db/:databaseId/patents/:patentId" element={<DatabaseRouteScope><PatentDetailRoute /></DatabaseRouteScope>} />
            <Route path="db/:databaseId/stats" element={<DatabaseRouteScope><StatsPage /></DatabaseRouteScope>} />
            <Route path="db/:databaseId/dashboard" element={<DatabaseRouteScope><DashboardPage /></DatabaseRouteScope>} />
            <Route path="db/:databaseId/automation" element={<DatabaseRouteScope><AutomationPage /></DatabaseRouteScope>} />
            <Route path="db/:databaseId/settings" element={<DatabaseRouteScope><SettingsPage /></DatabaseRouteScope>} />
            <Route path="db/:databaseId/fields" element={<DatabaseRouteScope><FieldSettingsPage /></DatabaseRouteScope>} />
            <Route path="db/:databaseId/management" element={<DatabaseRouteScope><ManagementPage /></DatabaseRouteScope>} />
            <Route path="db/:databaseId/sharing" element={<DatabaseRouteScope><SharingPage /></DatabaseRouteScope>} />
            <Route path="db/:databaseId/import-history" element={<DatabaseRouteScope><ImportHistoryPage /></DatabaseRouteScope>} />
            <Route path="db/:databaseId/ai-tasks" element={<DatabaseRouteScope><AITaskMonitor /></DatabaseRouteScope>} />
            <Route path="db/:databaseId/agent-analysis" element={<DatabaseRouteScope><AgentAnalysisPage /></DatabaseRouteScope>} />
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
