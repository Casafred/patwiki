import { useState, useEffect, useCallback } from 'react'
import { patentApi, fieldApi, exportApi, aiApi, customFieldApi, analyticsApi } from '../../api'
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
  const [searchInputText, setSearchInputText] = useState('')
  const [sortField, setSortField] = useState<string>('filing_date')
  const [sortOrder, setSortOrder] = useState<SortOrder>('desc')
  const [fields, setFields] = useState<FieldMeta[]>([])
  const [columnWidths, setColumnWidths] = useState<Record<string, number>>({})
  const [activeHeaderMenu, setActiveHeaderMenu] = useState<string | null>(null)
  const [headerFilterText, setHeaderFilterText] = useState<string>('')
  const [editingCell, setEditingCell] = useState<{ patentId: number; fieldKey: string } | null>(null)
  const [resizing, setResizing] = useState<{ fieldKey: string; startX: number; startWidth: number } | null>(null)
  const [showFieldConfig, setShowFieldConfig] = useState(false)
  const [showBulkEdit, setShowBulkEdit] = useState(false)
  const [showBulkTag, setShowBulkTag] = useState(false)
  const [showAIBatch, setShowAIBatch] = useState(false)
  const [showInsertAIColumn, setShowInsertAIColumn] = useState(false)
  const [insertColType, setInsertColType] = useState<'text' | 'longtext' | 'number' | 'date' | 'select' | 'boolean' | 'ai_field'>('text')
  const [insertColFrozen, setInsertColFrozen] = useState(false)
  const [newAIColumnName, setNewAIColumnName] = useState('')
  const [newAIPrompt, setNewAIPrompt] = useState('')
  const [newColumnOptions, setNewColumnOptions] = useState('')
  const [creatingAIColumn, setCreatingAIColumn] = useState(false)
  const [frozenFields, setFrozenFields] = useState<Set<string>>(new Set())
  const [showColumnStats, setShowColumnStats] = useState(false)
  const [statsFieldKey, setStatsFieldKey] = useState('')
  const [statsData, setStatsData] = useState<{ value: string; count: number; percentage: number }[]>([])
  const [statsLoading, setStatsLoading] = useState(false)
  const [showStatsToTags, setShowStatsToTags] = useState(false)
  const [tagGroupName, setTagGroupName] = useState('自动分类')
  const [autoApplyTags, setAutoApplyTags] = useState(true)
  const [convertingTags, setConvertingTags] = useState(false)
  const [bulkModule, setBulkModule] = useState('')
  const [bulkRiskLevel, setBulkRiskLevel] = useState('')
  const [aiFieldKey, setAiFieldKey] = useState('')
  const [aiFields, setAiFields] = useState<{ key: string; name: string; description: string; ai_config: any }[]>([])
  const [filterValues, setFilterValues] = useState<Record<string, string>>({})
  const [customFields, setCustomFields] = useState<CustomField[]>([])
  const [newFieldName, setNewFieldName] = useState('')
  const [newFieldType, setNewFieldType] = useState<string>('text')
  const [newFieldOptions, setNewFieldOptions] = useState('')
  const [pageInputValue, setPageInputValue] = useState('')
  const [aiProcessingRow, setAiProcessingRow] = useState<number | null>(null)

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
      if (currentDatabaseId !== null && currentDatabaseId !== undefined) {
        params.database_id = currentDatabaseId
      }
      if (currentProductId) params.product_id = currentProductId

      const allFilters: Record<string, any> = {}
      Object.entries(filterValues).forEach(([key, value]) => {
        if (value) {
          allFilters[key] = { contains: value }
        }
      })
      if (Object.keys(allFilters).length > 0) {
        params.filters = JSON.stringify(allFilters)
      }

      const result = await patentApi.list(params)
      setPatents(result.items, result.total)
    } catch (e) {
      console.error('Failed to load patents:', e)
    } finally {
      setLoading(false)
    }
  }, [page, pageSize, searchText, currentProductId, currentDatabaseId, sortField, sortOrder, filterValues, setPatents, setLoading])

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
    setPageInputValue(String(page))
  }, [page])

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
          setHeaderFilterText('')
        }
      }
    }
    document.addEventListener('click', handleClickOutside)
    return () => document.removeEventListener('click', handleClickOutside)
  }, [activeHeaderMenu])

  const handleSearch = (e: React.FormEvent) => {
    e.preventDefault()
    setSearchText(searchInputText)
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
    if ((e.target as HTMLElement).closest('.cell-action-btn')) return
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

  const handleHeaderFilterApply = (fieldKey: string) => {
    setFilterValues(prev => ({ ...prev, [fieldKey]: headerFilterText }))
    setPage(1)
    setActiveHeaderMenu(null)
    setHeaderFilterText('')
  }

  const handleHeaderFilterClear = (fieldKey: string) => {
    setFilterValues(prev => {
      const next = { ...prev }
      delete next[fieldKey]
      return next
    })
    setHeaderFilterText('')
    setPage(1)
  }

  const handleClearAllFilters = () => {
    setFilterValues({})
    setSearchText('')
    setSearchInputText('')
    setPage(1)
  }

  const handleQuickAI = async (patentId: number) => {
    if (aiFields.length === 0) {
      alert('未找到AI字段，请先在设置页配置LLM API')
      return
    }
    const firstAiField = aiFields[0]
    setAiProcessingRow(patentId)
    try {
      const task = await aiApi.process([patentId], firstAiField.key)
      const poll = async () => {
        try {
          const t = await aiApi.getTask(task.id)
          if (t.status === 'running' || t.status === 'pending') {
            setTimeout(poll, 1500)
          } else {
            setAiProcessingRow(null)
            loadPatents()
          }
        } catch {
          setAiProcessingRow(null)
        }
      }
      setTimeout(poll, 1500)
    } catch (e: any) {
      alert('AI处理失败: ' + (e?.response?.data?.detail || e?.message || ''))
      setAiProcessingRow(null)
    }
  }

  const handleInsertAIColumn = async (processAll: boolean) => {
    if (!newAIColumnName.trim()) {
      alert('请输入新列名称')
      return
    }
    const isAI = insertColType === 'ai_field'
    if (isAI && !newAIPrompt.trim()) {
      alert('AI列必须填写分析提示词（Prompt）')
      return
    }
    if ((insertColType === 'select') && !newColumnOptions.trim()) {
      alert('单选列必须填写候选项（每行一个）')
      return
    }
    setCreatingAIColumn(true)
    try {
      const key = (isAI ? 'ai_' : 'cf_') + Date.now().toString(36)
      const payload: any = {
        key,
        name: newAIColumnName.trim(),
        field_type: isAI ? 'ai_field' : insertColType,
        is_active: true,
        sort_order: fields.length,
      }
      if (insertColType === 'select' && newColumnOptions.trim()) {
        payload.options = newColumnOptions.split('\n').map(s => s.trim()).filter(Boolean)
      }
      if (isAI) {
        payload.ai_config = {
          prompt_template: newAIPrompt.trim(),
          ai_enabled: true,
        }
      }
      await customFieldApi.create(payload)
      // 记录冻结状态
      if (insertColFrozen) {
        setFrozenFields(prev => new Set(prev).add(key))
      }
      await loadFields()
      await loadCustomFields()
      // AI列立即触发处理
      if (isAI) {
        const targetIds = processAll ? patents.map(p => p.id) : selectedIds
        if (targetIds.length === 0) {
          alert('AI列已创建。选中专利后可点击行内 ✨ 按钮或使用"AI批量处理"运行该列')
        } else {
          try {
            const task = await aiApi.process(targetIds, key)
            alert(`AI列已创建，任务已启动（ID: ${task.id}），可在"AI 任务"页面查看进度`)
          } catch (e: any) {
            alert('AI列已创建，但启动AI任务失败: ' + (e?.response?.data?.detail || e?.message || '请先在设置页配置 LLM API'))
          }
        }
      } else {
        alert(`新列"${newAIColumnName.trim()}"已创建`)
      }
      setShowInsertAIColumn(false)
      setNewAIColumnName('')
      setNewAIPrompt('')
      setNewColumnOptions('')
      setInsertColType('text')
      setInsertColFrozen(false)
      loadPatents()
    } catch (e: any) {
      alert('创建列失败: ' + (e?.response?.data?.detail || e?.message || ''))
    } finally {
      setCreatingAIColumn(false)
    }
  }

  const openInsertAIDialog = (anchorFieldKey?: string) => {
    setActiveHeaderMenu(null)
    // 预填一个引用锚点列的 prompt 模板
    if (anchorFieldKey) {
      const f = fields.find(x => x.key === anchorFieldKey)
      if (f) {
        setInsertColType('ai_field')
        setNewAIPrompt(`请基于以下内容进行分析：\n{${anchorFieldKey}}\n\n要求：简洁准确地输出结果。`)
      }
    }
    setShowInsertAIColumn(true)
  }

  const handleToggleFreeze = (fieldKey: string) => {
    setActiveHeaderMenu(null)
    setFrozenFields(prev => {
      const next = new Set(prev)
      if (next.has(fieldKey)) {
        next.delete(fieldKey)
      } else {
        next.add(fieldKey)
      }
      return next
    })
  }

  const openColumnStats = async (fieldKey: string) => {
    setActiveHeaderMenu(null)
    setStatsFieldKey(fieldKey)
    setShowColumnStats(true)
    setStatsLoading(true)
    setStatsData([])
    try {
      const result = await analyticsApi.columnStats({
        field_key: fieldKey,
        database_id: currentDatabaseId ?? undefined,
        product_id: currentProductId || undefined,
      })
      setStatsData(result.items)
    } catch (e: any) {
      alert('统计失败: ' + (e?.response?.data?.detail || e?.message || ''))
    } finally {
      setStatsLoading(false)
    }
  }

  const handleStatsToTags = async () => {
    if (!statsFieldKey) return
    setConvertingTags(true)
    try {
      const result = await analyticsApi.statsToTags({
        field_key: statsFieldKey,
        group_name: tagGroupName.trim() || '自动分类',
        auto_apply_to_patents: autoApplyTags,
        database_id: currentDatabaseId ?? undefined,
        product_id: currentProductId || undefined,
      })
      alert(`已创建标签组"${result.group.name}"，共 ${result.total_tags} 个标签${autoApplyTags ? `，已为 ${result.applied_count} 条专利打标` : ''}`)
      setShowStatsToTags(false)
      setShowColumnStats(false)
    } catch (e: any) {
      alert('转换失败: ' + (e?.response?.data?.detail || e?.message || ''))
    } finally {
      setConvertingTags(false)
    }
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

  const handlePageJump = () => {
    const p = parseInt(pageInputValue)
    if (!isNaN(p) && p >= 1 && p <= totalPages) {
      setPage(p)
    } else {
      setPageInputValue(String(page))
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
  const hasActiveFilters = Object.values(filterValues).some(v => v) || !!searchText

  const pageNumbers = () => {
    const pages: (number | string)[] = []
    const maxVisible = 5
    if (totalPages <= maxVisible + 2) {
      for (let i = 1; i <= totalPages; i++) pages.push(i)
    } else {
      pages.push(1)
      let start = Math.max(2, page - 2)
      let end = Math.min(totalPages - 1, page + 2)
      if (start > 2) pages.push('...')
      for (let i = start; i <= end; i++) pages.push(i)
      if (end < totalPages - 1) pages.push('...')
      pages.push(totalPages)
    }
    return pages
  }

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
          <div style={{ fontWeight: 500, color: '#2563eb', cursor: 'pointer' }}
               onClick={(e) => { e.stopPropagation(); onPatentClick(patent.id) }}
               onMouseEnter={(e) => { (e.currentTarget as HTMLElement).style.textDecoration = 'underline' }}
               onMouseLeave={(e) => { (e.currentTarget as HTMLElement).style.textDecoration = 'none' }}
          >
            {value || '-'}
          </div>
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
        <span
          style={{ fontFamily: 'monospace', fontSize: 12, cursor: 'pointer', color: '#2563eb' }}
          onClick={(e) => { e.stopPropagation(); onPatentClick(patent.id) }}
          onMouseEnter={(e) => { (e.currentTarget as HTMLElement).style.textDecoration = 'underline' }}
          onMouseLeave={(e) => { (e.currentTarget as HTMLElement).style.textDecoration = 'none' }}
        >
          {value || '-'}
        </span>
      )
    }

    const displayValue = formatValue(value, field)

    return (
      <span
        style={{
          color: displayValue === '-' ? '#94a3b8' : '#374151',
          display: 'block',
          whiteSpace: 'normal',
          wordBreak: 'break-word',
          overflowWrap: 'anywhere',
          lineHeight: 1.5,
        }}
      >
        {displayValue}
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
              value={searchInputText}
              onChange={(e) => setSearchInputText(e.target.value)}
            />
          </form>
          <button
            className={`btn btn-sm ${hasActiveFilters ? 'btn-primary' : 'btn-secondary'}`}
            onClick={handleClearAllFilters}
            style={{ display: hasActiveFilters ? 'inline-flex' : 'none' }}
          >
            清除筛选
          </button>
          <button className="btn btn-sm btn-secondary" onClick={() => setShowFieldConfig(true)}>
            字段
          </button>
          <button
            className="btn btn-sm btn-primary"
            onClick={() => openInsertAIDialog()}
            title="插入新列（普通列或AI列）"
          >
            + 插入新列
          </button>
          <button className="btn btn-sm btn-secondary" onClick={handleExport}>
            导出
          </button>
        </div>
      </div>

      {Object.keys(filterValues).length > 0 && (
        <div style={{ display: 'flex', gap: 6, padding: '6px 20px', background: '#fff', borderBottom: '1px solid #e5e7eb', flexWrap: 'wrap', alignItems: 'center' }}>
          <span style={{ fontSize: 11, color: '#6b7280' }}>已筛选：</span>
          {Object.entries(filterValues).filter(([_, v]) => v).map(([key, value]) => {
            const field = fields.find(f => f.key === key)
            return (
              <span key={key} className="filter-chip">
                {field?.name || key}: {value}
                <span className="chip-remove" onClick={() => handleHeaderFilterClear(key)}>×</span>
              </span>
            )
          })}
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
                <th className="col-action" style={{ width: 70, minWidth: 70, maxWidth: 70, position: 'sticky', left: 40, zIndex: 16, background: '#f9fafb' }}>
                  <span style={{ fontSize: 12, color: '#6b7280', padding: '0 10px' }}>操作</span>
                </th>
                {visibleFields.map(field => {
                  const hasFilter = !!filterValues[field.key]
                  const isFilterable = field.filterable !== false
                  const isFrozen = field.frozen || frozenFields.has(field.key)
                  // 计算冻结列的 left 偏移：checkbox(40) + 操作(70) + 前面所有冻结列宽度
                  let leftOffset = 40 + 70
                  if (isFrozen) {
                    for (const f of visibleFields) {
                      if (f.key === field.key) break
                      if (f.frozen || frozenFields.has(f.key)) {
                        leftOffset += columnWidths[f.key] || DEFAULT_COLUMN_WIDTH
                      }
                    }
                  }
                  return (
                    <th
                      key={field.key}
                      className={`${isFrozen ? 'col-frozen' : ''} ${sortField === field.key ? 'col-sorted' : ''} ${hasFilter ? 'col-filtered' : ''}`}
                      style={{
                        width: columnWidths[field.key] || DEFAULT_COLUMN_WIDTH,
                        minWidth: 80,
                        ...(isFrozen ? { position: 'sticky', left: leftOffset, zIndex: 15, background: '#f9fafb' } : {}),
                      }}
                    >
                      <div
                        style={{
                          display: 'flex',
                          alignItems: 'center',
                          justifyContent: 'space-between',
                          height: '100%',
                          padding: '0 10px',
                          cursor: field.sortable ? 'pointer' : 'default',
                          minHeight: 34,
                        }}
                        onClick={() => handleSort(field.key)}
                      >
                        <span style={{
                          fontSize: 12,
                          fontWeight: 500,
                          color: sortField === field.key ? '#111827' : hasFilter ? '#2563eb' : '#6b7280',
                          overflow: 'hidden',
                          textOverflow: 'ellipsis',
                          whiteSpace: 'nowrap',
                          flex: 1,
                        }}>
                          {field.name}
                          {sortField === field.key && (
                            <span style={{ marginLeft: 4, fontSize: 10, color: '#3b82f6' }}>
                              {sortOrder === 'asc' ? '↑' : '↓'}
                            </span>
                          )}
                          {hasFilter && (
                            <span style={{ marginLeft: 4, fontSize: 10, color: '#2563eb' }}>●</span>
                          )}
                        </span>
                        <button
                          className="col-header-trigger"
                          onClick={(e) => {
                            e.stopPropagation()
                            if (activeHeaderMenu === field.key) {
                              setActiveHeaderMenu(null)
                              setHeaderFilterText('')
                            } else {
                              setActiveHeaderMenu(field.key)
                              setHeaderFilterText(filterValues[field.key] || '')
                            }
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
                            color: hasFilter ? '#2563eb' : '#9ca3af',
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
                        <div className="col-header-menu" onClick={e => e.stopPropagation()}>
                          {isFilterable && (
                            <div style={{ padding: '8px 10px', borderBottom: '1px solid #f3f4f6' }}>
                              <div style={{ fontSize: 10, color: '#9ca3af', marginBottom: 4 }}>筛选 {field.name}</div>
                              <div style={{ display: 'flex', gap: 4 }}>
                                <input
                                  type="text"
                                  placeholder="输入关键词..."
                                  value={headerFilterText}
                                  onChange={(e) => setHeaderFilterText(e.target.value)}
                                  onKeyDown={(e) => {
                                    if (e.key === 'Enter') handleHeaderFilterApply(field.key)
                                    if (e.key === 'Escape') { setActiveHeaderMenu(null); setHeaderFilterText('') }
                                  }}
                                  autoFocus
                                  style={{
                                    flex: 1,
                                    padding: '4px 8px',
                                    border: '1px solid #d1d5db',
                                    borderRadius: 4,
                                    fontSize: 12,
                                    outline: 'none',
                                    minWidth: 120,
                                  }}
                                />
                                <button
                                  className="btn btn-xs btn-primary"
                                  onClick={() => handleHeaderFilterApply(field.key)}
                                >
                                  确定
                                </button>
                              </div>
                              {filterValues[field.key] && (
                                <button
                                  className="btn btn-xs btn-ghost"
                                  onClick={() => handleHeaderFilterClear(field.key)}
                                  style={{ fontSize: 11, padding: '2px 0', marginTop: 4, color: '#dc2626' }}
                                >
                                  清除此列筛选
                                </button>
                              )}
                            </div>
                          )}
                          <div
                            className="menu-item"
                            onClick={() => handleSort(field.key)}
                          >
                            <span>{sortField === field.key && sortOrder === 'asc' ? '↓ 降序排列' : '↑ 升序排列'}</span>
                          </div>
                          <div className="menu-divider" />
                          <div
                            className="menu-item"
                            onClick={() => openInsertAIDialog(field.key)}
                          >
                            <span style={{ color: '#2563eb' }}>✨ 基于此列插入新列</span>
                          </div>
                          <div
                            className="menu-item"
                            onClick={() => handleToggleFreeze(field.key)}
                          >
                            <span>{frozenFields.has(field.key) ? '🔓 取消冻结' : '🔒 冻结此列'}</span>
                          </div>
                          <div
                            className="menu-item"
                            onClick={() => openColumnStats(field.key)}
                          >
                            <span style={{ color: '#0891b2' }}>📊 统计此列</span>
                          </div>
                          <div
                            className="menu-item"
                            onClick={() => handleToggleFieldVisible(field.key)}
                          >
                            <span>隐藏此列</span>
                          </div>
                        </div>
                      )}
                    </th>
                  )
                })}
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
                        (e.target as HTMLElement).closest('button') ||
                        (e.target as HTMLElement).closest('.cell-action-btn')) return
                    onPatentClick(p.id)
                  }}
                  style={{ cursor: 'pointer' }}
                >
                  <td className="col-checkbox">
                    <input
                      type="checkbox"
                      checked={selectedIds.includes(p.id)}
                      onChange={() => toggleSelect(p.id)}
                      onClick={(e) => e.stopPropagation()}
                    />
                  </td>
                  <td className="col-action" style={{ width: 70, minWidth: 70, maxWidth: 70, position: 'sticky', left: 40, zIndex: 6, background: '#fff', padding: '4px 6px' }}>
                    <div style={{ display: 'flex', gap: 2 }}>
                      <button
                        className="cell-action-btn"
                        onClick={(e) => {
                          e.stopPropagation()
                          handleQuickAI(p.id)
                        }}
                        disabled={aiProcessingRow === p.id}
                        style={{
                          width: 26,
                          height: 26,
                          border: '1px solid #bfdbfe',
                          background: aiProcessingRow === p.id ? '#dbeafe' : '#eff6ff',
                          color: aiProcessingRow === p.id ? '#93c5fd' : '#2563eb',
                          borderRadius: 4,
                          cursor: aiProcessingRow === p.id ? 'wait' : 'pointer',
                          fontSize: 12,
                          display: 'flex',
                          alignItems: 'center',
                          justifyContent: 'center',
                          padding: 0,
                        }}
                        title="AI快速分析"
                      >
                        {aiProcessingRow === p.id ? '⟳' : '✨'}
                      </button>
                    </div>
                  </td>
                  {visibleFields.map(field => {
                    const isFrozen = field.frozen || frozenFields.has(field.key)
                    let leftOffset = 40 + 70
                    if (isFrozen) {
                      for (const f of visibleFields) {
                        if (f.key === field.key) break
                        if (f.frozen || frozenFields.has(f.key)) {
                          leftOffset += columnWidths[f.key] || DEFAULT_COLUMN_WIDTH
                        }
                      }
                    }
                    return (
                    <td
                      key={field.key}
                      className={`${isFrozen ? 'col-frozen' : ''} ${field.editable ? 'cell-editable' : ''}`}
                      style={{
                        width: columnWidths[field.key] || DEFAULT_COLUMN_WIDTH,
                        maxWidth: columnWidths[field.key] || DEFAULT_COLUMN_WIDTH,
                        padding: field.field_type === 'longtext' ? '8px 10px' : '6px 10px',
                        whiteSpace: 'normal',
                        wordBreak: 'break-word',
                        overflowWrap: 'anywhere',
                        verticalAlign: 'top',
                        ...(isFrozen ? { position: 'sticky', left: leftOffset, zIndex: 5, background: '#fff' } : {}),
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
                    )
                  })}
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
        <div style={{ display: 'flex', alignItems: 'center', gap: 2 }}>
          <button
            className="btn btn-xs btn-secondary"
            disabled={page <= 1}
            onClick={() => setPage(page - 1)}
          >
            上一页
          </button>
          {pageNumbers().map((p, idx) =>
            typeof p === 'number' ? (
              <button
                key={idx}
                className="btn btn-xs"
                onClick={() => setPage(p)}
                style={{
                  padding: '2px 7px',
                  minWidth: 24,
                  background: p === page ? '#2563eb' : '#fff',
                  color: p === page ? '#fff' : '#374151',
                  border: `1px solid ${p === page ? '#2563eb' : '#d1d5db'}`,
                  fontWeight: p === page ? 600 : 400,
                }}
              >
                {p}
              </button>
            ) : (
              <span key={idx} style={{ fontSize: 12, color: '#9ca3af', padding: '0 2px' }}>…</span>
            )
          )}
          <button
            className="btn btn-xs btn-secondary"
            disabled={page >= totalPages}
            onClick={() => setPage(page + 1)}
          >
            下一页
          </button>
          <div style={{ display: 'flex', alignItems: 'center', gap: 4, marginLeft: 8 }}>
            <span style={{ fontSize: 12, color: '#6b7280' }}>跳至</span>
            <input
              type="number"
              min={1}
              max={totalPages}
              value={pageInputValue}
              onChange={(e) => setPageInputValue(e.target.value)}
              onKeyDown={(e) => { if (e.key === 'Enter') handlePageJump() }}
              onBlur={handlePageJump}
              style={{
                width: 48,
                height: 24,
                padding: '0 6px',
                border: '1px solid #d1d5db',
                borderRadius: 4,
                fontSize: 12,
                textAlign: 'center',
                outline: 'none',
              }}
            />
            <span style={{ fontSize: 12, color: '#6b7280' }}>页</span>
          </div>
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

      {showInsertAIColumn && (
        <Modal
          title="插入新列"
          width={680}
          onClose={() => {
            setShowInsertAIColumn(false)
            setNewAIColumnName('')
            setNewAIPrompt('')
            setNewColumnOptions('')
            setInsertColType('text')
            setInsertColFrozen(false)
          }}
        >
          <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
            <div style={{
              padding: '10px 12px',
              background: '#eff6ff',
              border: '1px solid #bfdbfe',
              borderRadius: 6,
              fontSize: 12,
              color: '#1e40af',
              lineHeight: 1.6,
            }}>
              💡 像Excel一样插入新列。普通列可手动填值；<strong>AI列</strong>会根据你指定的 Prompt 和已有列内容自动生成。
              在 Prompt 中使用 <code>{'{field_key}'}</code> 引用列，例如 <code>{'{title}'}</code>、<code>{'{abstract}'}</code>、<code>{'{applicant}'}</code>、<code>{'{claims}'}</code>。
            </div>

            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
              <div>
                <label style={{ display: 'block', fontSize: 12, color: '#64748b', marginBottom: 4, fontWeight: 500 }}>
                  新列名称 <span style={{ color: '#dc2626' }}>*</span>
                </label>
                <input
                  className="form-input"
                  value={newAIColumnName}
                  onChange={e => setNewAIColumnName(e.target.value)}
                  placeholder="例如：技术领域分类"
                />
              </div>
              <div>
                <label style={{ display: 'block', fontSize: 12, color: '#64748b', marginBottom: 4, fontWeight: 500 }}>
                  列类型
                </label>
                <select
                  className="form-input"
                  value={insertColType}
                  onChange={e => setInsertColType(e.target.value as any)}
                >
                  <option value="text">文本（手动填写）</option>
                  <option value="longtext">长文本（手动填写）</option>
                  <option value="number">数字</option>
                  <option value="date">日期</option>
                  <option value="select">单选（下拉）</option>
                  <option value="boolean">是/否</option>
                  <option value="ai_field">✨ AI列（自动生成）</option>
                </select>
              </div>
            </div>

            {insertColType === 'select' && (
              <div>
                <label style={{ display: 'block', fontSize: 12, color: '#64748b', marginBottom: 4, fontWeight: 500 }}>
                  候选项 <span style={{ color: '#dc2626' }}>*</span>（每行一个）
                </label>
                <textarea
                  className="form-input"
                  style={{ minHeight: 80, fontSize: 12 }}
                  value={newColumnOptions}
                  onChange={e => setNewColumnOptions(e.target.value)}
                  placeholder={'例如：\n机械\n电子\n软件\n化学'}
                />
              </div>
            )}

            <label style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 13, color: '#475569', cursor: 'pointer' }}>
              <input
                type="checkbox"
                checked={insertColFrozen}
                onChange={e => setInsertColFrozen(e.target.checked)}
              />
              冻结此列（始终显示在左侧）
            </label>

            {insertColType === 'ai_field' && (
              <>
                <div style={{ borderTop: '1px dashed #cbd5e1', paddingTop: 12, marginTop: 4 }}>
                  <label style={{ display: 'block', fontSize: 12, color: '#64748b', marginBottom: 4, fontWeight: 500 }}>
                    AI 提示词 (Prompt) <span style={{ color: '#dc2626' }}>*</span>
                  </label>
                  <div style={{ fontSize: 11, color: '#94a3b8', marginBottom: 6 }}>
                    点击下方列名按钮可快速插入变量到 Prompt 中：
                  </div>
                  <div style={{
                    display: 'flex', flexWrap: 'wrap', gap: 4, marginBottom: 8,
                    maxHeight: 80, overflowY: 'auto', padding: 6,
                    background: '#f8fafc', borderRadius: 4, border: '1px solid #e2e8f0',
                  }}>
                    {fields.filter(f => f.key !== 'id').map(f => (
                      <button
                        key={f.key}
                        onClick={() => setNewAIPrompt(prev => prev + `{${f.key}}`)}
                        style={{
                          padding: '2px 8px', fontSize: 11,
                          background: '#fff', border: '1px solid #cbd5e1',
                          borderRadius: 3, cursor: 'pointer', color: '#334155',
                        }}
                        title={f.name}
                      >
                        {`{${f.key}}`}
                      </button>
                    ))}
                  </div>
                  <textarea
                    className="form-input"
                    style={{ minHeight: 160, fontFamily: 'monospace', fontSize: 12, lineHeight: 1.5 }}
                    value={newAIPrompt}
                    onChange={e => setNewAIPrompt(e.target.value)}
                    placeholder={'例如：\n请阅读以下专利信息，提取该专利的核心技术关键词（5-8个），用英文逗号分隔。\n\n标题：{title}\n摘要：{abstract}\n权利要求：{claims}'}
                  />
                </div>

                <div style={{
                  padding: '8px 10px', background: '#f8fafc', borderRadius: 4,
                  fontSize: 11, color: '#64748b',
                }}>
                  处理范围：
                  {selectedIds.length > 0 ? (
                    <strong style={{ color: '#2563eb' }}>选中的 {selectedIds.length} 条专利</strong>
                  ) : (
                    <span>未选中专利，将仅创建字段。可在创建后通过行内 ✨ 按钮或"AI批量处理"运行。</span>
                  )}
                </div>
              </>
            )}

            <div style={{ display: 'flex', gap: 8, justifyContent: 'flex-end', marginTop: 4 }}>
              <button
                className="btn btn-secondary"
                onClick={() => {
                  setShowInsertAIColumn(false)
                  setNewAIColumnName('')
                  setNewAIPrompt('')
                  setNewColumnOptions('')
                  setInsertColType('text')
                  setInsertColFrozen(false)
                }}
              >
                取消
              </button>
              <button
                className="btn btn-primary"
                onClick={() => handleInsertAIColumn(false)}
                disabled={creatingAIColumn}
              >
                {creatingAIColumn ? '创建中...' : (insertColType === 'ai_field' ? '创建并处理' : '创建列')}
              </button>
            </div>
          </div>
        </Modal>
      )}

      {showColumnStats && (
        <Modal
          title={`列统计：${fields.find(f => f.key === statsFieldKey)?.name || statsFieldKey}`}
          width={680}
          onClose={() => {
            setShowColumnStats(false)
            setShowStatsToTags(false)
          }}
        >
          <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
            {statsLoading ? (
              <div style={{ textAlign: 'center', padding: 40, color: '#64748b' }}>
                <div className="spinner" style={{ width: 32, height: 32, margin: '0 auto 12px', borderWidth: 3 }}></div>
                统计中...
              </div>
            ) : statsData.length === 0 ? (
              <div style={{ textAlign: 'center', padding: 40, color: '#94a3b8' }}>无数据</div>
            ) : (
              <>
                <div style={{
                  display: 'flex', justifyContent: 'space-between', alignItems: 'center',
                  padding: '8px 12px', background: '#f0f9ff', borderRadius: 6, fontSize: 12, color: '#0369a1',
                }}>
                  <span>共 {statsData.length} 个去重值</span>
                  <button
                    className="btn btn-sm btn-primary"
                    style={{ fontSize: 12, padding: '4px 10px' }}
                    onClick={() => setShowStatsToTags(true)}
                  >
                    🏷️ 转为分类标签
                  </button>
                </div>

                {showStatsToTags && (
                  <div style={{
                    background: '#fefce8', border: '1px solid #fde68a', borderRadius: 6, padding: 12,
                  }}>
                    <div style={{ fontSize: 13, fontWeight: 600, marginBottom: 8 }}>把统计结果转为标签体系</div>
                    <div style={{ display: 'flex', gap: 8, marginBottom: 8 }}>
                      <input
                        className="form-input"
                        style={{ flex: 1, fontSize: 12 }}
                        value={tagGroupName}
                        onChange={e => setTagGroupName(e.target.value)}
                        placeholder="标签组名称"
                      />
                      <label style={{ display: 'flex', alignItems: 'center', gap: 4, fontSize: 12, color: '#475569', whiteSpace: 'nowrap' }}>
                        <input type="checkbox" checked={autoApplyTags} onChange={e => setAutoApplyTags(e.target.checked)} />
                        自动给原专利打标
                      </label>
                    </div>
                    <div style={{ display: 'flex', gap: 6 }}>
                      <button className="btn btn-primary" style={{ fontSize: 12, padding: '4px 12px' }} onClick={handleStatsToTags} disabled={convertingTags}>
                        {convertingTags ? '转换中...' : '确认转换'}
                      </button>
                      <button className="btn btn-secondary" style={{ fontSize: 12, padding: '4px 12px' }} onClick={() => setShowStatsToTags(false)}>
                        取消
                      </button>
                    </div>
                  </div>
                )}

                <div style={{ maxHeight: 400, overflowY: 'auto', border: '1px solid #e2e8f0', borderRadius: 6 }}>
                  <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 12 }}>
                    <thead style={{ position: 'sticky', top: 0, background: '#f8fafc', zIndex: 1 }}>
                      <tr>
                        <th style={{ padding: '8px 10px', textAlign: 'left', fontWeight: 600, borderBottom: '1px solid #e2e8f0' }}>值</th>
                        <th style={{ padding: '8px 10px', textAlign: 'right', fontWeight: 600, width: 80, borderBottom: '1px solid #e2e8f0' }}>计数</th>
                        <th style={{ padding: '8px 10px', textAlign: 'right', fontWeight: 600, width: 80, borderBottom: '1px solid #e2e8f0' }}>占比</th>
                        <th style={{ padding: '8px 10px', textAlign: 'left', fontWeight: 600, width: 120, borderBottom: '1px solid #e2e8f0' }}>分布</th>
                      </tr>
                    </thead>
                    <tbody>
                      {statsData.map((item, i) => (
                        <tr key={i} style={{ borderTop: '1px solid #f1f5f9' }}>
                          <td style={{ padding: '6px 10px', wordBreak: 'break-word' }}>{item.value}</td>
                          <td style={{ padding: '6px 10px', textAlign: 'right', fontFamily: 'monospace' }}>{item.count}</td>
                          <td style={{ padding: '6px 10px', textAlign: 'right', color: '#64748b' }}>{item.percentage}%</td>
                          <td style={{ padding: '6px 10px' }}>
                            <div style={{
                              height: 8, background: '#e2e8f0', borderRadius: 4, overflow: 'hidden',
                            }}>
                              <div style={{
                                height: '100%',
                                width: `${item.percentage}%`,
                                background: 'linear-gradient(90deg, #3b82f6, #60a5fa)',
                                borderRadius: 4,
                              }}></div>
                            </div>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </>
            )}
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
