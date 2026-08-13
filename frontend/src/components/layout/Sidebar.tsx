import { useState, useEffect, useCallback } from 'react'
import { productApi, databaseApi } from '../../api'
import { useAppStore } from '../../store'
import ViewSwitcher from '../views/ViewSwitcher'
import type { Page } from '../../App'
import Icon from '../common/Icon'

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
  const [deleteConfirm, setDeleteConfirm] = useState<{ db: typeof databases[0]; count: number } | null>(null)
  const [deleteInput, setDeleteInput] = useState('')
  const [deleting, setDeleting] = useState(false)

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

  // 整库删除：打开确认弹窗（需输入库名确认），级联删除库内所有专利后删库
  const handleDeleteDatabase = () => {
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
    setDeleteInput('')
    setDeleteConfirm({ db, count: db.patent_count ?? 0 })
  }

  const confirmDeleteDatabase = async () => {
    if (!deleteConfirm) return
    if (deleteInput.trim() !== deleteConfirm.db.name.trim()) {
      alert('输入的库名不匹配，请重新输入')
      return
    }
    setDeleting(true)
    try {
      await databaseApi.delete(deleteConfirm.db.id, true)
      const refreshed = await databaseApi.list()
      setDatabases(refreshed)
      if (refreshed.length > 0) {
        setCurrentDatabaseId(refreshed[0].id)
      } else {
        setCurrentDatabaseId(null)
      }
      onNavigate('patents', refreshed.length > 0 ? refreshed[0].id : null)
      setDeleteConfirm(null)
    } catch (e: unknown) {
      const detail = e && typeof e === 'object' && 'response' in e
        ? (e as { response?: { data?: { detail?: unknown } } }).response?.data?.detail
        : undefined
      alert(detail || '删除库失败')
    } finally {
      setDeleting(false)
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
              <button className="sidebar-link danger" onClick={handleDeleteDatabase} title="删除当前库及库内专利">删除</button>
            )}
          </div>
        )}
      </div>

      <nav className="sidebar-nav">
        <div className="sidebar-section-title">工作台</div>
        <button className={`nav-item ${currentPage === 'patents' && !currentProductId ? 'active' : ''}`} onClick={() => handleProductClick(null)} title="全部专利"><Icon name="table" /><span className="nav-label">全部专利</span></button>
        <button className={`nav-item ${currentPage === 'stats' ? 'active' : ''}`} onClick={() => onNavigate('stats', currentDatabaseId)} title="数据看板"><Icon name="chart" /><span className="nav-label">数据看板</span></button>
        <button className={`nav-item ${currentPage === 'dashboard' ? 'active' : ''}`} onClick={() => onNavigate('dashboard', currentDatabaseId)} title="可配置仪表盘"><Icon name="dashboard" /><span className="nav-label">可配置仪表盘</span></button>

        <div className="sidebar-section-title">智能与自动化</div>
        <button className={`nav-item ${currentPage === 'automation' ? 'active' : ''}`} onClick={() => onNavigate('automation', currentDatabaseId)} title="自动化规则"><Icon name="automation" /><span className="nav-label">自动化规则</span></button>
        <button className={`nav-item ${currentPage === 'agent-analysis' ? 'active' : ''}`} onClick={() => onNavigate('agent-analysis', currentDatabaseId)} title="智能分析"><Icon name="sparkles" /><span className="nav-label">智能分析</span></button>
        <button className={`nav-item ${currentPage === 'ai-tasks' ? 'active' : ''}`} onClick={() => onNavigate('ai-tasks', currentDatabaseId)} title="AI 任务"><Icon name="activity" /><span className="nav-label">AI 任务</span></button>

        <ViewSwitcher onOpenView={() => onNavigate('patents', currentDatabaseId)} />

        <div className="sidebar-section-title sidebar-section-title-row">
          <span>产品分类</span>
          <button className="sidebar-add" onClick={() => setShowAddProduct(true)} title="新增产品">+</button>
        </div>
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

        <div className="sidebar-section-title">管理</div>
        <button className={`nav-item ${currentPage === 'fields' ? 'active' : ''}`} onClick={() => onNavigate('fields', currentDatabaseId)} title="字段管理"><Icon name="columns" /><span className="nav-label">字段管理</span></button>
        <button className={`nav-item ${currentPage === 'management' ? 'active' : ''}`} onClick={() => onNavigate('management', currentDatabaseId)} title="管理台"><Icon name="settings" /><span className="nav-label">管理台</span></button>
        <button className={`nav-item ${currentPage === 'sharing' ? 'active' : ''}`} onClick={() => onNavigate('sharing', currentDatabaseId)} title="协作与权限"><Icon name="users" /><span className="nav-label">协作与权限</span></button>
        <button className={`nav-item ${currentPage === 'import-history' ? 'active' : ''}`} onClick={() => onNavigate('import-history', currentDatabaseId)} title="导入历史"><Icon name="history" /><span className="nav-label">导入历史</span></button>
        <button className={`nav-item ${currentPage === 'settings' ? 'active' : ''}`} onClick={() => onNavigate('settings', currentDatabaseId)} title="设置"><Icon name="sliders" /><span className="nav-label">设置</span></button>
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
      {deleteConfirm && (
        <div className="modal-overlay" onClick={() => !deleting && setDeleteConfirm(null)}>
          <div className="modal-dialog modal-danger" onClick={(e) => e.stopPropagation()}>
            <div className="modal-header">
              <h3>确认删除库</h3>
            </div>
            <div className="modal-body">
              <p className="modal-warning-text">
                即将删除库「<strong>{deleteConfirm.db.name}</strong>」
                {deleteConfirm.count > 0 && (
                  <>，该库包含 <strong style={{ color: '#dc2626' }}>{deleteConfirm.count}</strong> 条专利，将一并删除。</>
                )}
              </p>
              <p className="modal-warning-subtext">此操作不可恢复。为防止误操作，请在下方输入完整的库名称以确认：</p>
              <input
                className="modal-input"
                placeholder={deleteConfirm.db.name}
                value={deleteInput}
                onChange={(e) => setDeleteInput(e.target.value)}
                onKeyDown={(e) => e.key === 'Enter' && deleteInput.trim() === deleteConfirm.db.name.trim() && !deleting && confirmDeleteDatabase()}
                autoFocus
                disabled={deleting}
              />
            </div>
            <div className="modal-footer">
              <button className="btn btn-secondary" onClick={() => setDeleteConfirm(null)} disabled={deleting}>取消</button>
              <button
                className="btn btn-danger"
                onClick={confirmDeleteDatabase}
                disabled={deleting || deleteInput.trim() !== deleteConfirm.db.name.trim()}
              >
                {deleting ? '删除中…' : '确认删除'}
              </button>
            </div>
          </div>
        </div>
      )}
    </aside>
  )
}
