import { useState, useEffect, useCallback } from 'react'
import { patentApi, exportApi } from '../../api'
import { useAppStore } from '../../store'
import type { Patent } from '../../types'

export default function PatentListPage() {
  const {
    patents, totalPatents, currentProductId, loading,
    setPatents, setLoading, filters, setFilters,
    selectedIds, toggleSelect, clearSelection,
  } = useAppStore()

  const [page, setPage] = useState(1)
  const [pageSize] = useState(50)
  const [searchText, setSearchText] = useState('')
  const [legalStatusFilter, setLegalStatusFilter] = useState('')
  const [categoryFilter, setCategoryFilter] = useState('')
  const [riskFilter, setRiskFilter] = useState('')

  const loadPatents = useCallback(async () => {
    setLoading(true)
    try {
      const params: Record<string, any> = {
        page,
        page_size: pageSize,
      }
      if (searchText) params.search = searchText
      if (currentProductId) params.product_id = currentProductId
      if (legalStatusFilter) params.legal_status = legalStatusFilter
      if (categoryFilter) params.category = categoryFilter
      if (riskFilter) params.has_risk = riskFilter === 'true' ? true : undefined

      const result = await patentApi.list(params)
      setPatents(result.items, result.total)
    } catch (e) {
      console.error('Failed to load patents:', e)
    } finally {
      setLoading(false)
    }
  }, [page, pageSize, searchText, currentProductId, legalStatusFilter, categoryFilter, riskFilter, setPatents, setLoading])

  useEffect(() => {
    loadPatents()
  }, [loadPatents])

  const handleSearch = (e: React.FormEvent) => {
    e.preventDefault()
    setPage(1)
    loadPatents()
  }

  const handleExport = async () => {
    try {
      const blob = await exportApi.exportPatents({
        product_id: currentProductId || undefined,
      })
      const url = window.URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = `patents_${new Date().toISOString().slice(0, 10)}.xlsx`
      a.click()
      window.URL.revokeObjectURL(url)
    } catch (e) {
      alert('导出失败')
    }
  }

  const getStatusClass = (status?: string) => {
    if (!status) return 'status-unknown'
    return `status-${status}`
  }

  const getStatusText = (status?: string) => {
    const map: Record<string, string> = {
      granted: '授权', examining: '实审中', published: '公开',
      rejected: '驳回', withdrawn: '撤回', deemed_withdrawn: '视撤',
      expired: '终止', abandoned: '放弃', pending: '待审', unknown: '未知',
    }
    return map[status || 'unknown'] || status || '未知'
  }

  const getRiskClass = (level?: string) => {
    if (!level || level === 'none') return 'risk-none'
    return `risk-${level}`
  }

  const totalPages = Math.ceil(totalPatents / pageSize)

  return (
    <div>
      <div className="page-header">
        <h2 className="page-title">专利列表</h2>
        <p className="page-subtitle">
          共 {totalPatents} 件专利
          {currentProductId && ' - 当前产品筛选中'}
        </p>
      </div>

      <div className="toolbar">
        <form onSubmit={handleSearch} style={{ display: 'flex', gap: 8, flex: 1 }}>
          <input
            type="text"
            className="form-input"
            style={{ maxWidth: 300 }}
            placeholder="搜索专利号、标题、申请人..."
            value={searchText}
            onChange={(e) => setSearchText(e.target.value)}
          />
          <button type="submit" className="btn btn-primary">搜索</button>
        </form>
        <button className="btn btn-secondary" onClick={handleExport}>
          📤 导出Excel
        </button>
      </div>

      <div className="filter-bar">
        <select value={legalStatusFilter} onChange={(e) => { setLegalStatusFilter(e.target.value); setPage(1) }}>
          <option value="">全部法律状态</option>
          <option value="granted">授权</option>
          <option value="examining">实审中</option>
          <option value="published">公开</option>
          <option value="rejected">驳回</option>
          <option value="withdrawn">撤回</option>
          <option value="deemed_withdrawn">视撤</option>
          <option value="expired">终止</option>
        </select>

        <select value={riskFilter} onChange={(e) => { setRiskFilter(e.target.value); setPage(1) }}>
          <option value="">全部风险</option>
          <option value="true">有风险</option>
          <option value="false">无风险</option>
        </select>
      </div>

      {selectedIds.length > 0 && (
        <div className="toolbar" style={{ background: '#eff6ff', padding: 10, borderRadius: 6, marginBottom: 12 }}>
          <span style={{ fontSize: 13, color: '#1e40af' }}>已选中 {selectedIds.length} 件专利</span>
          <button className="btn btn-secondary" style={{ fontSize: 12 }}>批量编辑</button>
          <button className="btn btn-secondary" style={{ fontSize: 12 }}>批量打标签</button>
          <button className="btn btn-primary" style={{ fontSize: 12 }}>AI批量处理</button>
          <button className="btn btn-secondary" style={{ fontSize: 12, marginLeft: 'auto' }} onClick={clearSelection}>取消选择</button>
        </div>
      )}

      <div className="table-container">
        <div className="table-header-info">
          <span>
            第 {(page - 1) * pageSize + 1} - {Math.min(page * pageSize, totalPatents)} 条，共 {totalPatents} 条
          </span>
        </div>

        {loading ? (
          <div className="loading-spinner">
            <div className="spinner"></div>
            加载中...
          </div>
        ) : patents.length === 0 ? (
          <div className="empty-state">
            <div className="empty-state-icon">📭</div>
            <div className="empty-state-title">暂无专利数据</div>
            <div className="empty-state-desc">点击右上角"导入Excel"按钮，导入您的专利数据开始使用</div>
          </div>
        ) : (
          <div style={{ overflowX: 'auto' }}>
            <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13 }}>
              <thead>
                <tr style={{ background: '#f8fafc', borderBottom: '2px solid #e2e8f0' }}>
                  <th style={{ width: 36, padding: '10px 8px' }}>
                    <input type="checkbox" />
                  </th>
                  <th style={{ padding: '10px 12px', textAlign: 'left', fontWeight: 600, whiteSpace: 'nowrap' }}>申请号</th>
                  <th style={{ padding: '10px 12px', textAlign: 'left', fontWeight: 600, minWidth: 300 }}>标题</th>
                  <th style={{ padding: '10px 12px', textAlign: 'left', fontWeight: 600, whiteSpace: 'nowrap' }}>申请人</th>
                  <th style={{ padding: '10px 12px', textAlign: 'left', fontWeight: 600, whiteSpace: 'nowrap' }}>发明人</th>
                  <th style={{ padding: '10px 12px', textAlign: 'left', fontWeight: 600, whiteSpace: 'nowrap' }}>申请日</th>
                  <th style={{ padding: '10px 12px', textAlign: 'left', fontWeight: 600, whiteSpace: 'nowrap' }}>法律状态</th>
                  <th style={{ padding: '10px 12px', textAlign: 'left', fontWeight: 600, whiteSpace: 'nowrap' }}>分类</th>
                  <th style={{ padding: '10px 12px', textAlign: 'left', fontWeight: 600, whiteSpace: 'nowrap' }}>风险</th>
                </tr>
              </thead>
              <tbody>
                {patents.map((p) => (
                  <tr
                    key={p.id}
                    style={{ borderBottom: '1px solid #f1f5f9', cursor: 'pointer' }}
                    className="hover:bg-gray-50"
                    onMouseEnter={(e) => (e.currentTarget.style.background = '#f8fafc')}
                    onMouseLeave={(e) => (e.currentTarget.style.background = '')}
                  >
                    <td style={{ padding: '8px' }}>
                      <input
                        type="checkbox"
                        checked={selectedIds.includes(p.id)}
                        onChange={() => toggleSelect(p.id)}
                        onClick={(e) => e.stopPropagation()}
                      />
                    </td>
                    <td style={{ padding: '8px 12px', fontFamily: 'monospace', fontSize: 12 }}>
                      {p.application_number || p.publication_number || '-'}
                    </td>
                    <td style={{ padding: '8px 12px' }}>
                      <div style={{ fontWeight: 500, color: '#0f172a' }}>{p.title}</div>
                      {(p.category || p.subcategory) && (
                        <div style={{ fontSize: 11, color: '#94a3b8', marginTop: 2 }}>
                          {p.category}{p.subcategory ? ` / ${p.subcategory}` : ''}
                        </div>
                      )}
                    </td>
                    <td style={{ padding: '8px 12px', color: '#475569' }}>{p.applicant || '-'}</td>
                    <td style={{ padding: '8px 12px', color: '#475569' }}>
                      {p.inventor ? (p.inventor.length > 15 ? p.inventor.slice(0, 15) + '...' : p.inventor) : '-'}
                    </td>
                    <td style={{ padding: '8px 12px', color: '#475569', whiteSpace: 'nowrap' }}>
                      {p.filing_date ? new Date(p.filing_date).toLocaleDateString('zh-CN') : '-'}
                    </td>
                    <td style={{ padding: '8px 12px' }}>
                      <span className={`status-badge ${getStatusClass(p.legal_status)}`}>
                        {getStatusText(p.legal_status)}
                      </span>
                    </td>
                    <td style={{ padding: '8px 12px', color: '#475569', fontSize: 12 }}>
                      {p.category || '-'}
                    </td>
                    <td style={{ padding: '8px 12px' }}>
                      {p.has_risk ? (
                        <span className={`risk-badge ${getRiskClass(p.risk_level)}`}>
                          {p.risk_level === 'high' || p.risk_level === 'critical' ? '高风险' :
                           p.risk_level === 'medium' ? '中风险' : '低风险'}
                        </span>
                      ) : (
                        <span style={{ color: '#94a3b8', fontSize: 12 }}>-</span>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}

        <div className="pagination">
          <button disabled={page <= 1} onClick={() => setPage(page - 1)}>上一页</button>
          <span>第 {page} / {totalPages || 1} 页</span>
          <button disabled={page >= totalPages} onClick={() => setPage(page + 1)}>下一页</button>
        </div>
      </div>
    </div>
  )
}
