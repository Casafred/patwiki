import { useState, useEffect, useCallback } from 'react'
import { productApi, databaseApi } from '../../api'
import { useAppStore } from '../../store'
import ViewSwitcher from '../views/ViewSwitcher'
import type { Page } from '../../App'
import type { PatentDatabase } from '../../types'
import Icon from '../common/Icon'

const SIDEBAR_SECTIONS_STORAGE_KEY = 'patwiki_sidebar_sections'
const SIDEBAR_SUBSECTIONS_STORAGE_KEY = 'patwiki_sidebar_subsections'
type SidebarSectionKey = 'workspace' | 'intelligence' | 'views' | 'products' | 'management'
type SidebarSubsectionKey = 'analysis' | 'automation' | 'data' | 'system'
type SidebarSections = Record<SidebarSectionKey, boolean>
type SidebarSubsections = Record<SidebarSubsectionKey, boolean>

const DEFAULT_SIDEBAR_SECTIONS: SidebarSections = {
  workspace: true,
  intelligence: true,
  views: true,
  products: true,
  management: true,
}

const DEFAULT_SIDEBAR_SUBSECTIONS: SidebarSubsections = {
  analysis: true,
  automation: true,
  data: true,
  system: true,
}

function readSidebarSections(): SidebarSections {
  try {
    const parsed = JSON.parse(localStorage.getItem(SIDEBAR_SECTIONS_STORAGE_KEY) || '{}') as Partial<SidebarSections>
    return Object.fromEntries(
      Object.keys(DEFAULT_SIDEBAR_SECTIONS).map(key => [key, parsed[key as SidebarSectionKey] !== false]),
    ) as SidebarSections
  } catch {
    return DEFAULT_SIDEBAR_SECTIONS
  }
}

function readSidebarSubsections(): SidebarSubsections {
  try {
    const parsed = JSON.parse(localStorage.getItem(SIDEBAR_SUBSECTIONS_STORAGE_KEY) || '{}') as Partial<SidebarSubsections>
    return Object.fromEntries(
      Object.keys(DEFAULT_SIDEBAR_SUBSECTIONS).map(key => [key, parsed[key as SidebarSubsectionKey] !== false]),
    ) as SidebarSubsections
  } catch {
    return DEFAULT_SIDEBAR_SUBSECTIONS
  }
}

interface SidebarProps {
  currentPage: Page
  onNavigate: (page: Page, databaseId?: number | null) => void
  collapsed: boolean
  onToggleCollapse: (collapsed: boolean) => void
}

