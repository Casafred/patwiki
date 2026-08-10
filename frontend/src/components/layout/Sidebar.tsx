import { useState, useEffect, useCallback } from 'react'
import { productApi, databaseApi } from '../../api'
import { useAppStore } from '../../store'
import ViewSwitcher from '../views/ViewSwitcher'
import type { Page } from '../../App'

interface SidebarProps {
  currentPage: Page
  onNavigate: (page: Page) => void
}

export default function Sidebar({ currentPage, onNavigate }: SidebarProps) {
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
    onNavigate('patents')
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
      onNavigate('patents')
    } catch {
      alert('创建产品失败')
    }
  }

  // P0-11：库切换
  const handleDatabaseChange = (id: number) => {
    setCurrentDatabaseId(id)
    setCurrentViewId(null)
    setCurrentProductId(null)
    onNavigate('patents')
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
    } catch {
      alert('创建库失败')
    }
  }

  // 整库删除：级联删除库内所有专利后删库（默认库不可删）
  const handleDeleteDatabase = async () => {
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
    const count = db.patent_count ?? 0
    const msg = count > 0
      ? `确定要删除库「${db.name}」吗？\n\n该库包含 ${count} 条专利，将一并删除，此操作不可恢复！`
      : `确定要删除空库「${db.name}」吗？此操作不可恢复。`
    if (!confirm(msg)) return
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
      onNavigate('patents')
    } catch (e: unknown) {
      const detail = e && typeof e === 'object' && 'response' in e
        ? (e as { response?: { data?: { detail?: unknown } } }).response?.data?.detail
        : undefined
      alert(detail || '删除库失败')
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
        <button className={`nav-item ${currentPage === 'patents' && !currentProductId ? 'active' : ''}`} onClick={() => handleProductClick(null)}>全部专利</button>
        <button className={`nav-item ${currentPage === 'stats' ? 'active' : ''}`} onClick={() => onNavigate('stats')}>数据看板</button>
        <button className={`nav-item ${currentPage === 'dashboard' ? 'active' : ''}`} onClick={() => onNavigate('dashboard')}>可配置仪表盘</button>

        <div className="sidebar-section-title">智能与自动化</div>
        <button className={`nav-item ${currentPage === 'automation' ? 'active' : ''}`} onClick={() => onNavigate('automation')}>自动化规则</button>
        <button className={`nav-item ${currentPage === 'agent-analysis' ? 'active' : ''}`} onClick={() => onNavigate('agent-analysis')}>智能分析</button>
        <button className={`nav-item ${currentPage === 'ai-tasks' ? 'active' : ''}`} onClick={() => onNavigate('ai-tasks')}>AI 任务</button>

        <ViewSwitcher onOpenView={() => onNavigate('patents')} />

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
        <button className={`nav-item ${currentPage === 'fields' ? 'active' : ''}`} onClick={() => onNavigate('fields')}>字段管理</button>
        <button className={`nav-item ${currentPage === 'management' ? 'active' : ''}`} onClick={() => onNavigate('management')}>管理台</button>
        <button className={`nav-item ${currentPage === 'sharing' ? 'active' : ''}`} onClick={() => onNavigate('sharing')}>协作与权限</button>
        <button className={`nav-item ${currentPage === 'import-history' ? 'active' : ''}`} onClick={() => onNavigate('import-history')}>导入历史</button>
        <button className={`nav-item ${currentPage === 'settings' ? 'active' : ''}`} onClick={() => onNavigate('settings')}>设置</button>
      </nav>

      <button className="sidebar-account" onClick={() => onNavigate('sharing')} title="管理协作与权限">
        <div className={`account-avatar ${currentUser ? '' : 'muted'}`}>
          {currentUser ? (currentUser.display_name || currentUser.username).charAt(0).toUpperCase() : '?'}
        </div>
        <div className="account-info">
          <strong>{currentUser?.display_name || currentUser?.username || '未选择身份'}</strong>
          {currentUser && <span>@{currentUser.username}</span>}
        </div>
        <span className="account-arrow">›</span>
      </button>
    </aside>
  )
}
