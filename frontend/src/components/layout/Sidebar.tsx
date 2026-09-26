import { useState, useEffect, useCallback } from 'react'
import { productApi, databaseApi } from '../../api'
import { useAppStore } from '../../store'
import type { Page } from '../../App'
import type { PatentDatabase } from '../../types'
import Icon, { type IconName } from '../common/Icon'

const SIDEBAR_SECTIONS_STORAGE_KEY = 'patwiki_sidebar_sections'
type SidebarSectionKey = 'workspace' | 'intelligence' | 'management'
type SidebarSections = Record<SidebarSectionKey, boolean>

const DEFAULT_SIDEBAR_SECTIONS: SidebarSections = {
  workspace: true,
  intelligence: true,
  management: true,
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

interface NavDestination {
  page: Page
  label: string
  icon: IconName
  hint: string
}

const NAV_SECTIONS: Array<{ key: SidebarSectionKey; label: string; items: NavDestination[] }> = [
  {
    key: 'workspace',
    label: '专利工作区',
    items: [
      { page: 'patents', label: '全部专利', icon: 'table', hint: '浏览、检索与管理当前库全部专利' },
    ],
  },
  {
    key: 'intelligence',
    label: '智能与自动化',
    items: [
      { page: 'agent-analysis', label: '智能分析', icon: 'activity', hint: '用智能体对专利做多维分析' },
      { page: 'ai-center', label: 'AI 能力中心', icon: 'sparkles', hint: '管理 AI 能力、任务与配置' },
    ],
  },
  {
    key: 'management',
    label: '系统管理',
    items: [
      { page: 'management', label: '业务管理台', icon: 'dashboard', hint: '字段、模板与业务规则配置' },
      { page: 'sharing', label: '协作与权限', icon: 'users', hint: '成员、角色与权限管理' },
    ],
  },
]

interface SidebarProps {
  currentPage: Page
  onNavigate: (page: Page, databaseId?: number | null) => void
  collapsed: boolean
  onToggleCollapse: (collapsed: boolean) => void
}

export default function Sidebar({ currentPage, onNavigate, collapsed, onToggleCollapse }: SidebarProps) {
  const {
    currentProductId, setCurrentProductId, setProducts,
    databases, currentDatabaseId, setCurrentDatabaseId, setDatabases,
    currentUser, setCurrentViewId,
  } = useAppStore()
  const [showAddDatabase, setShowAddDatabase] = useState(false)
  const [newDbName, setNewDbName] = useState('')
  const [newDbDesc, setNewDbDesc] = useState('')
  const [expandedSections, setExpandedSections] = useState<SidebarSections>(() => readSidebarSections())
  const [pendingDeleteDatabase, setPendingDeleteDatabase] = useState<PatentDatabase | null>(null)
  const [deletingDatabase, setDeletingDatabase] = useState(false)

  const currentDatabase = databases.find(d => d.id === currentDatabaseId) ?? null

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

  const isDestinationActive = (page: Page) => (
    page === 'patents'
      ? currentPage === 'patents' && !currentProductId
      : currentPage === page
  )

  const handleNavSelect = (page: Page) => {
    if (page === 'patents') {
      handleProductClick(null)
    } else {
      onNavigate(page, currentDatabaseId)
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

      <button
        type="button"
        className="sidebar-rail-database"
        onClick={() => onToggleCollapse(false)}
        aria-label="展开并切换专利库"
        title={`当前库：${currentDatabase?.name ?? '未选择'}（点击展开切换）`}
      >
        <Icon name="database" size={18} />
      </button>

      <div className="sidebar-database">
        <div className="sidebar-label-row">
          <span className="sidebar-label"><Icon name="database" size={12} /> 当前专利库</span>
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
        {currentDatabase && (
          <div className="database-meta">{currentDatabase.patent_count ?? 0} 条专利</div>
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
            {currentDatabase && !currentDatabase.is_default && (
              <button className="sidebar-link danger" onClick={requestDeleteDatabase} title="删除当前库及库内专利">删除</button>
            )}
          </div>
        )}
      </div>

      <nav className="sidebar-nav">
        {NAV_SECTIONS.map(section => (
          <div className="sidebar-section" key={section.key}>
            {renderSectionToggle(section.key, section.label)}
            {(collapsed || expandedSections[section.key]) && (
              <div className="sidebar-section-content">
                {section.items.map(item => (
                  <button
                    key={item.page}
                    type="button"
                    className={`nav-item ${isDestinationActive(item.page) ? 'active' : ''}`}
                    onClick={() => handleNavSelect(item.page)}
                    title={collapsed ? item.label : item.hint}
                    aria-current={isDestinationActive(item.page) ? 'page' : undefined}
                  >
                    <Icon name={item.icon} size={17} />
                    <span className="nav-label">{item.label}</span>
                  </button>
                ))}
              </div>
            )}
          </div>
        ))}
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
