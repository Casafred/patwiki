import { useState, useEffect, useCallback } from 'react'
import { patentApi, exportApi, aiApi } from '../../api'
import { useAppStore } from '../../store'
import type { Patent } from '../../types'

interface PatentListPageProps {
  onPatentClick: (id: number) => void
}

type SortField = 'filing_date' | 'application_number' | 'title' | 'applicant' | 'legal_status' | 'created_at'
type SortOrder = 'asc' | 'desc'
type AIFieldInfo = { key: string; name: string; description: string; ai_config: any }

export default function PatentListPage({ onPatentClick }: PatentListPageProps) {
  const {
    patents, totalPatents, currentProductId, loading,
    setPatents, setLoading, selectedIds, toggleSelect, clearSelection, setSelectedIds,
  } = useAppStore()

  const [page, setPage] = useState(1)
  const [pageSize] = useState(50)
  const [searchText, setSearchText] = useState('')
  const [legalStatusFilter, setLegalStatusFilter] = useState('')
  const [categoryFilter, setCategoryFilter] = useState('')
  const [riskFilter, setRiskFilter] = useState('')
  const [sortField, setSortField] = useState<SortField>('filing_date')
  const [sortOrder, setSortOrder] = useState<SortOrder>('desc')
  const [showBulkEdit, setShowBulkEdit] = useState(false)
  const [showBulkTag, setShowBulkTag] = useState(false)
  const [showAIBatch, setShowAIBatch] = useState(false)
  const [bulkModule, setBulkModule] = useState('')
  const [bulkRiskLevel, setBulkRiskLevel] = useState('')
  const [aiFieldKey, setAiFieldKey] = useState('')
  const [aiFields, setAiFields] = useState<AIFieldInfo[]>([])

  const loadPatents = useCallback(async () => {
    setLoading(true)
    try {
      const params: Record<string, any> = {
        page,
        page_size: pageSize,
        sort_by: sortField,
        sort_order: sortOrder,
      }
      if (searchText) params.search = searchText
      if (currentProductId) params.product_id = currentProductId
      if (legalStatusFilter) params.legal_status = legalStatusFilter
      if (categoryFilter) params.category = categoryFilter
      if (riskFilter) params.has_risk = riskFilter === 'true' ? true : riskFilter === 'false' ? false : undefined

      const result = await patentApi.list(params)
      setPatents(result.items, result.total)
    } catch (e) {
      console.error('Failed to load patents:', e)
    } finally {
      setLoading(false)
    }
  }, [page, pageSize, searchText, currentProductId, legalStatusFilter, categoryFilter, riskFilter, sortField, sortOrder, setPatents, setLoading])

  useEffect(() => {
    loadPatents()
  }, [loadPatents])

  useEffect(() => {
    // 加载 AI 字段列表供批量处理使用
    aiApi.listAIFields().then(setAiFields).catch(() => {})
  }, [])

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

  const handleSelectAll = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.checked) {
      setSelectedIds(patents.map(p => p.id))
    } else {
      clearSelection()
    }
  }

  const handleSort = (field: SortField) => {
    if (sortField === field) {
      setSortOrder(prev => prev === 'asc' ? 'desc' : 'asc')
    } else {
      setSortField(field)
      setSortOrder('desc')
    }
  }

  const handleBulkEditSave = async () => {
    const updates: Partial<Patent> = {}
    if (bulkModule) updates.module = bulkModule
    if (bulkRiskLevel) {
      updates.risk_level = bulkRiskLevel
      if (bulkRiskLevel !== 'none') updates.has_risk = true
      else updates.has_risk = false
    }
    if (Object.keys(updates).length === 0) {
      alert('请至少填写一个要修改的字段')
      return
    }
    try {
      await patentApi.bulkUpdate(selectedIds, updates)
      alert(`成功更新 ${selectedIds.length} 条专利`)
      setShowBulkEdit(false)
      setBulkModule('')
      setBulkRiskLevel('')
      clearSelection()
      loadPatents()
    } catch (e: any) {
      alert('批量更新失败: ' + (e?.response?.data?.detail || e?.message || ''))
    }
  }

  const handleAIBatchProcess = async () => {
    if (!aiFieldKey) {
      alert('请选择要处理的 AI 字段')
      return
    }
    try {
      const task = await aiApi.process(selectedIds, aiFieldKey)
      alert(`AI 任务已启动（任务ID: ${task.id}），可在"AI 任务"页面查看进度`)
      setShowAIBatch(false)
      setAiFieldKey('')
      clearSelection()
    } catch (e: any) {
      alert('启动 AI 任务失败: ' + (e?.response?.data?.detail || e?.message || '请先在设置页配置 LLM API'))
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
  const allSelected = patents.length > 0 && selectedIds.length === patents.length

  const SortHeader = ({ field, label, style }: { field: SortField; label: string; style?: React.CSSProperties }) => (
    <th
      style={{ padding: '10px 12px', textAlign: 'left', fontWeight: 600, whiteSpace: 'nowrap', cursor: 'pointer', ...style }}
      onClick={() => handleSort(field)}
    >
      {label}
      {sortField === field && (
        <span style={{ marginLeft: 4 }}>{sortOrder === 'asc' ? '▲' : '▼'}</span>
      )}
    </th>
  )

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

        <input
          type="text"
          className="form-input"
          style={{ maxWidth: 200 }}
          placeholder="分类筛选"
          value={categoryFilter}
          onChange={(e) => { setCategoryFilter(e.target.value); setPage(1) }}
        />
      </div>

      {selectedIds.length > 0 && (
        <div className="toolbar" style={{ background: '#eff6ff', padding: 10, borderRadius: 6, marginBottom: 12 }}>
          <span style={{ fontSize: 13, color: '#1e40af' }}>已选中 {selectedIds.length} 件专利</span>
          <button className="btn btn-secondary" style={{ fontSize: 12 }} onClick={() => setShowBulkEdit(true)}>批量编辑</button>
          <button className="btn btn-secondary" style={{ fontSize: 12 }} onClick={() => setShowBulkTag(true)}>批量打标签</button>
          <button className="btn btn-primary" style={{ fontSize: 12 }} onClick={() => setShowAIBatch(true)}>AI批量处理</button>
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
                    <input type="checkbox" checked={allSelected} onChange={handleSelectAll} />
                  </th>
                  <SortHeader field="application_number" label="申请号" />
                  <SortHeader field="title" label="标题" style={{ minWidth: 300 }} />
                  <SortHeader field="applicant" label="申请人" />
                  <th style={{ padding: '10px 12px', textAlign: 'left', fontWeight: 600, whiteSpace: 'nowrap' }}>发明人</th>
                  <SortHeader field="filing_date" label="申请日" />
                  <SortHeader field="legal_status" label="法律状态" />
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
                    onClick={() => onPatentClick(p.id)}
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

      {/* 批量编辑弹窗 */}
      {showBulkEdit && (
        <Modal title={`批量编辑 ${selectedIds.length} 条专利`} onClose={() => setShowBulkEdit(false)}>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 12, minWidth: 400 }}>
            <div>
              <label style={{ display: 'block', fontSize: 12, color: '#64748b', marginBottom: 4 }}>关联模块</label>
              <input className="form-input" value={bulkModule} onChange={e => setBulkModule(e.target.value)} placeholder="如：摄像头模块" />
            </div>
            <div>
              <label style={{ display: 'block', fontSize: 12, color: '#64748b', marginBottom: 4 }}>风险等级</label>
              <select className="form-input" value={bulkRiskLevel} onChange={e => setBulkRiskLevel(e.target.value)}>
                <option value="">不修改</option>
                <option value="none">无风险</option>
                <option value="low">低风险</option>
                <option value="medium">中风险</option>
                <option value="high">高风险</option>
                <option value="critical">严重风险</option>
              </select>
            </div>
            <div style={{ display: 'flex', gap: 8, justifyContent: 'flex-end', marginTop: 8 }}>
              <button className="btn btn-secondary" onClick={() => setShowBulkEdit(false)}>取消</button>
              <button className="btn btn-primary" onClick={handleBulkEditSave}>保存</button>
            </div>
          </div>
        </Modal>
      )}

      {/* 批量打标签弹窗（简化版：直接清空提示，后续 P1 接入标签管理） */}
      {showBulkTag && (
        <Modal title={`批量打标签 ${selectedIds.length} 条专利`} onClose={() => setShowBulkTag(false)}>
          <div style={{ minWidth: 400 }}>
            <p style={{ color: '#64748b', fontSize: 13 }}>
              标签管理功能将在 P1 阶段完善。当前可在专利详情页的"关联关系"Tab 中为单条专利设置标签。
            </p>
            <div style={{ display: 'flex', justifyContent: 'flex-end', marginTop: 16 }}>
              <button className="btn btn-secondary" onClick={() => setShowBulkTag(false)}>关闭</button>
            </div>
          </div>
        </Modal>
      )}

      {/* AI 批量处理弹窗 */}
      {showAIBatch && (
        <Modal title={`AI 批量处理 ${selectedIds.length} 条专利`} onClose={() => setShowAIBatch(false)}>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 12, minWidth: 400 }}>
            <div>
              <label style={{ display: 'block', fontSize: 12, color: '#64748b', marginBottom: 4 }}>选择 AI 字段</label>
              <select className="form-input" value={aiFieldKey} onChange={e => setAiFieldKey(e.target.value)}>
                <option value="">请选择...</option>
                {aiFields.map(f => (
                  <option key={f.key} value={f.key}>{f.name}</option>
                ))}
              </select>
            </div>
            {aiFields.length === 0 && (
              <p style={{ color: '#dc2626', fontSize: 12 }}>
                未找到 AI 字段。请确认后端已初始化 AI 字段模板，且已在设置页配置 LLM API。
              </p>
            )}
            <div style={{ display: 'flex', gap: 8, justifyContent: 'flex-end', marginTop: 8 }}>
              <button className="btn btn-secondary" onClick={() => setShowAIBatch(false)}>取消</button>
              <button className="btn btn-primary" onClick={handleAIBatchProcess}>启动 AI 任务</button>
            </div>
          </div>
        </Modal>
      )}
    </div>
  )
}

// 通用 Modal 组件
function Modal({ title, children, onClose }: { title: string; children: React.ReactNode; onClose: () => void }) {
  return (
    <div style={{
      position: 'fixed', top: 0, left: 0, right: 0, bottom: 0,
      background: 'rgba(0,0,0,0.5)', display: 'flex', alignItems: 'center', justifyContent: 'center',
      zIndex: 1000,
    }} onClick={onClose}>
      <div style={{
        background: 'white', borderRadius: 8, padding: 20, maxWidth: 600,
        boxShadow: '0 20px 25px -5px rgba(0,0,0,0.2)',
      }} onClick={e => e.stopPropagation()}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
          <h3 style={{ margin: 0, fontSize: 16, fontWeight: 600 }}>{title}</h3>
          <button onClick={onClose} style={{ border: 'none', background: 'transparent', fontSize: 20, cursor: 'pointer', color: '#64748b' }}>×</button>
        </div>
        {children}
      </div>
    </div>
  )
}
