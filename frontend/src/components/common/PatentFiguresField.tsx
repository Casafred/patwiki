import { useRef, useState } from 'react'
import { attachmentApi } from '../../api'
import { BACKEND_URL } from '../../lib/api'
import type { AttachmentMeta, JsonValue } from '../../types'
import { getErrorMessage } from '../../lib/errors'
import ImageLightbox from './ImageLightbox'

interface PatentFiguresFieldProps {
  patentId: number
  databaseId: number | null
  value: JsonValue
  onChange?: (attachments: AttachmentMeta[]) => void
}

function normalize(value: JsonValue): AttachmentMeta[] {
  if (!Array.isArray(value)) return []
  return value.filter(item => typeof item === 'object' && item !== null).map(item => item as unknown as AttachmentMeta)
}

function resolveUrl(relativeUrl: string): string {
  const isTauri = '__TAURI_INTERNALS__' in window || '__TAURI__' in window
  return isTauri ? `${BACKEND_URL}${relativeUrl}` : relativeUrl
}

function sourceLabel(sourceType?: string): string {
  switch (sourceType) {
    case 'excel_embedded':
      return 'Excel 导入'
    case 'mcp':
      return 'MCP 更新'
    default:
      return '手动上传'
  }
}

export default function PatentFiguresField({ patentId, databaseId, value, onChange }: PatentFiguresFieldProps) {
  const [attachments, setAttachments] = useState<AttachmentMeta[]>(normalize(value))
  const [syncedValue, setSyncedValue] = useState(value)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [lightboxIndex, setLightboxIndex] = useState<number | null>(null)
  const inputRef = useRef<HTMLInputElement>(null)

  if (value !== syncedValue) {
    setSyncedValue(value)
    setAttachments(normalize(value))
  }

  const images = attachments.filter(item => item.is_image || item.mime_type?.startsWith('image/'))

  const upload = async (files: FileList) => {
    if (!databaseId) {
      setError('该专利未归属数据库，无法上传附图')
      return
    }
    setBusy(true)
    setError(null)
    try {
      let next = [...attachments]
      for (const file of Array.from(files)) {
        const body = new FormData()
        body.append('database_id', String(databaseId))
        body.append('patent_id', String(patentId))
        body.append('field_key', 'patent_figures')
        body.append('file', file)
        const created = await attachmentApi.upload(body)
        next = [...next, created]
      }
      setAttachments(next)
      onChange?.(next)
    } catch (requestError: unknown) {
      setError(getErrorMessage(requestError, '附图上传失败'))
    } finally {
      setBusy(false)
    }
  }

  const remove = async (attachment: AttachmentMeta) => {
    if (!window.confirm(`确定删除“${attachment.filename}”吗？`)) return
    setBusy(true)
    setError(null)
    try {
      await attachmentApi.remove(attachment.attachment_id)
      const next = attachments.filter(item => item.attachment_id !== attachment.attachment_id)
      setAttachments(next)
      onChange?.(next)
    } catch (requestError: unknown) {
      setError(getErrorMessage(requestError, '附图删除失败'))
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="patent-figures-field" onClick={event => event.stopPropagation()}>
      <div className="patent-figures-toolbar">
        <span className="patent-figures-count">共 {images.length} 张附图</span>
        <label className={`btn btn-secondary patent-figures-upload ${busy ? 'is-busy' : ''}`}>
          <span>{busy ? '上传中...' : '+ 上传附图'}</span>
          <input
            ref={inputRef}
            type="file"
            accept="image/*"
            multiple
            disabled={busy || !databaseId}
            onChange={event => { const files = event.target.files; if (files && files.length) void upload(files); event.target.value = '' }}
          />
        </label>
      </div>
      {images.length === 0 ? (
        <div className="patent-figures-empty">暂无附图。Excel 导入、MCP 更新与手动上传的图片都会汇总在这里。</div>
      ) : (
        <div className="patent-figures-grid">
          {images.map((image, index) => (
            <figure key={image.attachment_id} className="patent-figure-card">
              <button
                type="button"
                className="patent-figure-thumb"
                title={`预览 ${image.filename}`}
                onClick={() => setLightboxIndex(index)}
              >
                <img src={resolveUrl(image.preview_url)} alt={image.filename} loading="lazy" />
              </button>
              <figcaption className="patent-figure-caption">
                <span className="patent-figure-name" title={image.filename}>{image.filename}</span>
                <span className={`patent-figure-source patent-figure-source-${image.source_type || 'manual_upload'}`}>{sourceLabel(image.source_type)}</span>
                <button type="button" className="patent-figure-remove" disabled={busy} onClick={() => void remove(image)} title="删除附图">×</button>
              </figcaption>
            </figure>
          ))}
        </div>
      )}
      {error && <div className="patent-figures-error">{error}</div>}
      {lightboxIndex !== null && (
        <ImageLightbox
          images={images.map(image => ({
            src: resolveUrl(image.preview_url),
            title: image.filename,
            downloadUrl: resolveUrl(image.download_url),
          }))}
          index={lightboxIndex}
          onClose={() => setLightboxIndex(null)}
          onIndexChange={setLightboxIndex}
        />
      )}
    </div>
  )
}
