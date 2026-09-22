import type { AttachmentMeta } from '../../types'
import { BACKEND_URL } from '../../lib/api'

interface PatentImageStripProps {
  attachments: AttachmentMeta[]
}

function resolveUrl(relativeUrl: string): string {
  const isTauri = '__TAURI_INTERNALS__' in window || '__TAURI__' in window
  return isTauri ? `${BACKEND_URL}${relativeUrl}` : relativeUrl
}

export default function PatentImageStrip({ attachments }: PatentImageStripProps) {
  const images = attachments.filter(item => item.is_image || item.mime_type?.startsWith('image/'))
  if (images.length === 0) return null
  return (
    <div className="patent-image-strip" onClick={event => event.stopPropagation()}>
      <span className="patent-image-strip-label">图片 {images.length}</span>
      <div className="patent-image-strip-list">
        {images.map(image => (
          <a key={image.attachment_id} href={resolveUrl(image.preview_url)} target="_blank" rel="noreferrer noopener" title={image.filename}>
            <img src={resolveUrl(image.preview_url)} alt={image.filename} loading="lazy" />
          </a>
        ))}
      </div>
    </div>
  )
}
