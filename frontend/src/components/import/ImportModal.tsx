import { useState, useCallback, useEffect } from 'react'
import { importApi, databaseApi, viewApi } from '../../api'
import { fieldService } from '../../services'
import { useAppStore } from '../../store'
import type { ImportPreview, FieldMapping, PatentView } from '../../types'
import { getErrorMessage } from '../../lib/errors'

interface ImportModalProps {
  onClose: () => void
  onSuccess: () => void
}

const SYSTEM_FIELD_LABELS: Record<string, string> = {
  title: '专利标题',
  application_number: '申请号',
  publication_number: '公开号',
  grant_number: '授权号',
  applicant: '申请人',
  inventor: '发明人',
  assignee: '专利权人',
  agent: '代理机构',
  filing_date: '申请日',
  publication_date: '公开日',
  grant_date: '授权日',
  legal_status: '法律状态',
  patent_type: '专利类型',
  country: '国家',
  ipc_main: 'IPC分类',
  ipc_all: '全部IPC',
  cpc_main: 'CPC分类',
  cpc_all: '全部CPC',
  priority_date: '优先权日',
  priority_number: '优先权号',
  priority_country: '优先权国家',
  abstract: '摘要',
  claims: '权利要求',
  category: '技术分类',
  subcategory: '子分类',
  technical_problem: '技术问题',
  technical_effect: '技术效果',
  technical_solution: '技术方案',
  module: '功能模块',
  has_risk: '是否有风险',
  risk_level: '风险等级',
  risk_description: '风险描述',
  application_status: '应用状态',
  scope_description: '保护范围',
  notes: '备注',
  // P0-10：虚拟字段（同族/引用）
  family_members: '同族专利',
  cited_patents: '引用专利',
  citing_patents: '被引用专利',
}

