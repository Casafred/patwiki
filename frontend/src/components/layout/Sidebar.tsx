import { useState, useEffect, useCallback } from 'react'
import { productApi, databaseApi } from '../../api'
import { useAppStore } from '../../store'

interface SidebarProps {
  currentPage: string
  onNavigate: (page: 'patents' | 'stats' | 'settings' | 'fields' | 'ai-tasks' | 'agent-analysis' | 'sharing') => void
}

export default function Sidebar({ currentPage, onNavigate }: SidebarProps) {
  const {
    products, currentProductId, setCurrentProductId, setProducts,
    databases, currentDatabaseId, setCurrentDatabaseId, setDatabases,
    currentUser,
  } = useAppStore()
  const [showAddProduct, setShowAddProduct] = useState(false)
  const [newProductName, setNewProductName] = useState('')
  const [showAddDatabase, setShowAddDatabase] = useState(false)
  const [newDbName, setNewDbName] = useState('')
  const [newDbDesc, setNewDbDesc] = useState('')

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
    } catch (e: any) {
      const detail = e?.response?.data?.detail
      alert(detail || '删除库失败')
    }
  }

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
            <div style={{ display: 'flex', gap: 4, marginTop: 4 }}>
              <div
                className="product-item"
                style={{ color: '#64748b', fontStyle: 'italic', flex: 1 }}
                onClick={() => setShowAddDatabase(true)}
              >
                + 新建库
              </div>
              {currentDatabaseId !== null && databases.find(d => d.id === currentDatabaseId && !d.is_default) && (
                <div
                  className="product-item"
                  style={{ color: '#ef4444', fontStyle: 'italic', flexShrink: 0, padding: '4px 8px' }}
                  onClick={handleDeleteDatabase}
                  title="删除当前库（连同库内所有专利一并删除，不可恢复）"
                >
                  🗑 删除库
                </div>
              )}
            </div>
          )}
        </div>

        <div
          className={`nav-item ${currentPage === 'patents' && !currentProductId ? 'active' : ''}`}
          onClick={() => handleProductClick(null)}
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
