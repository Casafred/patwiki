import { useEffect, useMemo, useState } from 'react'
import { exportApi } from '../../api'
import type { JsonObject, JsonValue, PatentExportTemplate } from '../../types'
import { getErrorMessage } from '../../lib/errors'

interface WorkFileDialogProps {
  databaseId?: number | null
  selectedIds?: number[]
  search?: string
  filters?: JsonObject
  onClose: () => void
}

const FORMAT_LABELS: Record<string, string> = {
  excel: 'Excel',
  word: 'Word',
  csv: 'CSV',
}

const FORMAT_EXTENSIONS: Record<string, string> = {
  excel: 'xlsx',
  word: 'docx',
  csv: 'csv',
}

function toExportFilters(filters?: JsonObject): JsonObject {
  return Object.fromEntries(
    Object.entries(filters || {})
      .filter(([, value]) => {
        if (typeof value === 'string') return !!value.trim()
        if (!value || typeof value !== 'object' || Array.isArray(value)) return false
        const condition = value as JsonObject
        const operator = String(condition.operator || '')
        return operator === 'is_empty' || operator === 'is_not_empty' || !!String(condition.value || '').trim()
      })
      .map(([key, value]) => [key, typeof value === 'string' ? { contains: value } : value]),
  )
}

function download(blob: Blob, template: PatentExportTemplate) {
  const url = window.URL.createObjectURL(blob)
  const anchor = document.createElement('a')
  const extension = FORMAT_EXTENSIONS[template.output_format] || template.output_format
  const safeName = template.name.replace(/[\\/:*?"<>|]/g, '_').trim() || 'patwiki_work_file'
  anchor.href = url
  anchor.download = `${safeName}_v${template.version}.${extension}`
  anchor.style.display = 'none'
  document.body.appendChild(anchor)
  anchor.click()
  window.setTimeout(() => {
    window.URL.revokeObjectURL(url)
    anchor.remove()
  }, 2000)
}

export default function WorkFileDialog({ databaseId, selectedIds = [], search, filters, onClose }: WorkFileDialogProps) {
  const [templates, setTemplates] = useState<PatentExportTemplate[]>([])
  const [selectedId, setSelectedId] = useState<number | null>(null)
  const [loading, setLoading] = useState(true)
  const [downloadingId, setDownloadingId] = useState<number | null>(null)
  const [error, setError] = useState('')
  const [success, setSuccess] = useState('')
  const [scope, setScope] = useState<'selected' | 'filtered' | 'database'>(
    selectedIds.length > 0 ? 'selected' : (search?.trim() || Object.keys(filters || {}).length > 0) ? 'filtered' : 'database',
  )
  const selectedTemplate = useMemo(
    () => templates.find(template => template.id === selectedId) || null,
    [selectedId, templates],
  )

  useEffect(() => {
    let cancelled = false
    // The request synchronizes this dialog with the current database's templates.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setLoading(true)
    setError('')
    exportApi.listTemplates(databaseId)
      .then(items => {
        if (cancelled) return
        setTemplates(items)
        setSelectedId(items[0]?.id ?? null)
      })
      .catch(requestError => {
        if (!cancelled) setError(getErrorMessage(requestError, '工作文件模板加载失败'))
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })
    return () => { cancelled = true }
  }, [databaseId])

  const handleDownload = async () => {
    if (!selectedTemplate || downloadingId !== null) return
    setDownloadingId(selectedTemplate.id)
    setError('')
    setSuccess('')
    try {
      const payload: JsonObject = {
        database_id: databaseId ?? null,
        template_id: selectedTemplate.id,
        patent_ids: scope === 'selected' ? selectedIds : null,
        search: scope === 'database' ? null : search?.trim() || null,
        filters: (scope === 'database' ? {} : toExportFilters(filters)) as unknown as JsonValue,
      }
      const blob = selectedTemplate.output_format === 'word'
        ? await exportApi.word(payload)
        : selectedTemplate.output_format === 'csv'
          ? await exportApi.csv(payload)
          : await exportApi.excel(payload)
      download(blob, selectedTemplate)
      setSuccess(`已开始下载 ${selectedTemplate.name}，文件会出现在浏览器下载列表中。`)
    } catch (requestError: unknown) {
      setError(getErrorMessage(requestError, '工作文件生成失败'))
    } finally {
      setDownloadingId(null)
    }
  }

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal modal-lg work-file-modal" onClick={event => event.stopPropagation()}>
        <div className="modal-header">
          <div>
            <h3>生成工作文件</h3>
            <p className="work-file-subtitle">从当前专利库生成可继续编辑的业务文件，模板版本和字段来源随文件保留。</p>
          </div>
          <button type="button" className="modal-close" onClick={onClose} aria-label="关闭">×</button>
        </div>
        {error && <div className="work-file-error">{error}</div>}
        {loading ? (
          <div className="loading-state work-file-loading">加载模板中...</div>
        ) : templates.length === 0 ? (
          <div className="empty-state work-file-empty">当前数据库暂无工作文件模板</div>
        ) : (
          <>
            <div className="work-file-layout">
              <div className="work-file-template-list" role="listbox" aria-label="选择工作文件模板">
                {templates.map(template => (
                  <button
                    key={template.id}
                    type="button"
                    className={`work-file-template ${selectedId === template.id ? 'active' : ''}`}
                    onClick={() => setSelectedId(template.id)}
                    role="option"
                    aria-selected={selectedId === template.id}
                  >
                    <span className={`work-file-format work-file-format-${template.output_format}`}>{FORMAT_LABELS[template.output_format] || template.output_format}</span>
                    <span className="work-file-template-copy">
                      <strong>{template.name}</strong>
                      <small>{template.is_system ? '系统模板' : '自定义模板'} · v{template.version}</small>
                    </span>
                  </button>
                ))}
              </div>
              <div className="work-file-preview">
                {selectedTemplate && (
                  <>
                    <div className="work-file-preview-heading">
                      <div>
                        <span className="section-eyebrow">输出预览</span>
                        <h4>{selectedTemplate.name}</h4>
                      </div>
                      <span className="work-file-version">v{selectedTemplate.version}</span>
                    </div>
                    <p>{selectedTemplate.description || '使用模板定义的字段、筛选、排序和分组生成文件。'}</p>
                    <dl className="work-file-meta">
                      <div><dt>格式</dt><dd>{FORMAT_LABELS[selectedTemplate.output_format] || selectedTemplate.output_format}</dd></div>
                      <div><dt>字段</dt><dd>{selectedTemplate.field_keys.length} 个固定字段</dd></div>
                      <div><dt>关联视图</dt><dd>{selectedTemplate.view_id ? `视图 #${selectedTemplate.view_id}` : '当前数据库'}</dd></div>
                      <div><dt>当前条件</dt><dd>{search?.trim() || Object.keys(filters || {}).length > 0 ? '叠加当前搜索/筛选' : '使用模板默认条件'}</dd></div>
                    </dl>
                    <label className="work-file-scope">
                      <span>数据范围</span>
                      <select value={scope} onChange={event => setScope(event.target.value as 'selected' | 'filtered' | 'database')}>
                        <option value="selected" disabled={selectedIds.length === 0}>已选 {selectedIds.length} 条专利</option>
                        <option value="filtered">当前搜索和筛选</option>
                        <option value="database">整个专利库</option>
                      </select>
                    </label>
                    <div className="work-file-note">导出结果不会创建第二份专利数据。Excel 会附带“导出说明”页，Word 会附带模板版本和字段来源说明。</div>
                  </>
                )}
              </div>
            </div>
            {success && <div className="work-file-success">{success}</div>}
            <div className="work-file-actions">
              <button type="button" className="btn btn-secondary" onClick={onClose}>取消</button>
              <button type="button" className="btn btn-primary" onClick={() => void handleDownload()} disabled={!selectedTemplate || downloadingId !== null}>
                {downloadingId !== null ? '生成中...' : '生成并下载'}
              </button>
            </div>
          </>
        )}
      </div>
    </div>
  )
}
