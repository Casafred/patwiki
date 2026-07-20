import { useState, useEffect, useCallback } from 'react'
import { productApi, databaseApi, viewApi } from '../../api'
import { useAppStore } from '../../store'
import type { PatentView } from '../../types'

interface SidebarProps {
  currentPage: string
  onNavigate: (page: 'patents' | 'stats' | 'settings' | 'fields' | 'ai-tasks' | 'agent-analysis' | 'sharing' | 'views' | 'metadata') => void
}

export default function Sidebar({ currentPage, onNavigate }: SidebarProps) {
  const {
    products, currentProductId, setCurrentProductId, setProducts,
    databases, currentDatabaseId, setCurrentDatabaseId, setDatabases,
    currentUser,
    views, setViews, currentViewId, setCurrentViewId,
  } = useAppStore()
  const [showAddProduct, setShowAddProduct] = useState(false)
  const [newProductName, setNewProductName] = useState('')
  const [showAddDatabase, setShowAddDatabase] = useState(false)
  const [newDbName, setNewDbName] = useState('')
  const [newDbDesc, setNewDbDesc] = useState('')
  // P0-15：新建视图（内联简易表单）
  const [showAddView, setShowAddView] = useState(false)
  const [newViewName, setNewViewName] = useState('')
  const [newViewType, setNewViewType] = useState<'personal' | 'shared'>('personal')
  const [viewLoading, setViewLoading] = useState(false)

  // 打通关联：监听当前库切换，重新加载产品列表，patent_count 按当前库过滤
  const reloadProducts = useCallback(async () => {
    try {
      const params: Record<string, any> = {}
      if (currentDatabaseId !== null && currentDatabaseId !== undefined) {
        params.database_id = currentDatabaseId
      }
      const refreshed = await productApi.list(params)
      setProducts(refreshed)
    } catch (e) {
      console.error('Failed to reload products:', e)
    }
  }, [currentDatabaseId, setProducts])

  useEffect(() => {
    reloadProducts()
  }, [reloadProducts])

  // P0-15：当前库切换时重新加载视图列表
  const reloadViews = useCallback(async () => {
    if (currentDatabaseId == null) {
      setViews([])
      return
    }
    try {
      const list = await viewApi.list({ database_id: currentDatabaseId })
      setViews(list)
      // 校验 currentViewId 仍属于该库；否则置空
      if (currentViewId != null && !list.some(v => v.id === currentViewId)) {
        setCurrentViewId(null)
      }
    } catch (e) {
      console.error('Failed to load views:', e)
      setViews([])
    }
  }, [currentDatabaseId, setViews, currentViewId, setCurrentViewId])

  useEffect(() => {
    reloadViews()
  }, [reloadViews])

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
    } catch (e) {
      alert('创建产品失败')
    }
  }

  // P0-11：库切换
  const handleDatabaseChange = (id: number) => {
    setCurrentDatabaseId(id)
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
    } catch (e) {
      alert('创建库失败')
    }
  }

  // P0-15：切换视图
  const handleViewClick = (viewId: number | null) => {
    setCurrentViewId(viewId)
    setCurrentProductId(null)
    onNavigate('patents')
  }

  // P0-15：点击"部门总表"——若不存在则后端自动创建
  const handleMasterViewClick = async () => {
    if (currentDatabaseId == null) return
    setViewLoading(true)
    try {
      const master = await databaseApi.getOrCreateMasterView(currentDatabaseId)
      // 把 master 合入 views 缓存（若尚未存在）
      if (!views.some(v => v.id === master.id)) {
        setViews([...views, master])
      }
      setCurrentViewId(master.id)
      setCurrentProductId(null)
      onNavigate('patents')
    } catch (e) {
      console.error('Failed to get/create master view:', e)
      alert('获取部门总表失败')
    } finally {
      setViewLoading(false)
    }
  }

  // P0-15：新建视图（简易内联表单，完整管理在 P0-18）
  const handleAddView = async () => {
    if (!newViewName.trim() || currentDatabaseId == null) return
    try {
      const created = await viewApi.create({
        name: newViewName.trim(),
        database_id: currentDatabaseId,
        view_type: newViewType,
        filter_config: {},
        column_config: [],
        sort_config: {},
      })
      setViews([...views, created])
      setCurrentViewId(created.id)
      setCurrentProductId(null)
      setNewViewName('')
      setShowAddView(false)
      onNavigate('patents')
    } catch (e) {
      alert('创建视图失败')
    }
  }

  // 视图分组：部门总表 / 个人 / 共享
  const masterView = views.find(v => v.is_department_master)
  const personalViews = views.filter(v => !v.is_department_master && v.view_type === 'personal')
  const sharedViews = views.filter(v => !v.is_department_master && v.view_type === 'shared')

  return (
    <aside className="sidebar">
      <div className="sidebar-header">
        <h1>PatWiki</h1>
        <p>专利多维知识管理系统</p>
      </div>

      <nav className="sidebar-nav">
        {/* P0-11：库切换器 - 顶部 */}
        <div className="nav-section">专利库</div>
        <div style={{ padding: '0 12px 12px', borderBottom: '1px solid #1e293b', marginBottom: 8 }}>
          <select
            className="form-input"
            style={{ width: '100%', fontSize: 13, padding: '6px 8px', background: '#1e293b', border: '1px solid #334155', color: '#e2e8f0' }}
            value={currentDatabaseId ?? ''}
            onChange={(e) => handleDatabaseChange(Number(e.target.value))}
          >
            {databases.length === 0 && <option value="">无可用库</option>}
            {databases.map(d => (
              <option key={d.id} value={d.id}>
                {d.name}{d.patent_count !== undefined ? ` (${d.patent_count})` : ''}
              </option>
            ))}
          </select>
          {showAddDatabase ? (
            <div style={{ marginTop: 8 }}>
              <input
                className="form-input"
                style={{ fontSize: 12, padding: '4px 8px', background: '#1e293b', border: '1px solid #334155', color: '#e2e8f0', marginBottom: 4 }}
                placeholder="库名称（如：电钻专利库）"
                value={newDbName}
                onChange={(e) => setNewDbName(e.target.value)}
                autoFocus
              />
              <input
                className="form-input"
                style={{ fontSize: 12, padding: '4px 8px', background: '#1e293b', border: '1px solid #334155', color: '#e2e8f0', marginBottom: 4 }}
                placeholder="描述（可选）"
                value={newDbDesc}
                onChange={(e) => setNewDbDesc(e.target.value)}
              />
              <div style={{ display: 'flex', gap: 4 }}>
                <button className="btn btn-primary" style={{ fontSize: 11, padding: '3px 8px' }} onClick={handleAddDatabase}>
                  创建
                </button>
                <button
                  className="btn btn-secondary"
                  style={{ fontSize: 11, padding: '3px 8px', background: 'transparent', border: '1px solid #475569', color: '#cbd5e1' }}
                  onClick={() => { setShowAddDatabase(false); setNewDbName(''); setNewDbDesc('') }}
                >
                  取消
                </button>
              </div>
            </div>
          ) : (
            <div
              className="product-item"
              style={{ color: '#64748b', fontStyle: 'italic', marginTop: 4 }}
              onClick={() => setShowAddDatabase(true)}
            >
              + 新建库
            </div>
          )}
        </div>

        {/* P0-15：视图切换器 */}
        <div className="nav-section">视图（小表 / 部门总表）</div>
        <div style={{ borderBottom: '1px solid #1e293b', marginBottom: 8 }}>
          {/* 大表直查（不应用任何视图） */}
          <div
            className={`nav-item ${currentPage === 'patents' && currentViewId === null && currentProductId === null ? 'active' : ''}`}
            onClick={() => handleViewClick(null)}
            title="直接查询大表全部专利，不应用任何视图"
          >
            大表直查
          </div>

          {/* 部门总表入口（自动获取/创建） */}
          <div
            className={`nav-item ${currentPage === 'patents' && currentViewId !== null && masterView && currentViewId === masterView.id ? 'active' : ''}`}
            onClick={handleMasterViewClick}
            title="部门级综合全属性总表（显示全部字段、全部专利）"
            style={viewLoading ? { opacity: 0.5, pointerEvents: 'none' } : undefined}
          >
            <span style={{ color: '#fbbf24' }}>★</span> 部门总表
          </div>

          {/* 个人小表 */}
          {personalViews.length > 0 && (
            <div style={{ padding: '4px 12px 2px', fontSize: 10, color: '#64748b', textTransform: 'uppercase' }}>
              我的小表
            </div>
          )}
          {personalViews.map((v: PatentView) => (
            <div
              key={v.id}
              className={`nav-item ${currentPage === 'patents' && currentViewId === v.id ? 'active' : ''}`}
              onClick={() => handleViewClick(v.id)}
              title={v.description || v.name}
            >
              <span style={{ marginRight: 6, color: '#3b82f6' }}>●</span>
              {v.name}
            </div>
          ))}

          {/* 共享视图 */}
          {sharedViews.length > 0 && (
            <div style={{ padding: '4px 12px 2px', fontSize: 10, color: '#64748b', textTransform: 'uppercase' }}>
              共享视图
            </div>
          )}
          {sharedViews.map((v: PatentView) => (
            <div
              key={v.id}
              className={`nav-item ${currentPage === 'patents' && currentViewId === v.id ? 'active' : ''}`}
              onClick={() => handleViewClick(v.id)}
              title={v.description || v.name}
            >
              <span style={{ marginRight: 6, color: '#10b981' }}>◐</span>
              {v.name}
            </div>
          ))}

          {/* 新建视图 */}
          {showAddView ? (
            <div style={{ padding: '8px 12px' }}>
              <input
                className="form-input"
                style={{ fontSize: 12, padding: '4px 8px', background: '#1e293b', border: '1px solid #334155', color: '#e2e8f0', marginBottom: 4, width: '100%' }}
                placeholder="视图名称（如：电钻风险排查）"
                value={newViewName}
                onChange={(e) => setNewViewName(e.target.value)}
                autoFocus
              />
              <select
                className="form-input"
                style={{ fontSize: 12, padding: '4px 8px', background: '#1e293b', border: '1px solid #334155', color: '#e2e8f0', marginBottom: 4, width: '100%' }}
                value={newViewType}
                onChange={(e) => setNewViewType(e.target.value as 'personal' | 'shared')}
              >
                <option value="personal">个人小表（仅自己）</option>
                <option value="shared">共享视图（库内成员可见）</option>
              </select>
              <div style={{ display: 'flex', gap: 4 }}>
                <button className="btn btn-primary" style={{ fontSize: 11, padding: '3px 8px' }} onClick={handleAddView}>
                  创建
                </button>
                <button
                  className="btn btn-secondary"
                  style={{ fontSize: 11, padding: '3px 8px', background: 'transparent', border: '1px solid #475569', color: '#cbd5e1' }}
                  onClick={() => { setShowAddView(false); setNewViewName(''); setNewViewType('personal') }}
                >
                  取消
                </button>
              </div>
            </div>
          ) : (
            <div
              className="product-item"
              style={{ color: '#64748b', fontStyle: 'italic' }}
              onClick={() => setShowAddView(true)}
            >
              + 新建视图
            </div>
          )}
        </div>

        <div
          className={`nav-item ${currentPage === 'patents' && !currentProductId && currentViewId === null ? 'active' : ''}`}
          onClick={() => handleProductClick(null)}
          style={{ display: 'none' }}
        >
          全部专利
        </div>
        <div
          className={`nav-item ${currentPage === 'stats' ? 'active' : ''}`}
          onClick={() => onNavigate('stats')}
        >
          数据看板
        </div>
        <div
          className={`nav-item ${currentPage === 'agent-analysis' ? 'active' : ''}`}
          onClick={() => onNavigate('agent-analysis')}
        >
          AGENTAI 分析
        </div>
        <div
          className={`nav-item ${currentPage === 'ai-tasks' ? 'active' : ''}`}
          onClick={() => onNavigate('ai-tasks')}
        >
          AI 任务
        </div>
        <div
          className={`nav-item ${currentPage === 'fields' ? 'active' : ''}`}
          onClick={() => onNavigate('fields')}
        >
          字段管理
        </div>
        <div
          className={`nav-item ${currentPage === 'views' ? 'active' : ''}`}
          onClick={() => onNavigate('views')}
        >
          视图管理
        </div>
        <div
          className={`nav-item ${currentPage === 'metadata' ? 'active' : ''}`}
          onClick={() => onNavigate('metadata')}
        >
          元数据管理
        </div>
        <div
          className={`nav-item ${currentPage === 'sharing' ? 'active' : ''}`}
          onClick={() => onNavigate('sharing')}
        >
          协作与权限
        </div>
        <div
          className={`nav-item ${currentPage === 'settings' ? 'active' : ''}`}
          onClick={() => onNavigate('settings')}
        >
          设置
        </div>

        <div className="nav-section">产品分类</div>
        <div className="product-list">
          {products.map((p) => (
            <div
              key={p.id}
              className={`product-item ${currentProductId === p.id ? 'active' : ''}`}
              onClick={() => handleProductClick(p.id)}
            >
              {p.name}
              {p.patent_count !== undefined && p.patent_count > 0 && (
                <span style={{ marginLeft: 'auto', fontSize: 11, color: '#64748b' }}>
                  {p.patent_count}
                </span>
              )}
            </div>
          ))}
        </div>

        {showAddProduct ? (
          <div style={{ padding: '8px 20px' }}>
            <input
              className="form-input"
              style={{ fontSize: 13, padding: '6px 8px', background: '#1e293b', border: '1px solid #334155', color: '#e2e8f0' }}
              placeholder="产品名称"
              value={newProductName}
              onChange={(e) => setNewProductName(e.target.value)}
              onKeyDown={(e) => e.key === 'Enter' && handleAddProduct()}
              autoFocus
            />
            <div style={{ display: 'flex', gap: 4, marginTop: 6 }}>
              <button className="btn btn-primary" style={{ fontSize: 12, padding: '4px 10px' }} onClick={handleAddProduct}>
                确定
              </button>
              <button
                className="btn btn-secondary"
                style={{ fontSize: 12, padding: '4px 10px', background: 'transparent', border: '1px solid #475569', color: '#cbd5e1' }}
                onClick={() => { setShowAddProduct(false); setNewProductName('') }}
              >
                取消
              </button>
            </div>
          </div>
        ) : (
          <div
            className="product-item"
            style={{ color: '#64748b', fontStyle: 'italic' }}
            onClick={() => setShowAddProduct(true)}
          >
            + 新增产品
          </div>
        )}
      </nav>

      {/* 当前用户身份（底部） */}
      <div
        style={{
          padding: '10px 16px', borderTop: '1px solid #1e293b', cursor: 'pointer',
          display: 'flex', alignItems: 'center', gap: 8,
        }}
        onClick={() => onNavigate('sharing')}
        title="点击管理协作与权限"
      >
        {currentUser ? (
          <>
            <div style={{
              width: 28, height: 28, borderRadius: '50%', background: '#3b82f6',
              color: '#fff', display: 'flex', alignItems: 'center', justifyContent: 'center',
              fontSize: 12, fontWeight: 600, flexShrink: 0,
            }}>
              {(currentUser.display_name || currentUser.username).charAt(0).toUpperCase()}
            </div>
            <div style={{ minWidth: 0, flex: 1 }}>
              <div style={{ fontSize: 12, fontWeight: 500, color: '#e2e8f0', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                {currentUser.display_name || currentUser.username}
              </div>
              <div style={{ fontSize: 10, color: '#64748b' }}>@{currentUser.username}</div>
            </div>
          </>
        ) : (
          <>
            <div style={{
              width: 28, height: 28, borderRadius: '50%', background: '#475569',
              color: '#cbd5e1', display: 'flex', alignItems: 'center', justifyContent: 'center',
              fontSize: 12, fontWeight: 600, flexShrink: 0,
            }}>?</div>
            <div style={{ fontSize: 12, color: '#94a3b8' }}>未选择身份</div>
          </>
        )}
      </div>
    </aside>
  )
}
