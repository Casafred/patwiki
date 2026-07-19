import { useState, useEffect } from 'react'
import { productApi } from '../../api'
import { useAppStore } from '../../store'
import type { Product } from '../../types'

interface SidebarProps {
  currentPage: string
  onNavigate: (page: 'patents' | 'stats' | 'settings' | 'ai-tasks') => void
  onImport: () => void
}

export default function Sidebar({ currentPage, onNavigate, onImport }: SidebarProps) {
  const { products, currentProductId, setCurrentProductId } = useAppStore()
  const [showAddProduct, setShowAddProduct] = useState(false)
  const [newProductName, setNewProductName] = useState('')

  const handleProductClick = (productId: number | null) => {
    setCurrentProductId(productId)
    onNavigate('patents')
  }

  const handleAddProduct = async () => {
    if (!newProductName.trim()) return
    try {
      const product = await productApi.create({ name: newProductName.trim() })
      setCurrentProductId(product.id)
      setNewProductName('')
      setShowAddProduct(false)
      window.location.reload()
    } catch (e) {
      alert('创建产品失败')
    }
  }

  return (
    <aside className="sidebar">
      <div className="sidebar-header">
        <h1>📋 PatWiki</h1>
        <p>专利多维知识管理系统</p>
      </div>

      <nav className="sidebar-nav">
        <div
          className={`nav-item ${currentPage === 'patents' && !currentProductId ? 'active' : ''}`}
          onClick={() => handleProductClick(null)}
        >
          📄 全部专利
        </div>
        <div
          className={`nav-item ${currentPage === 'stats' ? 'active' : ''}`}
          onClick={() => onNavigate('stats')}
        >
          📊 数据看板
        </div>
        <div
          className={`nav-item ${currentPage === 'ai-tasks' ? 'active' : ''}`}
          onClick={() => onNavigate('ai-tasks')}
        >
          🤖 AI 任务
        </div>
        <div
          className={`nav-item ${currentPage === 'settings' ? 'active' : ''}`}
          onClick={() => onNavigate('settings')}
        >
          ⚙️ 设置
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
    </aside>
  )
}
