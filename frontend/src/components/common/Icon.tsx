import type { ReactNode, SVGProps } from 'react'

export type IconName =
  | 'activity' | 'automation' | 'chart' | 'check' | 'chevron-down' | 'chevron-left' | 'chevron-right' | 'chevron-up'
  | 'columns' | 'copy' | 'dashboard' | 'download' | 'file' | 'filter' | 'history' | 'lock' | 'menu'
  | 'play' | 'refresh' | 'settings' | 'sliders' | 'sparkles' | 'table' | 'tag' | 'trash'
  | 'undo' | 'unlock' | 'redo' | 'users' | 'x'

const paths: Record<IconName, ReactNode> = {
  activity: <path d="M3 12h4l2-7 4 14 2-7h6" />,
  automation: <path d="M12 3v4m0 10v4M3 12h4m10 0h4M5.6 5.6l2.8 2.8m6.9 6.9 2.8 2.8m0-12.5-2.8 2.8m-6.9 6.9-2.8 2.8" />,
  chart: <path d="M4 19V5m0 14h16M8 16v-5m4 5V7m4 9v-8" />,
  check: <path d="m5 12 4 4L19 6" />,
  'chevron-down': <path d="m6 9 6 6 6-6" />,
  'chevron-left': <path d="m14 5-7 7 7 7" />,
  'chevron-right': <path d="m10 5 7 7-7 7" />,
  'chevron-up': <path d="m6 15 6-6 6 6" />,
  columns: <path d="M4 4h16v16H4zm5 0v16m6-16v16" />,
  copy: <path d="M8 8h11v12H8zM5 16H4V4h11v1" />,
  dashboard: <path d="M4 4h7v7H4zm9 0h7v7h-7zM4 13h7v7H4zm9 0h7v7h-7z" />,
  download: <path d="M12 3v12m0 0 4-4m-4 4-4-4M4 20h16" />,
  file: <path d="M6 3h8l4 4v14H6zM14 3v5h5M9 13h6m-6 4h6" />,
  filter: <path d="M4 5h16l-6 7v5l-4 2v-7z" />,
  history: <path d="M3 12a9 9 0 1 0 3-6.7M3 4v5h5m4-1v5l3 2" />,
  lock: <path d="M7 10V8a5 5 0 0 1 10 0v2m-11 0h12v10H6z" />,
  menu: <path d="M4 6h16M4 12h16M4 18h16" />,
  play: <path d="m9 6 9 6-9 6z" />,
  refresh: <path d="M20 11a8 8 0 0 0-14.7-4L3 10m0 0V5m0 5h5M4 13a8 8 0 0 0 14.7 4L21 14m0 0v5m0-5h-5" />,
  settings: <path d="M12 8a4 4 0 1 0 0 8 4 4 0 0 0 0-8zm0-5v3m0 14v3M3 12h3m12 0h3M5.6 5.6l2.1 2.1m8.6 8.6 2.1 2.1m0-12.8-2.1 2.1m-8.6 8.6-2.1 2.1" />,
  sliders: <path d="M4 6h10m4 0h2M4 12h3m4 0h9M4 18h10m4 0h2M14 4v4M7 10v4M14 16v4" />,
  sparkles: <path d="m12 3 1.2 4.8L18 9l-4.8 1.2L12 15l-1.2-4.8L6 9l4.8-1.2zm7 11 .6 2.4L22 17l-2.4.6L19 20l-.6-2.4L16 17l2.4-.6z" />,
  table: <path d="M4 4h16v16H4zm0 5h16M9 4v16" />,
  tag: <path d="M4 5v6l9 9 6-6-9-9zm3 3h.01" />,
  trash: <path d="M4 7h16m-10 4v6m4-6v6M9 7V4h6v3m-9 0 1 13h10l1-13" />,
  undo: <path d="M9 7 4 12l5 5M5 12h8a6 6 0 0 1 6 6" />,
  redo: <path d="m15 7 5 5-5 5m4-5h-8a6 6 0 0 0-6 6" />,
  unlock: <path d="M17 10V8a5 5 0 0 0-9.8-1.2M6 10h12v10H6z" />,
  users: <path d="M16 20v-1a4 4 0 0 0-4-4H7a4 4 0 0 0-4 4v1m6-9a4 4 0 1 0 0-8 4 4 0 0 0 0 8zm8 1a3 3 0 1 0-1-5.8M21 20v-1a4 4 0 0 0-3-3.9" />,
  x: <path d="m6 6 12 12M18 6 6 18" />,
}

export default function Icon({ name, size = 16, strokeWidth = 1.8, ...props }: { name: IconName; size?: number; strokeWidth?: number } & Omit<SVGProps<SVGSVGElement>, 'name'>) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={strokeWidth} strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" {...props}>
      {paths[name]}
    </svg>
  )
}
