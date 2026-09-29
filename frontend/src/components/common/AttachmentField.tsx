import { Fragment, useState } from 'react'
import { attachmentApi } from '../../api'
import { BACKEND_URL } from '../../lib/api'
import type { AttachmentMeta, JsonValue } from '../../types'
import { getErrorMessage } from '../../lib/errors'
import ImageLightbox from './ImageLightbox'

interface AttachmentFieldProps {
  patentId: number
  databaseId: number | null
  fieldKey: string
  value: JsonValue
  displayMode?: 'all' | 'thumbnail'
  onChange?: (attachments: AttachmentMeta[]) => void
}

function normalize(value: JsonValue): AttachmentMeta[] {
  if (!Array.isArray(value)) return []
  return value.filter(item => typeof item === 'object' && item !== null).map(item => item as unknown as AttachmentMeta)
}

function formatSize(size: number): string {
  if (size < 1024) return `${size} B`
  if (size < 1024 * 1024) return `${(size / 1024).toFixed(1)} KB`
  return `${(size / (1024 * 1024)).toFixed(1)} MB`
}

/** Build a fully-qualified URL from the relative path returned by the backend.
 *  In dev mode the Vite proxy handles /api; in Tauri we need the absolute
 *  http://127.0.0.1:8765 origin so the webview can navigate to it. */
function resolveUrl(relativeUrl: string): string {
  const isTauri = '__TAURI_INTERNALS__' in window || '__TAURI__' in window
  return isTauri ? `${BACKEND_URL}${relativeUrl}` : relativeUrl
}

