import { createContext, useContext, useLayoutEffect, useRef, useState, type HTMLAttributes, type ReactNode, type RefObject } from 'react'
import { createPortal } from 'react-dom'

const AnchorContext = createContext<RefObject<HTMLElement | null> | null>(null)
const openPanels: HTMLElement[] = []

export function TableDropdownScope({ children }: { children: ReactNode }) {
  const anchor = useRef<HTMLElement | null>(null)
  return <AnchorContext.Provider value={anchor}>
    <div style={{ display: 'contents' }} onClickCapture={event => {
      const target = event.target as HTMLElement
      if (target.closest('[data-table-dropdown]')) return
      const workbench = target.closest('.workbench-shell')
      const button = target.closest<HTMLElement>('button, th, [role="button"]')
      anchor.current = workbench && button
        ? button.closest('.toolbar-menu')?.querySelector<HTMLElement>(':scope > button') || button
        : null
    }}>
      {children}
    </div>
  </AnchorContext.Provider>
}

interface DropdownProps {
  children: ReactNode
  onClose: () => void
  width?: number
  anchor?: HTMLElement | null
  className?: string
  role?: string
  label?: string
}

export function TableDropdown({ children, onClose, width = 480, anchor: explicitAnchor, className = '', role = 'dialog', label }: DropdownProps) {
  const context = useContext(AnchorContext)
  const [anchor] = useState(() => explicitAnchor || context?.current || null)
  const panel = useRef<HTMLDivElement>(null)
  const close = useRef(onClose)
  useLayoutEffect(() => { close.current = onClose }, [onClose])
  const [position, setPosition] = useState({ left: 8, top: 8, width: Math.min(width, window.innerWidth - 16), maxHeight: window.innerHeight - 16 })

  useLayoutEffect(() => {
    const element = panel.current
    if (!element) return
    openPanels.push(element)
    const update = () => {
      const viewport = window.visualViewport
      const viewportWidth = viewport?.width || window.innerWidth
      const viewportHeight = viewport?.height || window.innerHeight
      const x = viewport?.offsetLeft || 0
      const y = viewport?.offsetTop || 0
      const rect = anchor?.isConnected ? anchor.getBoundingClientRect() : null
      const panelWidth = Math.min(width, viewportWidth - 16)
      const below = rect ? y + viewportHeight - rect.bottom - 16 : viewportHeight - 16
      const above = rect ? rect.top - y - 16 : 0
      const flip = below < Math.min(role === 'menu' ? element.scrollHeight : 360, viewportHeight - 16) && above > below
      const maxHeight = Math.max(80, flip ? above : below)
      const height = Math.min(element.scrollHeight, maxHeight)
      setPosition({
        left: Math.max(x + 8, Math.min(rect?.left ?? x + 8, x + viewportWidth - panelWidth - 8)),
        top: Math.max(y + 8, Math.min(flip && rect ? rect.top - height - 8 : (rect?.bottom ?? y) + 8, y + viewportHeight - height - 8)),
        width: panelWidth,
        maxHeight: Math.min(maxHeight, viewportHeight - 16),
      })
    }
    const outside = (event: PointerEvent) => {
      if (openPanels.at(-1) !== element) return
      if (role === 'menu' && anchor?.contains(event.target as Node)) return
      if (!element.contains(event.target as Node)) close.current()
    }
    const keyboard = (event: KeyboardEvent) => {
      if (event.key !== 'Escape' || openPanels.at(-1) !== element) return
      event.preventDefault()
      event.stopPropagation()
      close.current()
      anchor?.focus()
    }
    const observer = new ResizeObserver(update)
    if (element.firstElementChild) observer.observe(element.firstElementChild)
    update()
    document.addEventListener('pointerdown', outside)
    document.addEventListener('keydown', keyboard)
    window.addEventListener('resize', update)
    window.addEventListener('scroll', update, true)
    window.visualViewport?.addEventListener('resize', update)
    window.visualViewport?.addEventListener('scroll', update)
    // Focus the surface without opening a mobile keyboard or moving the page.
    element.focus({ preventScroll: true })
    return () => {
      openPanels.splice(openPanels.indexOf(element), 1)
      observer.disconnect()
      document.removeEventListener('pointerdown', outside)
      document.removeEventListener('keydown', keyboard)
      window.removeEventListener('resize', update)
      window.removeEventListener('scroll', update, true)
      window.visualViewport?.removeEventListener('resize', update)
      window.visualViewport?.removeEventListener('scroll', update)
    }
  }, [anchor, width, role])

  return createPortal(<div ref={panel} data-table-dropdown className={`table-dropdown ${className}`} role={role} aria-label={label} tabIndex={-1} style={position}>
    {children}
  </div>, document.body)
}

// Shared dialogs keep their existing presentation outside the main table.
export default function TableDropdownOverlay({ children, onClose, width = 680, ...props }: HTMLAttributes<HTMLDivElement> & { onClose: () => void; width?: number }) {
  const context = useContext(AnchorContext)
  const [anchor] = useState(() => context?.current || null)
  if (!anchor) return <div {...props}>{children}</div>
  return <TableDropdown anchor={anchor} onClose={onClose} width={width}>{children}</TableDropdown>
}
