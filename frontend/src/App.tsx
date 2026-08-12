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
import Icon from './components/common/Icon'
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
  const [sidebarOpen, setSidebarOpen] = useState(false)
  const [sidebarCollapsed, setSidebarCollapsed] = useState(() => {
    try {
      return localStorage.getItem('patwiki_sidebar_collapsed') === '1'
    } catch {
      return false
    }
  })
  const {
    setProducts, setCustomFields, setTags, setProjects,
    setDatabases, setCurrentDatabaseId, currentDatabaseId,
    setViews, setCurrentViewId, currentViewId, databases,
  } = useAppStore()
  const routeDatabaseId = getDatabaseIdFromPath(location.pathname)
  const queryDatabaseId = Number(searchParams.get('db'))
  const requestedDatabaseId = routeDatabaseId || (Number.isInteger(queryDatabaseId) && queryDatabaseId > 0 ? queryDatabaseId : null)

  useEffect(() => {
    const activeDatabaseId = requestedDatabaseId ?? currentDatabaseId
    if (activeDatabaseId === null) return
    // 防止快速切库/翻页时旧请求覆盖新状态：
    // searchParamsString 会让本 effect 在每次 URL 变化（含翻页）时重跑，
    // 若不取消前一次未完成的请求，后到的旧结果会用旧库的视图覆盖当前视图。
    let cancelled = false
    const loadViews = async () => {
      try {
        let views = await viewApi.list(activeDatabaseId)
        if (cancelled) return
        if (views.length === 0) {
          views = [await viewApi.master(activeDatabaseId)]
        }
        if (cancelled) return
        setViews(views)
        const requestedViewId = Number(new URLSearchParams(searchParamsString).get('view'))
        const preferred = views.find(view => view.id === requestedViewId)
          || views.find(view => view.is_department_master)
          || views[0]
        setCurrentViewId(preferred?.id ?? null)
      } catch (e) {
        if (cancelled) return
        console.error('Failed to load views:', e)
        setViews([])
        setCurrentViewId(null)
      }
    }
    void loadViews()
    return () => { cancelled = true }
  }, [currentDatabaseId, requestedDatabaseId, searchParamsString, setCurrentViewId, setViews])

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
    const activeDatabaseId = requestedDatabaseId ?? currentDatabaseId
    navigate(activeDatabaseId ? `/db/${activeDatabaseId}/patents/${id}` : `/patents/${id}`)
  }

  const handleNavigate = (page: Page, databaseId = requestedDatabaseId ?? currentDatabaseId) => {
    navigate(databaseId ? `/db/${databaseId}/${pageSegments[page]}` : `/${pageSegments[page]}`)
    setSidebarOpen(false)
  }

  const handleSidebarCollapse = (collapsed: boolean) => {
    setSidebarCollapsed(collapsed)
    try {
      localStorage.setItem('patwiki_sidebar_collapsed', collapsed ? '1' : '0')
    } catch {
      // Preferences are optional when storage is unavailable.
    }
  }

  const pageTitles: Record<Page, string> = {
    patents: '专利工作区',
    stats: '数据看板',
    dashboard: '可配置仪表盘',
    automation: '自动化规则',
    settings: '系统设置',
    fields: '字段管理',
    management: '管理台',
    'ai-tasks': 'AI 任务',
    'agent-analysis': '智能分析',
    sharing: '协作与权限',
    'import-history': '导入历史',
  }
  const activeDatabaseId = requestedDatabaseId ?? currentDatabaseId
  const currentDatabase = databases.find(database => database.id === activeDatabaseId)

  return (
    <div className={`app-container ${sidebarOpen ? 'sidebar-open' : ''} ${sidebarCollapsed ? 'sidebar-collapsed' : ''}`}>
      <Sidebar
        currentPage={currentPage}
        onNavigate={handleNavigate}
        collapsed={sidebarCollapsed}
        onToggleCollapse={handleSidebarCollapse}
      />
      <button className="sidebar-scrim" aria-label="关闭导航" onClick={() => setSidebarOpen(false)} />
      <div className="main-content">
        <header className="header">
          <button className="mobile-nav-toggle" onClick={() => setSidebarOpen(true)} aria-label="打开导航" title="打开导航"><Icon name="menu" /></button>
          <div className="header-context">
            <div className="header-kicker">{currentDatabase?.name || 'PatWiki'}</div>
            <h2>{pageTitles[currentPage]}</h2>
          </div>
          <div className="header-actions">
            <button className="btn btn-primary" onClick={() => setShowImport(true)}>
              导入数据
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
              数据看板
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