export default function Sidebar({ currentPage, onNavigate, collapsed, onToggleCollapse }: SidebarProps) {
  const {
    products, currentProductId, setCurrentProductId, setProducts,
    databases, currentDatabaseId, setCurrentDatabaseId, setDatabases,
    currentUser, setCurrentViewId,
  } = useAppStore()
  const [showAddProduct, setShowAddProduct] = useState(false)
  const [newProductName, setNewProductName] = useState('')
  const [showAddDatabase, setShowAddDatabase] = useState(false)
  const [newDbName, setNewDbName] = useState('')
  const [newDbDesc, setNewDbDesc] = useState('')
  const [expandedSections, setExpandedSections] = useState<SidebarSections>(() => readSidebarSections())
  const [expandedSubsections, setExpandedSubsections] = useState<SidebarSubsections>(() => readSidebarSubsections())
  const [pendingDeleteDatabase, setPendingDeleteDatabase] = useState<PatentDatabase | null>(null)
  const [deletingDatabase, setDeletingDatabase] = useState(false)

  const toggleSection = (key: SidebarSectionKey) => {
    setExpandedSections(previous => {
      const next = { ...previous, [key]: !previous[key] }
      try { localStorage.setItem(SIDEBAR_SECTIONS_STORAGE_KEY, JSON.stringify(next)) } catch { /* preferences are optional */ }
      return next
    })
  }

  const renderSectionToggle = (key: SidebarSectionKey, label: string) => (
    <button
      type="button"
      className="sidebar-section-title sidebar-section-toggle"
      onClick={() => toggleSection(key)}
      aria-expanded={expandedSections[key]}
    >
      <span>{label}</span>
      <Icon name={expandedSections[key] ? 'chevron-down' : 'chevron-right'} size={13} />
    </button>
  )

  const renderSubsectionToggle = (key: SidebarSubsectionKey, label: string) => (
    <button
      type="button"
      className="sidebar-subsection-toggle"
      onClick={() => setExpandedSubsections(previous => {
        const next = { ...previous, [key]: !previous[key] }
        try { localStorage.setItem(SIDEBAR_SUBSECTIONS_STORAGE_KEY, JSON.stringify(next)) } catch { /* preferences are optional */ }
        return next
      })}
      aria-expanded={expandedSubsections[key]}
    >
      <span>{label}</span>
      <Icon name={expandedSubsections[key] ? 'chevron-down' : 'chevron-right'} size={12} />
    </button>
  )

  // 打通关联：监听当前库切换，重新加载产品列表，patent_count 按当前库过滤
  const reloadProducts = useCallback(async () => {
    try {
      const params = currentDatabaseId === null || currentDatabaseId === undefined
        ? {}
        : { database_id: currentDatabaseId }
      const refreshed = await productApi.list(params)
      setProducts(refreshed)
    } catch (e) {
      console.error('Failed to reload products:', e)
    }
  }, [currentDatabaseId, setProducts])

  useEffect(() => {
    reloadProducts()
  }, [reloadProducts])

  const handleProductClick = (productId: number | null) => {
    setCurrentProductId(productId)
    onNavigate('patents', currentDatabaseId)
  }

  const handleAddProduct = async () => {
    if (!newProductName.trim()) return
    try {
      const product = await productApi.create({ name: newProductName.trim() })
      // 不再整页刷新，只刷新产品列表
      await reloadProducts()
      setCurrentProductId(product.id)
      setNewProductName('')
      setShowAddProduct(false)
      onNavigate('patents', currentDatabaseId)
    } catch {
      alert('创建产品失败')
    }
  }

  // P0-11：库切换
  const handleDatabaseChange = (id: number) => {
    if (id === currentDatabaseId) return
    // URL is the source of truth; App loads the new database's views after navigation.
    setCurrentProductId(null)
    onNavigate('patents', id)
  }

  // P0-11：新建库
  const handleAddDatabase = async () => {
    if (!newDbName.trim()) return
    try {
      const db = await databaseApi.create({
        name: newDbName.trim(),
        description: newDbDesc.trim() || undefined,
        owner_id: currentUser?.id ?? null,
      })
      const refreshed = await databaseApi.list()
      setDatabases(refreshed)
      setCurrentDatabaseId(db.id)
      setNewDbName('')
      setNewDbDesc('')
      setShowAddDatabase(false)
      setCurrentProductId(null)
      setCurrentViewId(null)
      onNavigate('patents', db.id)
    } catch {
      alert('创建库失败')
    }
  }

  // 整库删除：级联删除库内所有专利后删库（默认库不可删）
  const requestDeleteDatabase = () => {
    if (currentDatabaseId === null || currentDatabaseId === undefined) {
      alert('请先选择要删除的库')
      return
    }
    const db = databases.find(d => d.id === currentDatabaseId)
    if (!db) {
      alert('未找到当前库')
      return
    }
    if (db.is_default) {
      alert('默认数据库不可删除')
      return
    }
    setPendingDeleteDatabase(db)
  }

  const handleDeleteDatabase = async () => {
    const db = pendingDeleteDatabase
    if (!db || deletingDatabase) return
    setDeletingDatabase(true)
    try {
      await databaseApi.delete(db.id, true)
      const refreshed = await databaseApi.list()
      setDatabases(refreshed)
      // 切到第一个可用库
      if (refreshed.length > 0) {
        setCurrentDatabaseId(refreshed[0].id)
      } else {
        setCurrentDatabaseId(null)
      }
      onNavigate('patents', refreshed.length > 0 ? refreshed[0].id : null)
    } catch (e: unknown) {
      const detail = e && typeof e === 'object' && 'response' in e
        ? (e as { response?: { data?: { detail?: unknown } } }).response?.data?.detail
        : undefined
      alert(typeof detail === 'string' ? detail : '删除库失败，请检查后端日志后重试')
    } finally {
      setDeletingDatabase(false)
      setPendingDeleteDatabase(null)
    }
  }

  return (
    <aside className="sidebar">
      <div className="sidebar-brand">
        <div className="brand-mark">PW</div>
        <div>
          <h1>PatWiki</h1>
          <p>专利知识工作台</p>
        </div>
        <button
          type="button"
          className="sidebar-collapse-toggle"
          onClick={() => onToggleCollapse(!collapsed)}
          aria-label={collapsed ? '展开导航栏' : '收起导航栏'}
          title={collapsed ? '展开导航栏' : '收起导航栏'}
        >
          <Icon name={collapsed ? 'chevron-right' : 'chevron-left'} />
        </button>
      </div>

      <div className="sidebar-database">
        <div className="sidebar-label-row">
          <span className="sidebar-label">当前专利库</span>
          <span className="sidebar-count">{databases.length}</span>
        </div>
        <select
          className="database-select"
          value={currentDatabaseId ?? ''}
          onChange={(e) => handleDatabaseChange(Number(e.target.value))}
          aria-label="选择当前专利库"
        >
          {databases.length === 0 && <option value="">无可用库</option>}
          {databases.map(d => (
            <option key={d.id} value={d.id}>{d.name}</option>
          ))}
        </select>
        {currentDatabaseId !== null && databases.find(d => d.id === currentDatabaseId) && (
          <div className="database-meta">
            {databases.find(d => d.id === currentDatabaseId)?.patent_count ?? 0} 条专利
          </div>
        )}
        {showAddDatabase ? (
          <div className="sidebar-form">
            <input className="sidebar-input" placeholder="库名称" value={newDbName} onChange={(e) => setNewDbName(e.target.value)} autoFocus />
            <input className="sidebar-input" placeholder="描述（可选）" value={newDbDesc} onChange={(e) => setNewDbDesc(e.target.value)} />
            <div className="sidebar-form-actions">
              <button className="sidebar-action primary" onClick={handleAddDatabase}>创建</button>
              <button className="sidebar-action" onClick={() => { setShowAddDatabase(false); setNewDbName(''); setNewDbDesc('') }}>取消</button>
            </div>
          </div>
        ) : (
          <div className="sidebar-inline-actions">
            <button className="sidebar-link" onClick={() => setShowAddDatabase(true)}>+ 新建专利库</button>
            {currentDatabaseId !== null && databases.find(d => d.id === currentDatabaseId && !d.is_default) && (
              <button className="sidebar-link danger" onClick={requestDeleteDatabase} title="删除当前库及库内专利">删除</button>
            )}
          </div>
        )}
      </div>

      <nav className="sidebar-nav">
        {renderSectionToggle('workspace', '工作台')}
        {expandedSections.workspace && <div className="sidebar-section-content">
          <button className={`nav-item ${currentPage === 'patents' && !currentProductId ? 'active' : ''}`} onClick={() => handleProductClick(null)} title="全部专利"><Icon name="table" /><span className="nav-label">全部专利</span></button>
          <button className={`nav-item ${currentPage === 'stats' ? 'active' : ''}`} onClick={() => onNavigate('stats', currentDatabaseId)} title="数据看板"><Icon name="chart" /><span className="nav-label">数据看板</span></button>
          <button className={`nav-item ${currentPage === 'dashboard' ? 'active' : ''}`} onClick={() => onNavigate('dashboard', currentDatabaseId)} title="可配置仪表盘"><Icon name="dashboard" /><span className="nav-label">可配置仪表盘</span></button>
        </div>}

        {renderSectionToggle('intelligence', '智能与自动化')}
        {expandedSections.intelligence && <div className="sidebar-section-content">
          <div className="sidebar-subsection">
            {renderSubsectionToggle('analysis', '分析与任务')}
            {expandedSubsections.analysis && <div className="sidebar-subsection-content">
              <button className={`nav-item ${currentPage === 'agent-analysis' ? 'active' : ''}`} onClick={() => onNavigate('agent-analysis', currentDatabaseId)} title="智能分析"><Icon name="sparkles" /><span className="nav-label">智能分析</span></button>
              <button className={`nav-item ${currentPage === 'ai-tasks' ? 'active' : ''}`} onClick={() => onNavigate('ai-tasks', currentDatabaseId)} title="AI 任务"><Icon name="activity" /><span className="nav-label">AI 任务</span></button>
            </div>}
          </div>
          <div className="sidebar-subsection">
            {renderSubsectionToggle('automation', '自动化')}
            {expandedSubsections.automation && <div className="sidebar-subsection-content">
              <button className={`nav-item ${currentPage === 'automation' ? 'active' : ''}`} onClick={() => onNavigate('automation', currentDatabaseId)} title="自动化规则"><Icon name="automation" /><span className="nav-label">自动化规则</span></button>
            </div>}
          </div>
        </div>}

        {renderSectionToggle('views', '视图')}
        {expandedSections.views && <div className="sidebar-section-content"><ViewSwitcher onOpenView={() => onNavigate('patents', currentDatabaseId)} /></div>}

        <div className="sidebar-section-title sidebar-section-title-row">
          <button type="button" className="sidebar-section-toggle" onClick={() => toggleSection('products')} aria-expanded={expandedSections.products}>
            <span>产品分类</span><Icon name={expandedSections.products ? 'chevron-down' : 'chevron-right'} size={13} />
          </button>
          <button className="sidebar-add" onClick={() => setShowAddProduct(true)} title="新增产品">+</button>
        </div>
        {expandedSections.products && <div className="sidebar-section-content">
          <div className="product-list">
            {products.map((p) => (
              <button key={p.id} className={`product-item ${currentProductId === p.id ? 'active' : ''}`} onClick={() => handleProductClick(p.id)}>
                <span className="product-dot" />
                <span className="product-name">{p.name}</span>
                {p.patent_count !== undefined && <span className="product-count">{p.patent_count}</span>}
              </button>
            ))}
            {products.length === 0 && <div className="sidebar-empty">暂无产品分类</div>}
          </div>
          {showAddProduct && (
            <div className="sidebar-form product-form">
              <input className="sidebar-input" placeholder="产品名称" value={newProductName} onChange={(e) => setNewProductName(e.target.value)} onKeyDown={(e) => e.key === 'Enter' && handleAddProduct()} autoFocus />
              <div className="sidebar-form-actions">
                <button className="sidebar-action primary" onClick={handleAddProduct}>创建</button>
                <button className="sidebar-action" onClick={() => { setShowAddProduct(false); setNewProductName('') }}>取消</button>
              </div>
            </div>
          )}
        </div>}

        {renderSectionToggle('management', '管理')}
        {expandedSections.management && <div className="sidebar-section-content">
          <div className="sidebar-subsection">
            {renderSubsectionToggle('data', '数据管理')}
            {expandedSubsections.data && <div className="sidebar-subsection-content">
              <button className={`nav-item ${currentPage === 'fields' ? 'active' : ''}`} onClick={() => onNavigate('fields', currentDatabaseId)} title="字段管理"><Icon name="columns" /><span className="nav-label">字段管理</span></button>
              <button className={`nav-item ${currentPage === 'import-history' ? 'active' : ''}`} onClick={() => onNavigate('import-history', currentDatabaseId)} title="导入历史"><Icon name="history" /><span className="nav-label">导入历史</span></button>
              <button className={`nav-item ${currentPage === 'governance' ? 'active' : ''}`} onClick={() => onNavigate('governance', currentDatabaseId)} title="数据治理"><Icon name="history" /><span className="nav-label">数据治理</span></button>
            </div>}
          </div>
          <div className="sidebar-subsection">
            {renderSubsectionToggle('system', '系统管理')}
            {expandedSubsections.system && <div className="sidebar-subsection-content">
              <button className={`nav-item ${currentPage === 'management' ? 'active' : ''}`} onClick={() => onNavigate('management', currentDatabaseId)} title="管理台"><Icon name="settings" /><span className="nav-label">管理台</span></button>
              <button className={`nav-item ${currentPage === 'sharing' ? 'active' : ''}`} onClick={() => onNavigate('sharing', currentDatabaseId)} title="协作与权限"><Icon name="users" /><span className="nav-label">协作与权限</span></button>
              <button className={`nav-item ${currentPage === 'settings' ? 'active' : ''}`} onClick={() => onNavigate('settings', currentDatabaseId)} title="设置"><Icon name="sliders" /><span className="nav-label">设置</span></button>
            </div>}
          </div>
        </div>}
      </nav>

      <button className="sidebar-account" onClick={() => onNavigate('sharing', currentDatabaseId)} title="管理协作与权限">
        <div className={`account-avatar ${currentUser ? '' : 'muted'}`}>
          {currentUser ? (currentUser.display_name || currentUser.username).charAt(0).toUpperCase() : '?'}
        </div>
        <div className="account-info">
          <strong>{currentUser?.display_name || currentUser?.username || '未选择身份'}</strong>
          {currentUser && <span>@{currentUser.username}</span>}
        </div>
        <span className="account-arrow">›</span>
      </button>
      {pendingDeleteDatabase && (
        <div className="modal-overlay" role="presentation" onMouseDown={(event) => {
          if (event.target === event.currentTarget && !deletingDatabase) setPendingDeleteDatabase(null)
        }}>
          <div className="modal sidebar-delete-modal" role="dialog" aria-modal="true" aria-labelledby="delete-db-title">
            <div className="modal-header">
              <h2 id="delete-db-title">删除专利库</h2>
              <button type="button" className="modal-close" onClick={() => setPendingDeleteDatabase(null)} disabled={deletingDatabase} aria-label="关闭">×</button>
            </div>
            <div className="modal-body">
              <p>确定删除「{pendingDeleteDatabase.name}」吗？</p>
              <p className="text-muted">库内 {pendingDeleteDatabase.patent_count ?? 0} 条专利及其关联数据将一并删除，操作不可恢复。</p>
            </div>
            <div className="modal-footer">
              <button type="button" className="btn-secondary" onClick={() => setPendingDeleteDatabase(null)} disabled={deletingDatabase}>取消</button>
              <button type="button" className="btn-danger" onClick={() => void handleDeleteDatabase()} disabled={deletingDatabase}>
                {deletingDatabase ? '删除中...' : '确认删除'}
              </button>
            </div>
          </div>
        </div>
      )}
    </aside>
  )
}
