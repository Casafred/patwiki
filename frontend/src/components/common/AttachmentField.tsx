import { useState } from 'react'
import { attachmentApi } from '../../api'
import type { AttachmentMeta, JsonValue } from '../../types'
import { getErrorMessage } from '../../lib/errors'

interface AttachmentFieldProps {
  patentId: number
  databaseId: number | null
  fieldKey: string
  value: JsonValue
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

export default function AttachmentField({ patentId, databaseId, fieldKey, value }: AttachmentFieldProps) {
  const [attachments, setAttachments] = useState<AttachmentMeta[]>(normalize(value))
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const openFile = async (attachment: AttachmentMeta, preview: boolean) => {
    const popup = window.open('', '_blank')
    try {
      const blob = await attachmentApi.download(attachment.attachment_id, preview)
      const url = URL.createObjectURL(blob)
      if (popup) popup.location.href = url
      else window.open(url, '_blank')
      window.setTimeout(() => URL.revokeObjectURL(url), 60_000)
    } catch (requestError: unknown) {
      popup?.close()
      setError(getErrorMessage(requestError, '文件打开失败'))
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
      setAttachments(current => [...current, created])
    } catch (requestError: unknown) {
      setError(getErrorMessage(requestError, '附件上传失败'))
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
      setAttachments(current => current.filter(item => item.attachment_id !== attachment.attachment_id))
    } catch (requestError: unknown) {
      setError(getErrorMessage(requestError, '附件删除失败'))
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="attachment-field" onClick={event => event.stopPropagation()}>
      <div className="attachment-list">
        {attachments.map(attachment => (
          <div className="attachment-item" key={attachment.attachment_id}>
            <span className="attachment-name" title={attachment.filename}>{attachment.filename}</span>
            <span className="attachment-size">{formatSize(attachment.file_size)}</span>
            <button type="button" className="attachment-action" onClick={() => void openFile(attachment, true)}>预览</button>
            <button type="button" className="attachment-action" onClick={() => void openFile(attachment, false)}>下载</button>
            <button type="button" className="attachment-action attachment-action-danger" disabled={busy} onClick={() => void remove(attachment)}>删除</button>
          </div>
        ))}
      </div>
      <label className={`attachment-upload ${busy ? 'is-busy' : ''}`}>
        <span>{busy ? '处理中...' : '+ 添加附件'}</span>
        <input type="file" disabled={busy || !databaseId} onChange={event => { const file = event.target.files?.[0]; if (file) void upload(file); event.target.value = '' }} />
      </label>
      {error && <div className="attachment-error">{error}</div>}
    </div>
  )
}
