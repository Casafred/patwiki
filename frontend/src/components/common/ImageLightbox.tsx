import { useEffect } from 'react'
import { createPortal } from 'react-dom'

export interface LightboxImage {
  src: string
  title?: string
  downloadUrl?: string
}

interface ImageLightboxProps {
  images: LightboxImage[]
  index: number
  onClose: () => void
  onIndexChange: (index: number) => void
}

export default function ImageLightbox({ images, index, onClose, onIndexChange }: ImageLightboxProps) {
  const count = images.length
  const safeIndex = count === 0 ? 0 : ((index % count) + count) % count
  const current = images[safeIndex]

  useEffect(() => {
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        event.stopPropagation()
        onClose()
      } else if (count > 1 && event.key === 'ArrowLeft') {
        event.stopPropagation()
        onIndexChange((safeIndex - 1 + count) % count)
      } else if (count > 1 && event.key === 'ArrowRight') {
        event.stopPropagation()
        onIndexChange((safeIndex + 1) % count)
      }
    }
    document.addEventListener('keydown', handleKeyDown, true)
    return () => document.removeEventListener('keydown', handleKeyDown, true)
  }, [count, safeIndex, onClose, onIndexChange])

  if (!current) return null

  const step = (delta: number) => {
    if (count <= 1) return
    onIndexChange((safeIndex + delta + count) % count)
  }

  return createPortal(
    <div
      className="image-lightbox-overlay"
      role="presentation"
      onMouseDown={event => {
        if (event.target === event.currentTarget) onClose()
      }}
    >
      <button type="button" className="image-lightbox-close" onClick={onClose} aria-label="关闭">×</button>
      {count > 1 && (
        <button type="button" className="image-lightbox-nav image-lightbox-prev" onClick={() => step(-1)} aria-label="上一张">‹</button>
      )}
      <figure className="image-lightbox-figure">
        <img className="image-lightbox-image" src={current.src} alt={current.title || ''} />
        <figcaption className="image-lightbox-caption">
          {current.title && <span className="image-lightbox-title" title={current.title}>{current.title}</span>}
          <span className="image-lightbox-counter">{safeIndex + 1} / {count}</span>
          {current.downloadUrl && (
            <a className="image-lightbox-download" href={current.downloadUrl} download onClick={event => event.stopPropagation()}>下载</a>
          )}
        </figcaption>
      </figure>
      {count > 1 && (
        <button type="button" className="image-lightbox-nav image-lightbox-next" onClick={() => step(1)} aria-label="下一张">›</button>
      )}
    </div>,
    document.body,
  )
}
