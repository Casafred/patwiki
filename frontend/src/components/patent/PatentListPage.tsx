import { useState, useEffect, useCallback } from 'react'
import { patentApi, fieldApi, exportApi, aiApi, customFieldApi } from '../../api'
import { useAppStore } from '../../store'
import type { Patent, FieldMeta, CustomField } from '../../types'

interface PatentListPageProps {
  onPatentClick: (id: number) => void
}

type SortOrder = 'asc' | 'desc'

const DEFAULT_COLUMN_WIDTH = 150

export default function PatentListPage({ onPatentClick }: PatentListPageProps) {
  const {
    patents, totalPatents, currentProductId, currentDatabaseId, loading,
    setPatents, setLoading, selectedIds, toggleSelect, clearSelection, setSelectedIds,
  } = useAppStore()

  const [page, setPage] = useState(1)
  const [pageSize] = useState(50)
  const [searchText, setSearchText] = useState('')
  const [sortField, setSortField] = useState<string>('filing_date')
  const [sortOrder, setSortOrder] = useState<SortOrder>('desc')
  const [fields, setFields] = useState<FieldMeta[]>([])
  const [columnWidths, setColumnWidths] = useState<Record<string, number>>({})
  const [activeHeaderMenu, setActiveHeaderMenu] = useState<string | null>(null)
  const [editingCell, setEditingCell] = useState<{ patentId: number; fieldKey: string } | null>(null)
  const [resizing, setResizing] = useState<{ fieldKey: string; startX: number; startWidth: number } | null>(null)
  const [showFieldConfig, setShowFieldConfig] = useState(false)
  const [showBulkEdit, setShowBulkEdit] = useState(false)
  const [showBulkTag, setShowBulkTag] = useState(false)
  const [showAIBatch, setShowAIBatch] = useState(false)
  const [bulkModule, setBulkModule] = useState('')
  const [bulkRiskLevel, setBulkRiskLevel] = useState('')
  const [aiFieldKey, setAiFieldKey] = useState('')
  const [aiFields, setAiFields] = useState<{ key: string; name: string; description: string; ai_config: any }[]>([])
  const [filterValues, setFilterValues] = useState<Record<string, string>>({})
  const [showFilterPanel, setShowFilterPanel] = useState(false)
  const [customFields, setCustomFields] = useState<CustomField[]>([])
  const [newFieldName, setNewFieldName] = useState('')
  const [newFieldType, setNewFieldType] = useState<string>('text')
  const [newFieldOptions, setNewFieldOptions] = useState('')

  const loadFields = useCallback(async () => {
    try {
      const fieldsData = await fieldApi.list()
      setFields(fieldsData)
      const widths: Record<string, number> = {}
      fieldsData.forEach(f => {
        widths[f.key] = f.width || DEFAULT_COLUMN_WIDTH
      })
      setColumnWidths(widths)
    } catch (e) {
      console.error('Failed to load fields:', e)
    }
  }, [])

  const loadCustomFields = useCallback(async () => {
    try {
      const cf = await customFieldApi.list()
      setCustomFields(cf)
    } catch (e) {
      console.error('Failed to load custom fields:', e)
    }
  }, [])

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
      // P0-11：库筛选（限定当前库）
      if (currentDatabaseId !== null && currentDatabaseId !== undefined) {
        params.database_id = currentDatabaseId
      }
      if (currentProductId) params.product_id = currentProductId

      const customFilters: Record<string, any> = {}
      Object.entries(filterValues).forEach(([key, value]) => {
        if (value) {
          const field = fields.find(f => f.key === key)
          if (field && !field.is_system) {
            customFilters[key] = { contains: value }
          } else {
            params[key] = value
          }
        }
      })
      if (Object.keys(customFilters).length > 0) {
        params.custom_filters = JSON.stringify(customFilters)
      }

      const result = await patentApi.list(params)
      setPatents(result.items, result.total)
    } catch (e) {
      console.error('Failed to load patents:', e)
    } finally {
      setLoading(false)
    }
  }, [page, pageSize, searchText, currentProductId, currentDatabaseId, sortField, sortOrder, filterValues, fields, setPatents, setLoading])

  useEffect(() => {
    loadFields()
    loadCustomFields()
  }, [loadFields, loadCustomFields])

  useEffect(() => {
    if (fields.length > 0) {
      loadPatents()
    }
  }, [loadPatents, fields.length])

  useEffect(() => {
    aiApi.listAIFields().then(setAiFields).catch(() => {})
  }, [])

  useEffect(() => {
    const handleMouseMove = (e: MouseEvent) => {
      if (resizing) {
        const diff = e.clientX - resizing.startX
        const newWidth = Math.max(80, resizing.startWidth + diff)
        setColumnWidths(prev => ({ ...prev, [resizing.fieldKey]: newWidth }))
      }
    }
    const handleMouseUp = () => {
      setResizing(null)
    }
    if (resizing) {
      document.addEventListener('mousemove', handleMouseMove)
      document.addEventListener('mouseup', handleMouseUp)
      document.body.style.cursor = 'col-resize'
      document.body.style.userSelect = 'none'
    }
    return () => {
      document.removeEventListener('mousemove', handleMouseMove)
      document.removeEventListener('mouseup', handleMouseUp)
      document.body.style.cursor = ''
      document.body.style.userSelect = ''
    }
  }, [resizing])

  useEffect(() => {
    const handleClickOutside = (e: MouseEvent) => {
      if (activeHeaderMenu) {
        const target = e.target as HTMLElement
        if (!target.closest('.col-header-menu') && !target.closest('.col-header-trigger')) {
          setActiveHeaderMenu(null)
        }
      }
    }
    document.addEventListener('click', handleClickOutside)
    return () => document.removeEventListener('click', handleClickOutside)
  }, [activeHeaderMenu])

  const handleSearch = (e: React.FormEvent) => {
    e.preventDefault()
    setPage(1)
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

  const handleSort = (fieldKey: string) => {
    const field = fields.find(f => f.key === fieldKey)
    if (!field?.sortable) return
    if (sortField === fieldKey) {
      setSortOrder(prev => prev === 'asc' ? 'desc' : 'asc')
    } else {
      setSortField(fieldKey)
      setSortOrder('desc')
    }
    setActiveHeaderMenu(null)
  }

  const handleCellClick = (patentId: number, fieldKey: string, e: React.MouseEvent) => {
    const field = fields.find(f => f.key === fieldKey)
    if (!field?.editable) {
      onPatentClick(patentId)
      return
    }
    if ((e.target as HTMLElement).tagName === 'INPUT' || (e.target as HTMLElement).tagName === 'SELECT') {
      return
    }
    setEditingCell({ patentId, fieldKey })
  }

  const handleCellSave = async (patentId: number, fieldKey: string, value: any) => {
    try {
      await patentApi.updateCell(patentId, fieldKey, value)
      setEditingCell(null)
      loadPatents()
    } catch (e: any) {
      alert('保存失败: ' + (e?.response?.data?.detail || e?.message || ''))
    }
  }

  const handleToggleFieldVisible = (fieldKey: string) => {
    setFields(prev => prev.map(f =>
      f.key === fieldKey ? { ...f, visible: !f.visible } : f
    ))
    setActiveHeaderMenu(null)
  }

  const handleCreateCustomField = async () => {
    if (!newFieldName.trim()) {
      alert('请输入字段名称')
      return
    }
    try {
      const key = newFieldName.toLowerCase().replace(/\s+/g, '_') + '_' + Date.now().toString(36)
      await customFieldApi.create({
        key,
        name: newFieldName.trim(),
        field_type: newFieldType,
        options: newFieldType === 'select' || newFieldType === 'multiselect'
          ? newFieldOptions.split('\n').map(s => s.trim()).filter(Boolean)
          : undefined,
        is_active: true,
        sort_order: fields.length,
      })
      setNewFieldName('')
      setNewFieldType('text')
      setNewFieldOptions('')
      await loadFields()
      await loadCustomFields()
      loadPatents()
    } catch (e: any) {
      alert('创建字段失败: ' + (e?.response?.data?.detail || e?.message || ''))
    }
  }

  const handleDeleteCustomField = async (id: number) => {
    if (!confirm('确定要删除此字段吗？该字段的所有数据将被保留但不再显示。')) return
    try {
      await customFieldApi.delete(id)
      await loadFields()
      await loadCustomFields()
    } catch (e: any) {
      alert('删除失败: ' + (e?.response?.data?.detail || e?.message || ''))
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

  const getFieldValue = (patent: Patent, fieldKey: string): any => {
    const field = fields.find(f => f.key === fieldKey)
    if (!field) return null
    if (field.is_system) {
      return (patent as any)[fieldKey]
    }
    return patent.custom_fields?.[fieldKey] ?? patent.ai_fields?.[fieldKey] ?? null
  }

  const formatValue = (value: any, field: FieldMeta): string => {
    if (value === null || value === undefined || value === '') return '-'
    if (field.field_type === 'date' && value) {
      try {
        return new Date(value).toLocaleDateString('zh-CN')
      } catch {
        return String(value)
      }
    }
    if (field.field_type === 'boolean') {
      return value ? '是' : '否'
    }
    if (Array.isArray(value)) {
      return value.join(', ')
    }
    return String(value)
  }

  const getStatusText = (status?: string) => {
    const map: Record<string, string> = {
      granted: '授权', examining: '实审中', published: '公开',
      rejected: '驳回', withdrawn: '撤回', deemed_withdrawn: '视撤',
      expired: '终止', abandoned: '放弃', pending: '待审', unknown: '未知',
    }
    return map[status || 'unknown'] || status || '未知'
  }

  const getRiskText = (level?: string, hasRisk?: boolean) => {
    if (!hasRisk) return '-'
    const map: Record<string, string> = {
      critical: '严重', high: '高', medium: '中', low: '低', none: '无',
    }
    return map[level || 'none'] || '-'
  }

  const visibleFields = fields.filter(f => f.visible !== false)
  const totalPages = Math.ceil(totalPatents / pageSize)
  const allSelected = patents.length > 0 && selectedIds.length === patents.length
  const hasActiveFilters = Object.values(filterValues).some(v => v)

  const renderCellEditor = (patent: Patent, field: FieldMeta, value: any) => {
    const save = (v: any) => handleCellSave(patent.id, field.key, v)
    const cancel = () => setEditingCell(null)

    const commonStyle: React.CSSProperties = {
      width: '100%',
      padding: '4px 8px',
      border: '1px solid #3b82f6',
      borderRadius: 3,
      fontSize: 13,
      outline: 'none',
      background: '#fff',
    }

    if (field.field_type === 'select' && field.options) {
      return (
        <select
          style={commonStyle}
          autoFocus
          defaultValue={value || ''}
          onBlur={(e) => save(e.target.value || null)}
          onChange={(e) => {
            if (e.target.value) save(e.target.value)
          }}
        >
          <option value="">-</option>
          {field.options.map(opt => (
            <option key={opt} value={opt}>{opt}</option>
          ))}
        </select>
      )
    }

    if (field.field_type === 'boolean') {
      return (
        <select
          style={commonStyle}
          autoFocus
          defaultValue={value ? 'true' : value === false ? 'false' : ''}
          onBlur={(e) => save(e.target.value === 'true' ? true : e.target.value === 'false' ? false : null)}
        >
          <option value="">-</option>
          <option value="true">是</option>
          <option value="false">否</option>
        </select>
      )
    }

    if (field.field_type === 'longtext') {
      return (
        <textarea
          style={{ ...commonStyle, minHeight: 60, resize: 'vertical' }}
          autoFocus
          defaultValue={value || ''}
          onBlur={(e) => save(e.target.value || null)}
          onKeyDown={(e) => {
            if (e.key === 'Escape') cancel()
            if (e.key === 'Enter' && e.ctrlKey) save((e.target as HTMLTextAreaElement).value)
          }}
        />
      )
    }

    return (
      <input
        type={field.field_type === 'number' ? 'number' : field.field_type === 'date' ? 'date' : 'text'}
        style={commonStyle}
        autoFocus
        defaultValue={value || ''}
        onBlur={(e) => save(e.target.value || null)}
        onKeyDown={(e) => {
          if (e.key === 'Escape') cancel()
          if (e.key === 'Enter') save((e.target as HTMLInputElement).value)
        }}
      />
    )
  }

  const renderCellContent = (patent: Patent, field: FieldMeta) => {
    const value = getFieldValue(patent, field.key)
    const isEditing = editingCell?.patentId === patent.id && editingCell?.fieldKey === field.key

    if (isEditing) {
      return renderCellEditor(patent, field, value)
    }

    if (field.key === 'legal_status') {
      const status = value as string
      return (
        <span className={`status-badge status-${status || 'unknown'}`}>
          {getStatusText(status)}
        </span>
      )
    }

    if (field.key === 'risk_level' || field.key === 'has_risk') {
      const hasRisk = patent.has_risk
      const level = patent.risk_level
      if (!hasRisk) return <span style={{ color: '#94a3b8', fontSize: 12 }}>-</span>
      return (
        <span className={`risk-badge risk-${level || 'low'}`}>
          {getRiskText(level, hasRisk)}
        </span>
      )
    }

    if (field.key === 'title') {
      return (
        <div>
          <div style={{ fontWeight: 500, color: '#0f172a' }}>{value || '-'}</div>
          {(patent.category || patent.subcategory) && (
            <div style={{ fontSize: 11, color: '#94a3b8', marginTop: 2 }}>
              {patent.category}{patent.subcategory ? ` / ${patent.subcategory}` : ''}
            </div>
          )}
        </div>
      )
    }

    if (field.key === 'application_number' || field.key === 'publication_number') {
      return (
        <span style={{ fontFamily: 'monospace', fontSize: 12 }}>
          {value || '-'}
        </span>
      )
    }

    const displayValue = formatValue(value, field)
    const isTruncated = typeof displayValue === 'string' && displayValue.length > 50

    return (
      <span
        style={{
          color: displayValue === '-' ? '#94a3b8' : '#374151',
          display: 'block',
          overflow: 'hidden',
          textOverflow: 'ellipsis',
          whiteSpace: field.field_type === 'longtext' ? 'normal' : 'nowrap',
          lineHeight: field.field_type === 'longtext' ? 1.5 : 1.4,
        }}
        title={typeof displayValue === 'string' ? displayValue : undefined}
      >
        {isTruncated ? displayValue.slice(0, 50) + '...' : displayValue}
      </span>
    )
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%', background: '#f3f4f6' }}>
      <div className="datagrid-toolbar">
        <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
          <h2 style={{ margin: 0, fontSize: 18, fontWeight: 600, color: '#111827' }}>专利列表</h2>
          <span style={{ fontSize: 13, color: '#6b7280' }}>
            共 {totalPatents} 件{currentProductId ? ' · 当前产品筛选中' : ''}
          </span>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <form onSubmit={handleSearch} style={{ display: 'flex', gap: 4 }}>
            <input
              type="text"
              className="form-input"
              style={{ width: 260, height: 32, fontSize: 13 }}
              placeholder="搜索专利号、标题、申请人..."
              value={searchText}
              onChange={(e) => setSearchText(e.target.value)}
            />
          </form>
          <button
            className={`btn btn-sm ${hasActiveFilters ? 'btn-primary' : 'btn-secondary'}`}
            onClick={() => setShowFilterPanel(!showFilterPanel)}
          >
            筛选{hasActiveFilters ? ' (已激活)' : ''}
          </button>
          <button className="btn btn-sm btn-secondary" onClick={() => setShowFieldConfig(true)}>
            字段
          </button>
          <button className="btn btn-sm btn-secondary" onClick={handleExport}>
            导出
          </button>
        </div>
      </div>

      {showFilterPanel && (
        <div className="filter-panel">
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 12, padding: 12 }}>
            {visibleFields.filter(f => f.filterable).slice(0, 8).map(field => (
              <div key={field.key} style={{ display: 'flex', flexDirection: 'column', gap: 4, minWidth: 140 }}>
                <label style={{ fontSize: 11, color: '#6b7280', fontWeight: 500 }}>{field.name}</label>
                {field.field_type === 'select' && field.options ? (
                  <select
                    className="form-input"
                    style={{ height: 30, fontSize: 12 }}
                    value={filterValues[field.key] || ''}
                    onChange={(e) => {
                      setFilterValues(prev => ({ ...prev, [field.key]: e.target.value }))
                      setPage(1)
                    }}
                  >
                    <option value="">全部</option>
                    {field.options.map(opt => (
                      <option key={opt} value={opt}>{opt}</option>
                    ))}
                  </select>
                ) : (
                  <input
                    type="text"
                    className="form-input"
                    style={{ height: 30, fontSize: 12 }}
                    placeholder={`搜索${field.name}...`}
                    value={filterValues[field.key] || ''}
                    onChange={(e) => {
                      setFilterValues(prev => ({ ...prev, [field.key]: e.target.value }))
                      setPage(1)
                    }}
                  />
                )}
              </div>
            ))}
            <div style={{ display: 'flex', alignItems: 'flex-end' }}>
              <button
                className="btn btn-sm btn-secondary"
                onClick={() => { setFilterValues({}); setPage(1) }}
              >
                重置
              </button>
            </div>
          </div>
        </div>
      )}

      {selectedIds.length > 0 && (
        <div className="selection-bar">
          <span style={{ fontSize: 13, color: '#1e40af', fontWeight: 500 }}>
            已选中 {selectedIds.length} 件专利
          </span>
          <div style={{ display: 'flex', gap: 6 }}>
            <button className="btn btn-xs btn-secondary" onClick={() => setShowBulkEdit(true)}>批量编辑</button>
            <button className="btn btn-xs btn-secondary" onClick={() => setShowBulkTag(true)}>批量打标签</button>
            <button className="btn btn-xs btn-primary" onClick={() => setShowAIBatch(true)}>AI批量处理</button>
          </div>
          <button className="btn btn-xs btn-ghost" onClick={clearSelection} style={{ marginLeft: 'auto' }}>
            取消选择
          </button>
        </div>
      )}

      <div className="data-grid-wrapper" onScroll={() => setActiveHeaderMenu(null)}>
        {loading ? (
          <div className="loading-state">
            <div className="spinner" style={{ width: 24, height: 24, borderWidth: 2, marginBottom: 12 }}></div>
            <span style={{ fontSize: 13, color: '#6b7280' }}>加载中...</span>
          </div>
        ) : patents.length === 0 ? (
          <div className="empty-state">
            <div style={{ fontSize: 40, marginBottom: 12, color: '#d1d5db' }}>[ ]</div>
            <div style={{ fontSize: 15, fontWeight: 500, color: '#374151', marginBottom: 6 }}>暂无专利数据</div>
            <div style={{ fontSize: 13, color: '#9ca3af' }}>点击右上角"导入"按钮导入专利数据，或先在左侧创建产品分类</div>
          </div>
        ) : (
          <table className="data-grid" style={{ minWidth: '100%' }}>
            <thead>
              <tr>
                <th className="col-checkbox" style={{ width: 40, minWidth: 40, maxWidth: 40 }}>
                  <input type="checkbox" checked={allSelected} onChange={handleSelectAll} />
                </th>
                {visibleFields.map(field => (
                  <th
                    key={field.key}
                    className={`${field.frozen ? 'col-frozen' : ''} ${sortField === field.key ? 'col-sorted' : ''}`}
                    style={{ width: columnWidths[field.key] || DEFAULT_COLUMN_WIDTH, minWidth: 80 }}
                  >
                    <div
                      className="col-header-trigger"
                      onClick={() => handleSort(field.key)}
                      style={{
                        display: 'flex',
                        alignItems: 'center',
                        justifyContent: 'space-between',
                        height: '100%',
                        padding: '0 10px',
                        cursor: field.sortable ? 'pointer' : 'default',
                      }}
                    >
                      <span style={{
                        fontSize: 12,
                        fontWeight: 500,
                        color: sortField === field.key ? '#111827' : '#6b7280',
                        overflow: 'hidden',
                        textOverflow: 'ellipsis',
                        whiteSpace: 'nowrap',
                      }}>
                        {field.name}
                        {sortField === field.key && (
                          <span style={{ marginLeft: 4, fontSize: 10, color: '#3b82f6' }}>
                            {sortOrder === 'asc' ? '↑' : '↓'}
                          </span>
                        )}
                      </span>
                      <button
                        className="col-header-trigger"
                        onClick={(e) => {
                          e.stopPropagation()
                          setActiveHeaderMenu(activeHeaderMenu === field.key ? null : field.key)
                        }}
                        style={{
                          width: 20,
                          height: 20,
                          display: 'flex',
                          alignItems: 'center',
                          justifyContent: 'center',
                          border: 'none',
                          background: 'transparent',
                          cursor: 'pointer',
                          color: '#9ca3af',
                          borderRadius: 3,
                          fontSize: 14,
                          flexShrink: 0,
                          marginLeft: 4,
                        }}
                        onMouseEnter={(e) => { (e.currentTarget as HTMLElement).style.background = '#e5e7eb' }}
                        onMouseLeave={(e) => { (e.currentTarget as HTMLElement).style.background = 'transparent' }}
                      >
                        ▾
                      </button>
                    </div>
                    <div
                      className="col-resize-handle"
                      onMouseDown={(e) => {
                        e.preventDefault()
                        e.stopPropagation()
                        setResizing({
                          fieldKey: field.key,
                          startX: e.clientX,
                          startWidth: columnWidths[field.key] || DEFAULT_COLUMN_WIDTH,
                        })
                      }}
                    />
                    {activeHeaderMenu === field.key && (
                      <div className="col-header-menu">
                        <div
                          className="menu-item"
                          onClick={() => handleSort(field.key)}
                        >
                          <span>{sortField === field.key && sortOrder === 'asc' ? '↓ 降序' : '↑ 升序'}</span>
                        </div>
                        {field.filterable && (
                          <div
                            className="menu-item"
                            onClick={() => {
                              setShowFilterPanel(true)
                              setActiveHeaderMenu(null)
                              setFilterValues(prev => ({ ...prev, [field.key]: prev[field.key] || '' }))
                            }}
                          >
                            <span>按此列筛选</span>
                          </div>
                        )}
                        <div className="menu-divider" />
                        <div
                          className="menu-item"
                          onClick={() => handleToggleFieldVisible(field.key)}
                        >
                          <span>隐藏此列</span>
                        </div>
                      </div>
                    )}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {patents.map((p) => (
                <tr
                  key={p.id}
                  className={selectedIds.includes(p.id) ? 'row-selected' : ''}
                  onClick={(e) => {
                    if ((e.target as HTMLElement).closest('input') ||
                        (e.target as HTMLElement).closest('select') ||
                        (e.target as HTMLElement).closest('textarea') ||
                        (e.target as HTMLElement).closest('button')) return
                    onPatentClick(p.id)
                  }}
                >
                  <td className="col-checkbox">
                    <input
                      type="checkbox"
                      checked={selectedIds.includes(p.id)}
                      onChange={() => toggleSelect(p.id)}
                      onClick={(e) => e.stopPropagation()}
                    />
                  </td>
                  {visibleFields.map(field => (
                    <td
                      key={field.key}
                      className={`${field.frozen ? 'col-frozen' : ''} ${field.editable ? 'cell-editable' : ''}`}
                      style={{
                        width: columnWidths[field.key] || DEFAULT_COLUMN_WIDTH,
                        maxWidth: columnWidths[field.key] || DEFAULT_COLUMN_WIDTH,
                        padding: field.field_type === 'longtext' ? '8px 10px' : '6px 10px',
                      }}
                      onClick={(e) => {
                        if (field.editable) {
                          e.stopPropagation()
                          handleCellClick(p.id, field.key, e)
                        }
                      }}
                    >
                      {renderCellContent(p, field)}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      <div className="datagrid-footer">
        <span style={{ fontSize: 12, color: '#6b7280' }}>
          第 {(page - 1) * pageSize + 1} - {Math.min(page * pageSize, totalPatents)} 条，共 {totalPatents} 条
        </span>
        <div style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
          <button
            className="btn btn-xs btn-secondary"
            disabled={page <= 1}
            onClick={() => setPage(page - 1)}
          >
            上一页
          </button>
          <span style={{ fontSize: 12, color: '#374151', padding: '0 8px' }}>
            {page} / {totalPages || 1}
          </span>
          <button
            className="btn btn-xs btn-secondary"
            disabled={page >= totalPages}
            onClick={() => setPage(page + 1)}
          >
            下一页
          </button>
        </div>
      </div>

      {showFieldConfig && (
      <Modal title="字段配置" onClose={() => setShowFieldConfig(false)} width={600}>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
          <div>
            <h4 style={{ margin: '0 0 8px', fontSize: 13, fontWeight: 600, color: '#374151' }}>显示的字段</h4>
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>
              {fields.map(field => (
                <label
                  key={field.key}
                  style={{
                    display: 'inline-flex',
                    alignItems: 'center',
                    gap: 4,
                    padding: '4px 8px',
                    background: field.visible !== false ? '#eff6ff' : '#f3f4f6',
                    border: `1px solid ${field.visible !== false ? '#bfdbfe' : '#e5e7eb'}`,
                    borderRadius: 4,
                    fontSize: 12,
                    cursor: 'pointer',
                  }}
                >
                  <input
                    type="checkbox"
                    checked={field.visible !== false}
                    onChange={() => handleToggleFieldVisible(field.key)}
                    style={{ margin: 0 }}
                  />
                  <span style={{ color: field.visible !== false ? '#1e40af' : '#6b7280' }}>
                    {field.name}
                    {field.is_system && <span style={{ color: '#9ca3af', marginLeft: 4 }}>(系统)</span>}
                  </span>
                  {!field.is_system && (
                    <button
                      onClick={(e) => {
                        e.preventDefault()
                        const cf = customFields.find(c => c.key === field.key)
                        if (cf) handleDeleteCustomField(cf.id)
                      }}
                      style={{
                        border: 'none',
                        background: 'transparent',
                        color: '#ef4444',
                        cursor: 'pointer',
                        fontSize: 14,
                        padding: '0 2px',
                        lineHeight: 1,
                      }}
                    >
                      ×
                    </button>
                  )}
                </label>
              ))}
            </div>
          </div>

          <div style={{ borderTop: '1px solid #e5e7eb', paddingTop: 16 }}>
            <h4 style={{ margin: '0 0 8px', fontSize: 13, fontWeight: 600, color: '#374151' }}>新建自定义字段</h4>
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 8, marginBottom: 8 }}>
              <input
                type="text"
                className="form-input"
                placeholder="字段名称"
                value={newFieldName}
                onChange={(e) => setNewFieldName(e.target.value)}
                style={{ height: 32, fontSize: 13 }}
              />
              <select
                className="form-input"
                value={newFieldType}
                onChange={(e) => setNewFieldType(e.target.value)}
                style={{ height: 32, fontSize: 13 }}
              >
                <option value="text">单行文本</option>
                <option value="longtext">多行文本</option>
                <option value="number">数字</option>
                <option value="date">日期</option>
                <option value="select">单选</option>
                <option value="boolean">是/否</option>
              </select>
            </div>
            {(newFieldType === 'select') && (
              <textarea
                className="form-input"
                placeholder="选项（每行一个）"
                value={newFieldOptions}
                onChange={(e) => setNewFieldOptions(e.target.value)}
                style={{ fontSize: 12, minHeight: 60, marginBottom: 8 }}
              />
            )}
            <button className="btn btn-sm btn-primary" onClick={handleCreateCustomField}>
              添加字段
            </button>
          </div>

          <div style={{ display: 'flex', justifyContent: 'flex-end', paddingTop: 8, borderTop: '1px solid #e5e7eb' }}>
            <button className="btn btn-sm btn-secondary" onClick={() => setShowFieldConfig(false)}>
              完成
            </button>
          </div>
        </div>
      </Modal>
      )}

      {showBulkEdit && (
        <Modal title={`批量编辑 ${selectedIds.length} 条专利`} onClose={() => setShowBulkEdit(false)}>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 12, minWidth: 360 }}>
            <div>
              <label style={{ display: 'block', fontSize: 12, color: '#6b7280', marginBottom: 4 }}>关联模块</label>
              <input className="form-input" value={bulkModule} onChange={e => setBulkModule(e.target.value)} placeholder="如：摄像头模块" />
            </div>
            <div>
              <label style={{ display: 'block', fontSize: 12, color: '#6b7280', marginBottom: 4 }}>风险等级</label>
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

      {showBulkTag && (
        <Modal title={`批量打标签 ${selectedIds.length} 条专利`} onClose={() => setShowBulkTag(false)}>
          <div style={{ minWidth: 360 }}>
            <p style={{ color: '#6b7280', fontSize: 13, margin: 0 }}>
              标签管理功能将在后续版本完善。当前可在专利详情页中为单条专利设置标签。
            </p>
            <div style={{ display: 'flex', justifyContent: 'flex-end', marginTop: 16 }}>
              <button className="btn btn-secondary" onClick={() => setShowBulkTag(false)}>关闭</button>
            </div>
          </div>
        </Modal>
      )}

      {showAIBatch && (
        <Modal title={`AI 批量处理 ${selectedIds.length} 条专利`} onClose={() => setShowAIBatch(false)}>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 12, minWidth: 360 }}>
            <div>
              <label style={{ display: 'block', fontSize: 12, color: '#6b7280', marginBottom: 4 }}>选择 AI 字段</label>
              <select className="form-input" value={aiFieldKey} onChange={e => setAiFieldKey(e.target.value)}>
                <option value="">请选择...</option>
                {aiFields.map(f => (
                  <option key={f.key} value={f.key}>{f.name}</option>
                ))}
              </select>
            </div>
            {aiFields.length === 0 && (
              <p style={{ color: '#dc2626', fontSize: 12, margin: 0 }}>
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

function Modal({ title, children, onClose, width = 480 }: {
  title: string
  children: React.ReactNode
  onClose: () => void
  width?: number
}) {
  return (
    <div
      style={{
        position: 'fixed', top: 0, left: 0, right: 0, bottom: 0,
        background: 'rgba(0,0,0,0.45)', display: 'flex', alignItems: 'center', justifyContent: 'center',
        zIndex: 1000, padding: 20,
      }}
      onClick={onClose}
    >
      <div
        style={{
          background: 'white', borderRadius: 8, padding: 20, width: '100%', maxWidth: width,
          maxHeight: '90vh', overflowY: 'auto',
          boxShadow: '0 20px 60px rgba(0,0,0,0.15)',
        }}
        onClick={e => e.stopPropagation()}
      >
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
          <h3 style={{ margin: 0, fontSize: 15, fontWeight: 600, color: '#111827' }}>{title}</h3>
          <button
            onClick={onClose}
            style={{
              border: 'none', background: 'transparent', fontSize: 20, cursor: 'pointer',
              color: '#9ca3af', padding: 4, lineHeight: 1,
            }}
          >
            ×
          </button>
        </div>
        {children}
      </div>
    </div>
  )
}
