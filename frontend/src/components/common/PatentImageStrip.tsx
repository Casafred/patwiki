import { useState } from 'react'
import type { AttachmentMeta } from '../../types'
import { BACKEND_URL } from '../../lib/api'
import ImageLightbox from './ImageLightbox'

interface PatentImageStripProps {
  attachments: AttachmentMeta[]
}

function resolveUrl(relativeUrl: string): string {
  const isTauri = '__TAURI_INTERNALS__' in window || '__TAURI__' in window
  return isTauri ? `${BACKEND_URL}${relativeUrl}` : relativeUrl
}

export default function PatentImageStrip({ attachments }: PatentImageStripProps) {
  const [lightboxIndex, setLightboxIndex] = useState<number | null>(null)
  const images = attachments.filter(item => item.is_image || item.mime_type?.startsWith('image/'))
  if (images.length === 0) return null
  return (
    <div className="patent-image-strip" onClick={event => event.stopPropagation()}>
      <span className="patent-image-strip-label">图片 {images.length}</span>
      <div className="patent-image-strip-list">
        {images.map((image, index) => (
          <button
            key={image.attachment_id}
            type="button"
            className="patent-image-strip-thumb"
            title={image.filename}
            onClick={() => setLightboxIndex(index)}
          >
            <img src={resolveUrl(image.preview_url)} alt={image.filename} loading="lazy" />
          </button>
        ))}
      </div>
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
