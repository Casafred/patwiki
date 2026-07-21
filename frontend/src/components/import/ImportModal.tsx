import { useState, useCallback, useEffect } from 'react'
import { importApi, databaseApi } from '../../api'
import { useAppStore } from '../../store'
import type { ImportPreview, FieldMapping } from '../../types'

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
  const { currentDatabaseId, databases, setDatabases, setCurrentDatabaseId } = useAppStore()

  // P0-12：新增 chooseDatabase 步骤
  const [step, setStep] = useState<'chooseDatabase' | 'upload' | 'mapping' | 'processing' | 'complete'>(
    databases.length > 0 ? 'upload' : 'chooseDatabase'
  )
  const [file, setFile] = useState<File | null>(null)
  const [preview, setPreview] = useState<ImportPreview | null>(null)
  const [mapping, setMapping] = useState<Record<string, string>>({})
  const [selectedDatabaseId, setSelectedDatabaseId] = useState<number | ''>(
    currentDatabaseId ?? ''
  )
  const [selectedProductId, setSelectedProductId] = useState<number | ''>('')
  const [selectedProjectId, setSelectedProjectId] = useState<number | ''>('')
  const [dedupeField, setDedupeField] = useState<'application_number' | 'publication_number' | 'both'>('both')
  const [importResult, setImportResult] = useState<{
    total: number; created: number; updated: number; skipped: number; errors: number;
    family_links?: number; citation_links?: number;
  } | null>(null)
  const [uploading, setUploading] = useState(false)
  const [importing, setImporting] = useState(false)
  const [error, setError] = useState('')

  // P0-12：新建库表单
  const [showCreateDb, setShowCreateDb] = useState(false)
  const [newDbName, setNewDbName] = useState('')
  const [newDbDesc, setNewDbDesc] = useState('')

  // P0-12：库列表为空时自动跳到 chooseDatabase；有库时默认 upload
  useEffect(() => {
    if (databases.length === 0) {
      setStep('chooseDatabase')
    } else if (step === 'chooseDatabase' && currentDatabaseId) {
      setStep('upload')
    }
  }, [databases.length, currentDatabaseId, step])

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
    } catch (e: any) {
      setError(e?.response?.data?.detail || '创建库失败')
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
      const result = await importApi.upload(file)
      setPreview(result)
      // P0-10：使用后端 suggested_mapping（已自动为未知列创建 CustomField）
      setMapping(result.suggested_mapping || {})
      setStep('mapping')
    } catch (e: any) {
      setError(e?.response?.data?.detail || '上传失败，请检查文件格式')
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
    setImporting(true)
    setStep('processing')
    try {
      const fieldMappings: FieldMapping[] = Object.entries(mapping)
        .filter(([, target]) => target)
        .map(([source, target]) => ({ source_column: source, target_field: target }))

      const result = await importApi.confirmImport(
        preview.import_id,
        fieldMappings,
        dedupeField,
        true,
        selectedProductId || undefined,
        selectedProjectId || undefined,
        currentDatabaseId,
      )
      setImportResult(result)
      setStep('complete')
    } catch (e: any) {
      setError(e?.response?.data?.detail || '导入失败')
      setStep('mapping')
    } finally {
      setImporting(false)
    }
  }, [preview, mapping, dedupeField, selectedProductId, selectedProjectId, currentDatabaseId])

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
                    setFile(f)
                  }
                }}
                onClick={() => {
                  const input = document.createElement('input')
                  input.type = 'file'
                  input.accept = '.xlsx,.xls,.csv'
                  input.onchange = (e: any) => {
                    const f = e.target.files[0]
                    if (f) setFile(f)
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

              <div style={{ marginTop: 20 }}>
                <p style={{ fontSize: 13, color: '#64748b', marginBottom: 8 }}>导入选项</p>
                <div style={{ display: 'flex', gap: 16, flexWrap: 'wrap' }}>
                  <div>
                    <label style={{ fontSize: 12, color: '#475569', display: 'block', marginBottom: 4 }}>去重依据</label>
                    <select className="form-input" value={dedupeField} onChange={(e) => setDedupeField(e.target.value as any)}>
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
                              <option value="">-- 不导入 --</option>
                              <optgroup label="系统字段">
                                {Object.entries(SYSTEM_FIELD_LABELS).map(([f, l]) => (
                                  <option key={f} value={f}>{l} ({f})</option>
                                ))}
                              </optgroup>
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
                  <select className="form-input" value={selectedProductId} onChange={(e) => setSelectedProductId(e.target.value ? Number(e.target.value) : '')}>
                    <option value="">不关联产品</option>
                  </select>
                </div>
                <div style={{ flex: 1 }}>
                  <label style={{ fontSize: 12, color: '#475569', display: 'block', marginBottom: 4 }}>关联项目（可选）</label>
                  <select className="form-input" value={selectedProjectId} onChange={(e) => setSelectedProjectId(e.target.value ? Number(e.target.value) : '')}>
                    <option value="">不关联项目</option>
                  </select>
                </div>
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
              <button className="btn btn-primary" onClick={onSuccess}>完成</button>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
