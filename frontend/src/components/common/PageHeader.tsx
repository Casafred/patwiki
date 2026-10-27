import type { ReactNode } from 'react'

export default function PageHeader({ title, description, actions }: {
  title: ReactNode
  description?: ReactNode
  actions?: ReactNode
}) {
  return <header className="workspace-heading">
    <div className="workspace-heading-copy"><h2>{title}</h2>{description && <p>{description}</p>}</div>
    {actions && <div className="workspace-heading-actions">{actions}</div>}
  </header>
}