export default function AttachmentField({ patentId, databaseId, fieldKey, value, displayMode = 'all', onChange }: AttachmentFieldProps) {
  const [attachments, setAttachments] = useState<AttachmentMeta[]>(normalize(value))
  const [noteDrafts, setNoteDrafts] = useState<Record<number, string>>(() => Object.fromEntries(normalize(value).map(item => [item.attachment_id, item.note || ''])))
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [savedNoteId, setSavedNoteId] = useState<number | null>(null)
  const [lightboxIndex, setLightboxIndex] = useState<number | null>(null)
  const imageAttachments = attachments.filter(item => item.is_image || item.mime_type.startsWith('image/'))
  const displayedAttachments = displayMode === 'thumbnail' ? imageAttachments.slice(0, 1) : attachments

  const openImage = (attachment: AttachmentMeta) => {
    const index = imageAttachments.findIndex(item => item.attachment_id === attachment.attachment_id)
    if (index >= 0) setLightboxIndex(index)
  }

  const openFile = async (attachment: AttachmentMeta, preview: boolean) => {
    const popup = preview ? window.open('', '_blank') : null
    try {
      const blob = await attachmentApi.download(attachment.attachment_id, preview)
      const url = URL.createObjectURL(blob)
      if (popup) {
        popup.location.href = url
        window.setTimeout(() => URL.revokeObjectURL(url), 60_000)
      } else {
        const a = document.createElement('a')
        a.href = url
        a.download = attachment.filename
        document.body.appendChild(a)
        a.click()
        a.remove()
        window.setTimeout(() => URL.revokeObjectURL(url), 5_000)
      }
    } catch (requestError: unknown) {
      popup?.close()
      setError(getErrorMessage(requestError, preview ? '附件预览失败' : '附件下载失败'))
    }
  }

  const upload = async (file: File) => {
    if (!databaseId) return
    setBusy(true)
    setError(null)
    try {
      const body = new FormData()
      body.append('database_id', String(databaseId))
      body.append('patent_id', String(patentId))
      body.append('field_key', fieldKey)
      body.append('file', file)
      const created = await attachmentApi.upload(body)
      const next = [...attachments, created]
      setAttachments(next)
      setNoteDrafts(current => ({ ...current, [created.attachment_id]: created.note || '' }))
      onChange?.(next)
    } catch (requestError: unknown) {
      setError(getErrorMessage(requestError, '附件上传失败'))
    } finally {
      setBusy(false)
    }
  }

  const saveNote = async (attachment: AttachmentMeta) => {
    setBusy(true)
    setError(null)
    try {
      const updated = await attachmentApi.update(attachment.attachment_id, { note: noteDrafts[attachment.attachment_id] || null })
      const next = attachments.map(item => item.attachment_id === attachment.attachment_id ? updated : item)
      setAttachments(next)
      setNoteDrafts(current => ({ ...current, [attachment.attachment_id]: updated.note || '' }))
      setSavedNoteId(attachment.attachment_id)
      onChange?.(next)
    } catch (requestError: unknown) {
      setError(getErrorMessage(requestError, '附件备注保存失败'))
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
      setNoteDrafts(current => {
        const next = { ...current }
        delete next[attachment.attachment_id]
        return next
      })
      onChange?.(next)
    } catch (requestError: unknown) {
      setError(getErrorMessage(requestError, '附件删除失败'))
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="attachment-field" onClick={event => event.stopPropagation()}>
      <div className={`attachment-list attachment-list-${displayMode}`}>
        {displayedAttachments.map(attachment => (
          <Fragment key={attachment.attachment_id}>
          <div className="attachment-item">
            <div className="attachment-media">
              {attachment.is_image || attachment.mime_type.startsWith('image/') ? (
                <button
                  type="button"
                  className="attachment-thumbnail-button"
                  title={`预览 ${attachment.filename}`}
                  onClick={() => openImage(attachment)}
                >
                  <img
                    className="attachment-thumbnail"
                    src={resolveUrl(attachment.preview_url)}
                    alt={attachment.filename}
                    loading="lazy"
                  />
                </button>
              ) : null}
              <span className="attachment-name" title={attachment.filename}>{attachment.filename}</span>
            </div>
            <span className="attachment-size">{formatSize(attachment.file_size)}</span>
            <button type="button" className="attachment-action" onClick={() => { if (attachment.is_image || attachment.mime_type.startsWith('image/')) openImage(attachment); else void openFile(attachment, true) }}>预览</button>
            <button type="button" className="attachment-action" onClick={() => void openFile(attachment, false)}>下载</button>
            <button type="button" className="attachment-action attachment-action-danger" disabled={busy} onClick={() => void remove(attachment)}>删除</button>
          </div>
          {displayMode === 'all' && <div className="attachment-note-row">
            <label htmlFor={`attachment-note-${attachment.attachment_id}`}>备注</label>
            <textarea
              id={`attachment-note-${attachment.attachment_id}`}
              className="form-input"
              rows={2}
              maxLength={2000}
              value={noteDrafts[attachment.attachment_id] ?? attachment.note ?? ''}
              onChange={event => { setSavedNoteId(current => current === attachment.attachment_id ? null : current); setNoteDrafts(current => ({ ...current, [attachment.attachment_id]: event.target.value })) }}
              placeholder="填写该附件对应的项目、用途或补充说明"
              disabled={busy}
            />
            <button
              type="button"
              className="btn btn-secondary"
              disabled={busy || (noteDrafts[attachment.attachment_id] ?? attachment.note ?? '') === (attachment.note || '')}
              onClick={() => void saveNote(attachment)}
            >{savedNoteId === attachment.attachment_id ? '已保存' : '保存备注'}</button>
          </div>}
          </Fragment>
        ))}
        {displayMode === 'thumbnail' && imageAttachments.length > 1 && <span className="attachment-count">共 {imageAttachments.length} 张</span>}
      </div>
      <label className={`attachment-upload ${busy ? 'is-busy' : ''}`}>
        <span>{busy ? '处理中...' : '+ 添加附件'}</span>
        <input type="file" disabled={busy || !databaseId} onChange={event => { const file = event.target.files?.[0]; if (file) void upload(file); event.target.value = '' }} />
      </label>
      {error && <div className="attachment-error">{error}</div>}
      {lightboxIndex !== null && (
        <ImageLightbox
          images={imageAttachments.map(image => ({
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