export default function ImportModal({ onClose, onSuccess }: ImportModalProps) {
  const {
    currentDatabaseId,
    databases,
    products,
    projects,
    setDatabases,
    setCurrentDatabaseId,
  } = useAppStore()

  // P0-12：新增 chooseDatabase 步骤
  const [step, setStep] = useState<'chooseDatabase' | 'upload' | 'mapping' | 'processing' | 'complete'>(
    databases.length > 0 ? 'upload' : 'chooseDatabase'
  )
  const [file, setFile] = useState<File | null>(null)
  const [preview, setPreview] = useState<ImportPreview | null>(null)
  const [selectedSheet, setSelectedSheet] = useState<string | null>(null)
  const [mapping, setMapping] = useState<Record<string, string>>({})
  const [selectedDatabaseId, setSelectedDatabaseId] = useState<number | ''>(
    currentDatabaseId ?? ''
  )
  const [selectedProductId, setSelectedProductId] = useState<number | ''>('')
  const [selectedProjectId, setSelectedProjectId] = useState<number | ''>('')
  // P0-14：导入到指定视图
  const [views, setViews] = useState<PatentView[]>([])
  const [selectedViewId, setSelectedViewId] = useState<number | ''>('')
  const [showCreateView, setShowCreateView] = useState(false)
  const [newViewName, setNewViewName] = useState('')
  const [creatingView, setCreatingView] = useState(false)
  const [dedupeField, setDedupeField] = useState<'application_number' | 'publication_number' | 'both'>('both')
  const [importResult, setImportResult] = useState<{
    total: number; created: number; updated: number; skipped: number; errors: number;
    family_links?: number; citation_links?: number;
    error_details?: { row: number; status?: string; reason?: string; error?: string; patent_id?: number }[]
    row_reports?: { row: number; status: string; reason: string; patent_id?: number }[]
  } | null>(null)
  const [uploading, setUploading] = useState(false)
  const [importing, setImporting] = useState(false)
  const [error, setError] = useState('')

  const selectFile = (nextFile: File) => {
    setFile(nextFile)
    setPreview(null)
    setSelectedSheet(null)
  }

  // P0-12：新建库表单
  const [showCreateDb, setShowCreateDb] = useState(false)
  const [newDbName, setNewDbName] = useState('')
  const [newDbDesc, setNewDbDesc] = useState('')

  // P0-12：库列表为空时自动跳到 chooseDatabase；有库时默认 upload
  useEffect(() => {
    if (databases.length === 0) {
      // Database availability is external state; update the workflow after the check.
      // eslint-disable-next-line react-hooks/set-state-in-effect
      setStep('chooseDatabase')
    } else if (step === 'chooseDatabase' && currentDatabaseId) {
      setStep('upload')
    }
  }, [databases.length, currentDatabaseId, step])

  // P0-14：加载当前库的视图列表（用于导入到指定视图）
  useEffect(() => {
    if (!currentDatabaseId) {
      setViews([])
      return
    }
    viewApi.list(currentDatabaseId).then(setViews).catch(() => setViews([]))
  }, [currentDatabaseId])

  const handleCreateView = useCallback(async () => {
    if (!newViewName.trim() || !currentDatabaseId) return
    setCreatingView(true)
    try {
      // 创建成员型视图：只展示导入到本视图的专利
      const view = await viewApi.create({
        name: newViewName.trim(),
        database_id: currentDatabaseId,
        membership_based: true,
      })
      setViews(prev => [...prev, view])
      setSelectedViewId(view.id)
      setNewViewName('')
      setShowCreateView(false)
    } catch (error: unknown) {
      setError(getErrorMessage(error, '创建视图失败'))
    } finally {
      setCreatingView(false)
    }
  }, [newViewName, currentDatabaseId])

  const handleCreateDatabase = useCallback(async () => {
    if (!newDbName.trim()) return
    try {
      const db = await databaseApi.create({ name: newDbName.trim(), description: newDbDesc.trim() || undefined })
      const refreshed = await databaseApi.list()
      setDatabases(refreshed)
      setSelectedDatabaseId(db.id)
      setCurrentDatabaseId(db.id)
      setNewDbName('')
      setNewDbDesc('')
      setShowCreateDb(false)
      setStep('upload')
    } catch (error: unknown) {
      setError(getErrorMessage(error, '创建库失败'))
    }
  }, [newDbName, newDbDesc, setDatabases, setCurrentDatabaseId])

  const handleChooseDatabase = useCallback(() => {
    if (!selectedDatabaseId) {
      setError('请选择一个专利库')
      return
    }
    setCurrentDatabaseId(Number(selectedDatabaseId))
    setError('')
    setStep('upload')
  }, [selectedDatabaseId, setCurrentDatabaseId])

  const handleUpload = useCallback(async () => {
    if (!file) return
    setUploading(true)
    setError('')
    try {
      const result = await importApi.upload(file, selectedSheet)
      setPreview(result)
      setSelectedSheet(result.selected_sheet || null)
      if ((result.sheets?.length || 0) > 1 && !selectedSheet) {
        setStep('upload')
        return
      }
      // P0-10：使用后端 suggested_mapping（已自动为未知列创建 CustomField）
      setMapping(result.suggested_mapping || {})
      setStep('mapping')
    } catch (error: unknown) {
      setError(getErrorMessage(error, '上传失败，请检查文件格式'))
    } finally {
      setUploading(false)
    }
  }, [file, selectedSheet])

  const handleSheetChange = useCallback(async (sheet: string) => {
    if (!file) return
    setUploading(true)
    setError('')
    try {
      const result = await importApi.upload(file, sheet)
      setPreview(result)
      setSelectedSheet(result.selected_sheet || sheet)
      setMapping(result.suggested_mapping || {})
    } catch (error: unknown) {
      setError(getErrorMessage(error, '读取 Sheet 失败'))
    } finally {
      setUploading(false)
    }
  }, [file])

  const handleImport = useCallback(async () => {
    if (!preview) return
    if (!currentDatabaseId) {
      setError('未选择库，无法导入')
      setStep('chooseDatabase')
      return
    }
    const unmappedColumns = preview.detected_columns.filter(column => !mapping[column])
    if (unmappedColumns.length > 0) {
      setError(`以下 Excel 列尚未映射，已阻止导入以保证数据完整：${unmappedColumns.join('、')}`)
      return
    }
    setImporting(true)
    setStep('processing')
    try {
      const fieldMappings: FieldMapping[] = preview.detected_columns.map(source => ({
        source_column: source,
        target_field: mapping[source] || '',
      }))

      const result = await importApi.confirmImport(
        preview.import_id,
        fieldMappings,
        dedupeField,
        true,
        selectedProductId || undefined,
        selectedProjectId || undefined,
        currentDatabaseId,
        selectedViewId || undefined,
        selectedSheet || undefined,
      )
      // 防御：后端返回空体或异常时 result 可能为 undefined，
      // 若直接进入 complete 步骤会导致渲染条件不满足而白屏。
      if (!result || typeof result !== 'object') {
        setError('导入返回异常，请检查数据后重试')
        setStep('mapping')
        return
      }
      setImportResult(result)
      setStep('complete')
      fieldService.invalidate()
      // Imported mappings can create custom fields. Clear stale local column hiding
      // so newly available claim and metadata columns are visible immediately.
      try {
        const importedKeys = fieldMappings.map(item => item.target_field).filter(Boolean)
        const hiddenRaw = localStorage.getItem('patwiki_hidden_fields')
        if (hiddenRaw) {
          const hidden = JSON.parse(hiddenRaw) as unknown
          if (Array.isArray(hidden)) {
            localStorage.setItem('patwiki_hidden_fields', JSON.stringify(hidden.filter(key => !importedKeys.includes(String(key)))))
          }
        }
        const previousForced = JSON.parse(localStorage.getItem('patwiki_force_visible_fields') || '[]') as unknown
        const previousKeys = Array.isArray(previousForced) ? previousForced.map(String) : []
        localStorage.setItem('patwiki_force_visible_fields', JSON.stringify([...new Set([...previousKeys, ...importedKeys])]))
      } catch {
        // Column preferences are optional and must not block a successful import.
      }
    } catch (error: unknown) {
      setError(getErrorMessage(error, '导入失败'))
      setStep('mapping')
    } finally {
      setImporting(false)
    }
  }, [preview, mapping, dedupeField, selectedProductId, selectedProjectId, currentDatabaseId, selectedViewId, selectedSheet])

  const handleBackdropClick = (e: React.MouseEvent) => {
    if (e.target === e.currentTarget) onClose()
  }

  // P0-10：统计未匹配列（将被自动创建为 CustomField）数量
  const newFieldCount = preview
    ? Object.entries(preview.suggested_mapping || {}).filter(
        ([, key]) => key && key.startsWith('cf_')
      ).length
    : 0

  const stepTitle = {
    chooseDatabase: '选择专利库',
    upload: '上传 Excel 文件',
    mapping: '字段映射',
    processing: '正在导入...',
    complete: '导入完成',
  }[step]

  return (
    <div
      style={{
        position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.5)',
        display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 100,
      }}
      onClick={handleBackdropClick}
    >
      <div style={{ background: 'white', borderRadius: 12, width: '90%', maxWidth: 800, maxHeight: '90vh', overflow: 'auto', boxShadow: '0 25px 50px -12px rgba(0,0,0,0.25)' }}>
        <div style={{ padding: '20px 24px', borderBottom: '1px solid #e2e8f0', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <h3 style={{ fontSize: 18, fontWeight: 600, margin: 0 }}>{stepTitle}</h3>
          <button onClick={onClose} style={{ background: 'none', border: 'none', fontSize: 20, cursor: 'pointer', color: '#94a3b8' }}>×</button>
        </div>

        <div style={{ padding: 24 }}>
          {error && (
            <div style={{ background: '#fef2f2', border: '1px solid #fecaca', color: '#dc2626', padding: 12, borderRadius: 6, marginBottom: 16, fontSize: 13 }}>
              {error}
            </div>
          )}

          {/* P0-12：第一步 - 选择/创建库 */}
          {step === 'chooseDatabase' && (
            <div>
              <div style={{ background: '#f0f9ff', border: '1px solid #bae6fd', padding: 12, borderRadius: 6, marginBottom: 16, fontSize: 13 }}>
                导入前请先选择或创建一个专利库。库是顶层品类容器，例如"电钻专利数据库"、"传感器专利数据库"。
              </div>

              <label style={{ fontSize: 12, color: '#475569', display: 'block', marginBottom: 4 }}>选择已有库</label>
              <select
                className="form-input"
                value={selectedDatabaseId}
                onChange={(e) => setSelectedDatabaseId(e.target.value ? Number(e.target.value) : '')}
                style={{ width: '100%', marginBottom: 16 }}
              >
                <option value="">-- 请选择 --</option>
                {databases.map(d => (
                  <option key={d.id} value={d.id}>
                    {d.name}{d.patent_count !== undefined ? `（${d.patent_count} 条）` : ''}
                  </option>
                ))}
              </select>

              <div style={{ borderTop: '1px dashed #cbd5e1', paddingTop: 16, marginTop: 8 }}>
                {!showCreateDb ? (
                  <button className="btn btn-secondary" onClick={() => setShowCreateDb(true)}>
                    + 创建新库
                  </button>
                ) : (
                  <div>
                    <label style={{ fontSize: 12, color: '#475569', display: 'block', marginBottom: 4 }}>库名称</label>
                    <input
                      className="form-input"
                      style={{ width: '100%', marginBottom: 8 }}
                      placeholder="如：电钻专利数据库"
                      value={newDbName}
                      onChange={(e) => setNewDbName(e.target.value)}
                      autoFocus
                    />
                    <label style={{ fontSize: 12, color: '#475569', display: 'block', marginBottom: 4 }}>描述（可选）</label>
                    <input
                      className="form-input"
                      style={{ width: '100%', marginBottom: 12 }}
                      placeholder="简要描述该库的用途"
                      value={newDbDesc}
                      onChange={(e) => setNewDbDesc(e.target.value)}
                    />
                    <div style={{ display: 'flex', gap: 8 }}>
                      <button className="btn btn-primary" onClick={handleCreateDatabase}>创建并使用</button>
                      <button className="btn btn-secondary" onClick={() => { setShowCreateDb(false); setNewDbName(''); setNewDbDesc('') }}>取消</button>
                    </div>
                  </div>
                )}
              </div>

              <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 8, marginTop: 24 }}>
                <button className="btn btn-secondary" onClick={onClose}>取消</button>
                <button
                  className="btn btn-primary"
                  disabled={!selectedDatabaseId}
                  onClick={handleChooseDatabase}
                >
                  下一步：上传文件
                </button>
              </div>
            </div>
          )}

          {step === 'upload' && (
            <div>
              {/* P0-12：当前库显示 */}
              <div style={{ background: '#f0fdf4', border: '1px solid #bbf7d0', padding: '8px 12px', borderRadius: 6, marginBottom: 16, fontSize: 13, color: '#15803d' }}>
                当前库：<strong>{databases.find(d => d.id === currentDatabaseId)?.name || '未选择'}</strong>
                <button
                  onClick={() => setStep('chooseDatabase')}
                  style={{ marginLeft: 12, background: 'transparent', border: 'none', color: '#15803d', cursor: 'pointer', textDecoration: 'underline', fontSize: 12 }}
                >
                  切换
                </button>
              </div>

              <div
                style={{
                  border: '2px dashed #cbd5e1', borderRadius: 8, padding: 40,
                  textAlign: 'center', cursor: 'pointer',
                  background: file ? '#f0fdf4' : '#f8fafc',
                }}
                onDragOver={(e) => { e.preventDefault(); e.currentTarget.style.borderColor = '#2563eb' }}
                onDragLeave={(e) => { e.currentTarget.style.borderColor = '#cbd5e1' }}
                onDrop={(e) => {
                  e.preventDefault()
                  e.currentTarget.style.borderColor = '#cbd5e1'
                  const f = e.dataTransfer.files[0]
                  if (f && (f.name.endsWith('.xlsx') || f.name.endsWith('.xls') || f.name.endsWith('.csv'))) {
                    selectFile(f)
                  }
                }}
                onClick={() => {
                  const input = document.createElement('input')
                  input.type = 'file'
                  input.accept = '.xlsx,.xls,.csv'
                  input.onchange = (event: Event) => {
                    const target = event.target
                    if (!(target instanceof HTMLInputElement)) return
                    const f = target.files?.[0]
                    if (f) selectFile(f)
                  }
                  input.click()
                }}
              >
                {file ? (
                  <div>
                    <div style={{ fontSize: 14, fontWeight: 500 }}>{file.name}</div>
                    <div style={{ fontSize: 12, color: '#64748b', marginTop: 4 }}>
                      {(file.size / 1024 / 1024).toFixed(2)} MB - 点击重新选择
                    </div>
                  </div>
                ) : (
                  <div>
                    <div style={{ fontSize: 14, color: '#334155' }}>点击或拖拽Excel文件到此处上传</div>
                    <div style={{ fontSize: 12, color: '#94a3b8', marginTop: 8 }}>支持 .xlsx, .xls, .csv 格式</div>
                  </div>
                )}
              </div>

              {preview && (preview.mapping_issues?.length || 0) > 0 && (
                <div style={{ background: '#fef2f2', border: '1px solid #fecaca', color: '#991b1b', padding: 12, borderRadius: 6, marginBottom: 16, fontSize: 12 }}>
                  {preview.mapping_issues?.map(issue => <div key={issue.column}>{issue.column}: {issue.reason}</div>)}
                </div>
              )}

              {preview?.sheets && preview.sheets.length > 1 && (
                <div style={{ marginTop: 16, padding: 12, background: '#f8fafc', border: '1px solid #e2e8f0', borderRadius: 6 }}>
                  <label style={{ fontSize: 12, color: '#475569', display: 'block', marginBottom: 4 }}>选择导入 Sheet</label>
                  <select
                    className="form-input"
                    value={selectedSheet || preview.selected_sheet || preview.sheets[0]}
                    disabled={uploading}
                    onChange={e => void handleSheetChange(e.target.value)}
                  >
                    {preview.sheets.map(sheet => <option key={sheet} value={sheet}>{sheet}</option>)}
                  </select>
                </div>
              )}

              <div style={{ marginTop: 20 }}>
                <p style={{ fontSize: 13, color: '#64748b', marginBottom: 8 }}>导入选项</p>
                <div style={{ display: 'flex', gap: 16, flexWrap: 'wrap' }}>
                  <div>
                    <label style={{ fontSize: 12, color: '#475569', display: 'block', marginBottom: 4 }}>去重依据</label>
                    <select className="form-input" value={dedupeField} onChange={(e) => {
                      const value = e.target.value
                      if (value === 'both' || value === 'application_number' || value === 'publication_number') {
                        setDedupeField(value)
                      }
                    }}>
                      <option value="both">申请号或公开号</option>
                      <option value="application_number">仅申请号</option>
                      <option value="publication_number">仅公开号</option>
                    </select>
                  </div>
                </div>
              </div>

              <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 8, marginTop: 24 }}>
                <button className="btn btn-secondary" onClick={onClose}>取消</button>
                <button className="btn btn-primary" disabled={!file || uploading} onClick={handleUpload}>
                  {uploading ? '解析中...' : '下一步：预览字段'}
                </button>
              </div>
            </div>
          )}

          {step === 'mapping' && preview && (
            <div>
              <div style={{ background: '#f0f9ff', border: '1px solid #bae6fd', padding: 12, borderRadius: 6, marginBottom: 16, fontSize: 13 }}>
                已识别 <strong>{preview.detected_columns.length}</strong> 列，共 <strong>{preview.total_rows}</strong> 行数据。
                请确认Excel列与系统字段的对应关系。
                {newFieldCount > 0 && (
                  <span style={{ color: '#ea580c', marginLeft: 8, fontWeight: 600 }}>
                    将自动创建 {newFieldCount} 个新字段
                  </span>
                )}
              </div>

              <div style={{ maxHeight: 350, overflowY: 'auto', border: '1px solid #e2e8f0', borderRadius: 6, marginBottom: 16 }}>
                <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13 }}>
                  <thead>
                    <tr style={{ background: '#f8fafc' }}>
                      <th style={{ padding: '8px 12px', textAlign: 'left', fontWeight: 600, width: '30%' }}>Excel列名</th>
                      <th style={{ padding: '8px 12px', textAlign: 'left', fontWeight: 600, width: '40%' }}>映射到系统字段</th>
                      <th style={{ padding: '8px 12px', textAlign: 'left', fontWeight: 600 }}>预览（前3条）</th>
                    </tr>
                  </thead>
                  <tbody>
                    {preview.detected_columns.map((col) => {
                      const mappedKey = mapping[col] || ''
                      const isNewField = mappedKey.startsWith('cf_')
                      const isVirtual = ['family_members', 'cited_patents', 'citing_patents'].includes(mappedKey)
                      return (
                        <tr key={col} style={{ borderTop: '1px solid #f1f5f9' }}>
                          <td style={{ padding: '8px 12px', fontWeight: 500 }}>{col}</td>
                          <td style={{ padding: '6px 12px' }}>
                            <select
                              className="form-input"
                              style={{ fontSize: 12, padding: '4px 8px' }}
                              value={mappedKey}
                              onChange={(e) => setMapping(prev => ({ ...prev, [col]: e.target.value }))}
                            >
                              <option value="">-- 必须映射 --</option>
                              <optgroup label="系统字段">
                                {Object.entries(SYSTEM_FIELD_LABELS).map(([f, l]) => (
                                  <option key={f} value={f}>{l} ({f})</option>
                                ))}
                              </optgroup>
                              {(preview.available_fields || []).filter(field => !field.is_system && field.key !== mappedKey).length > 0 && (
                                <optgroup label="已有自定义字段">
                                  {(preview.available_fields || []).filter(field => !field.is_system && field.key !== mappedKey).map(field => (
                                    <option key={field.key} value={field.key}>{field.name} ({field.key})</option>
                                  ))}
                                </optgroup>
                              )}
                              {isNewField && (
                                <optgroup label="新建自定义字段">
                                  <option value={mappedKey}>新建：{col}</option>
                                </optgroup>
                              )}
                            </select>
                            {isNewField && (
                              <span style={{ display: 'inline-block', marginLeft: 6, padding: '1px 6px', fontSize: 10, background: '#fed7aa', color: '#9a3412', borderRadius: 3 }}>
                                新建字段
                              </span>
                            )}
                            {isVirtual && (
                              <span style={{ display: 'inline-block', marginLeft: 6, padding: '1px 6px', fontSize: 10, background: '#e0e7ff', color: '#3730a3', borderRadius: 3 }}>
                                关系入库
                              </span>
                            )}
                          </td>
                          <td style={{ padding: '8px 12px', fontSize: 11, color: '#64748b', maxWidth: 200, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                            {preview.preview_rows.slice(0, 3).map((row, ri) => (
                              <div key={ri}>{String(row[col] ?? '')}</div>
                            ))}
                          </td>
                        </tr>
                      )
                    })}
                  </tbody>
                </table>
              </div>

              <div style={{ display: 'flex', gap: 16, marginBottom: 16 }}>
                <div style={{ flex: 1 }}>
                  <label style={{ fontSize: 12, color: '#475569', display: 'block', marginBottom: 4 }}>关联产品（可选）</label>
                  <select
                    className="form-input"
                    value={selectedProductId}
                    onChange={(e) => {
                      const nextProductId = e.target.value ? Number(e.target.value) : ''
                      setSelectedProductId(nextProductId)
                      setSelectedProjectId('')
                    }}
                  >
                    <option value="">不关联产品</option>
                    {products.map(product => (
                      <option key={product.id} value={product.id}>{product.name}</option>
                    ))}
                  </select>
                </div>
                <div style={{ flex: 1 }}>
                  <label style={{ fontSize: 12, color: '#475569', display: 'block', marginBottom: 4 }}>关联项目（可选）</label>
                  <select className="form-input" value={selectedProjectId} onChange={(e) => setSelectedProjectId(e.target.value ? Number(e.target.value) : '')}>
                    <option value="">不关联项目</option>
                    {projects
                      .filter(project => !selectedProductId || project.product_id === selectedProductId)
                      .map(project => (
                        <option key={project.id} value={project.id}>{project.name}</option>
                      ))}
                  </select>
                </div>
              </div>

              {/* P0-14：导入到指定视图 */}
              <div style={{ marginBottom: 16 }}>
                <label style={{ fontSize: 12, color: '#475569', display: 'block', marginBottom: 4 }}>
                  导入到视图（可选）
                  <span style={{ fontSize: 11, color: '#94a3b8', marginLeft: 6 }}>
                    不选则导入到库的主视图
                  </span>
                </label>
                {!showCreateView ? (
                  <div style={{ display: 'flex', gap: 8 }}>
                    <select
                      className="form-input"
                      style={{ flex: 1 }}
                      value={selectedViewId}
                      onChange={(e) => setSelectedViewId(e.target.value ? Number(e.target.value) : '')}
                    >
                      <option value="">不指定（导入到主视图）</option>
                      {views.filter(v => !v.is_department_master).map(v => (
                        <option key={v.id} value={v.id}>{v.name}</option>
                      ))}
                    </select>
                    <button
                      type="button"
                      className="btn btn-secondary"
                      style={{ whiteSpace: 'nowrap', fontSize: 12 }}
                      onClick={() => setShowCreateView(true)}
                    >
                      + 新建视图
                    </button>
                  </div>
                ) : (
                  <div style={{ border: '1px solid #e2e8f0', borderRadius: 6, padding: 12, background: '#f8fafc' }}>
                    <div style={{ fontSize: 12, color: '#475569', marginBottom: 6 }}>
                      新建成员型视图：只展示本次导入的专利
                    </div>
                    <div style={{ display: 'flex', gap: 8 }}>
                      <input
                        className="form-input"
                        style={{ flex: 1 }}
                        placeholder="如：2024年Q1竞品分析"
                        value={newViewName}
                        onChange={(e) => setNewViewName(e.target.value)}
                        autoFocus
                      />
                      <button
                        type="button"
                        className="btn btn-primary"
                        style={{ fontSize: 12, whiteSpace: 'nowrap' }}
                        disabled={!newViewName.trim() || creatingView}
                        onClick={handleCreateView}
                      >
                        {creatingView ? '创建中...' : '创建并选中'}
                      </button>
                      <button
                        type="button"
                        className="btn btn-secondary"
                        style={{ fontSize: 12 }}
                        onClick={() => { setShowCreateView(false); setNewViewName('') }}
                      >
                        取消
                      </button>
                    </div>
                  </div>
                )}
              </div>

              <div style={{ display: 'flex', justifyContent: 'space-between', gap: 8 }}>
                <button className="btn btn-secondary" onClick={() => setStep('upload')}>返回</button>
                <div style={{ display: 'flex', gap: 8 }}>
                  <button className="btn btn-secondary" onClick={onClose}>取消</button>
                  <button className="btn btn-primary" disabled={importing} onClick={handleImport}>
                    {importing ? '导入中...' : `开始导入 ${preview.total_rows} 条数据`}
                  </button>
                </div>
              </div>
            </div>
          )}

          {step === 'processing' && (
            <div style={{ textAlign: 'center', padding: 40 }}>
              <div className="spinner" style={{ width: 40, height: 40, margin: '0 auto 16px' }}></div>
              <p style={{ fontSize: 14, color: '#475569' }}>正在处理数据，请勿关闭窗口...</p>
              <p style={{ fontSize: 12, color: '#94a3b8', marginTop: 8 }}>数据量大时可能需要一些时间</p>
            </div>
          )}

              {step === 'complete' && importResult && (
            <div style={{ textAlign: 'center', padding: 20 }}>
              <h4 style={{ fontSize: 16, fontWeight: 600, marginBottom: 16 }}>导入完成！</h4>
              <div style={{ display: 'flex', justifyContent: 'center', gap: 24, marginBottom: 24, flexWrap: 'wrap' }}>
                <div style={{ textAlign: 'center' }}>
                  <div style={{ fontSize: 24, fontWeight: 700, color: '#16a34a' }}>{importResult.created}</div>
                  <div style={{ fontSize: 12, color: '#64748b' }}>新增</div>
                </div>
                <div style={{ textAlign: 'center' }}>
                  <div style={{ fontSize: 24, fontWeight: 700, color: '#2563eb' }}>{importResult.updated}</div>
                  <div style={{ fontSize: 12, color: '#64748b' }}>更新（字段级合并）</div>
                </div>
                <div style={{ textAlign: 'center' }}>
                  <div style={{ fontSize: 24, fontWeight: 700, color: '#64748b' }}>{importResult.skipped}</div>
                  <div style={{ fontSize: 12, color: '#64748b' }}>跳过</div>
                </div>
                {importResult.family_links !== undefined && importResult.family_links > 0 && (
                  <div style={{ textAlign: 'center' }}>
                    <div style={{ fontSize: 24, fontWeight: 700, color: '#7c3aed' }}>{importResult.family_links}</div>
                    <div style={{ fontSize: 12, color: '#64748b' }}>同族关联</div>
                  </div>
                )}
                {importResult.citation_links !== undefined && importResult.citation_links > 0 && (
                  <div style={{ textAlign: 'center' }}>
                    <div style={{ fontSize: 24, fontWeight: 700, color: '#0891b2' }}>{importResult.citation_links}</div>
                    <div style={{ fontSize: 12, color: '#64748b' }}>引用关联</div>
                  </div>
                )}
                {importResult.errors > 0 && (
                  <div style={{ textAlign: 'center' }}>
                    <div style={{ fontSize: 24, fontWeight: 700, color: '#dc2626' }}>{importResult.errors}</div>
                    <div style={{ fontSize: 12, color: '#64748b' }}>错误</div>
                  </div>
                )}
              </div>
              {(importResult.row_reports || importResult.error_details || []).filter(report => report.status !== 'created').length > 0 && (
                <div style={{ textAlign: 'left', maxHeight: 220, overflowY: 'auto', marginBottom: 20, border: '1px solid #e2e8f0', borderRadius: 6 }}>
                  <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 12 }}>
                    <thead><tr style={{ background: '#f8fafc' }}><th style={{ padding: 8, textAlign: 'left' }}>行号</th><th style={{ padding: 8, textAlign: 'left' }}>结果</th><th style={{ padding: 8, textAlign: 'left' }}>原因</th></tr></thead>
                    <tbody>
                      {(importResult.row_reports || importResult.error_details || []).filter(report => report.status !== 'created').map((report, index) => (
                        <tr key={`${report.row}-${index}`} style={{ borderTop: '1px solid #f1f5f9' }}><td style={{ padding: 8 }}>{report.row}</td><td style={{ padding: 8 }}>{report.status || '错误'}</td><td style={{ padding: 8 }}>{report.reason || ('error' in report ? report.error : undefined) || '未知原因'}</td></tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
              <button className="btn btn-primary" onClick={onSuccess}>完成</button>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
