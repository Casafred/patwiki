import { useState, useEffect } from 'react'
import Sidebar from './components/layout/Sidebar'
import PatentListPage from './components/patent/PatentListPage'
import StatsPage from './components/patent/StatsPage'
import ImportModal from './components/import/ImportModal'
import { productApi, customFieldApi, tagApi } from './api'
import { useAppStore } from './store'
import type { Product, CustomField, Tag } from './types'
import './index.css'

type Page = 'patents' | 'stats' | 'settings'

function App() {
  const [currentPage, setCurrentPage] = useState<Page>('patents')
  const [showImport, setShowImport] = useState(false)
  const { setProducts, setCustomFields, setTags, setProjects } = useAppStore()

  useEffect(() => {
    loadMeta()
  }, [])

  const loadMeta = async () => {
    try {
      const [products, fields, tags, projects] = await Promise.all([
        productApi.list(),
        customFieldApi.list(),
        tagApi.list(),
        fetch('/api/projects').then(r => r.json()),
      ])
      setProducts(products)
      setCustomFields(fields)
      setTags(tags)
      setProjects(projects)
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

  return (
    <div className="app-container">
      <Sidebar
        currentPage={currentPage}
        onNavigate={setCurrentPage}
        onImport={() => setShowImport(true)}
      />
      <div className="main-content">
        <header className="header">
          <div className="header-search">
            <span className="search-icon">🔍</span>
            <input placeholder="搜索专利号、标题、申请人、发明人..." />
          </div>
          <div className="header-actions">
            <button className="btn btn-primary" onClick={() => setShowImport(true)}>
              📥 导入Excel
            </button>
            <button className="btn btn-secondary" onClick={() => setCurrentPage('stats')}>
              📊 统计
            </button>
          </div>
        </header>
        <div className="content-area">
          {currentPage === 'patents' && <PatentListPage />}
          {currentPage === 'stats' && <StatsPage />}
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
