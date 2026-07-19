import { useState, useEffect } from 'react'
import Sidebar from './components/layout/Sidebar'
import PatentListPage from './components/patent/PatentListPage'
import PatentDetailPage from './components/patent/PatentDetailPage'
import StatsPage from './components/patent/StatsPage'
import SettingsPage from './components/settings/SettingsPage'
import ImportModal from './components/import/ImportModal'
import AITaskMonitor from './components/ai/AITaskMonitor'
import { productApi, customFieldApi, tagApi, projectApi, databaseApi } from './api'
import { useAppStore } from './store'
import './index.css'

type Page = 'patents' | 'stats' | 'settings' | 'ai-tasks'

function App() {
  const [currentPage, setCurrentPage] = useState<Page>('patents')
  const [showImport, setShowImport] = useState(false)
  const [selectedPatentId, setSelectedPatentId] = useState<number | null>(null)
  const {
    setProducts, setCustomFields, setTags, setProjects,
    setDatabases, setCurrentDatabaseId, currentDatabaseId,
  } = useAppStore()

  useEffect(() => {
    loadMeta()
  }, [])

  const loadMeta = async () => {
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
  }

  const handleImportSuccess = () => {
    setShowImport(false)
    if (currentPage === 'patents') {
      window.location.reload()
    }
  }

  const handlePatentClick = (id: number) => {
    setSelectedPatentId(id)
  }

  const handleBackToList = () => {
    setSelectedPatentId(null)
  }

  return (
    <div className="app-container">
      <Sidebar
        currentPage={currentPage}
        onNavigate={(p) => {
          setCurrentPage(p)
          setSelectedPatentId(null)
        }}
      />
      <div className="main-content">
        <header className="header">
          <div className="header-actions">
            <button className="btn btn-primary" onClick={() => setShowImport(true)}>
              导入Excel
            </button>
            <button
              className="btn btn-secondary"
              onClick={() => { setCurrentPage('ai-tasks'); setSelectedPatentId(null) }}
            >
              AI任务
            </button>
            <button
              className="btn btn-secondary"
              onClick={() => { setCurrentPage('stats'); setSelectedPatentId(null) }}
            >
              统计
            </button>
            <button
              className="btn btn-secondary"
              onClick={() => { setCurrentPage('settings'); setSelectedPatentId(null) }}
            >
              设置
            </button>
          </div>
        </header>
        <div className="content-area">
          {selectedPatentId ? (
            <PatentDetailPage patentId={selectedPatentId} onBack={handleBackToList} />
          ) : currentPage === 'patents' ? (
            <PatentListPage onPatentClick={handlePatentClick} />
          ) : currentPage === 'stats' ? (
            <StatsPage />
          ) : currentPage === 'settings' ? (
            <SettingsPage />
          ) : currentPage === 'ai-tasks' ? (
            <AITaskMonitor />
          ) : null}
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

export default App
