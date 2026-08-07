import { useState } from 'react'
import { viewApi } from '../../api'
import { useAppStore } from '../../store'

interface ViewSwitcherProps {
  onOpenView: () => void
}

const layoutLabels: Record<string, string> = {
  table: '表格',
  kanban: '看板',
  form: '表单',
  gantt: '甘特',
  calendar: '日历',
}

export default function ViewSwitcher({ onOpenView }: ViewSwitcherProps) {
  const {
    currentDatabaseId,
    views,
    currentViewId,
    setViews,
    setCurrentViewId,
  } = useAppStore()
  const [showCreate, setShowCreate] = useState(false)
  const [name, setName] = useState('')
  const [creating, setCreating] = useState(false)

  const handleChange = (viewId: number) => {
    setCurrentViewId(viewId)
    onOpenView()
  }

  const handleCreate = async () => {
    if (!currentDatabaseId || !name.trim() || creating) return
    setCreating(true)
    try {
      const view = await viewApi.create({
        name: name.trim(),
        database_id: currentDatabaseId,
        view_type: 'personal',
        layout_type: 'table',
      })
      setViews([...views, view])
      setCurrentViewId(view.id)
      setName('')
      setShowCreate(false)
      onOpenView()
    } catch {
      alert('创建视图失败')
    } finally {
      setCreating(false)
    }
  }

  return (
    <div className="view-switcher">
      <div className="nav-section">视图</div>
      <div className="view-switcher-control">
        <select
          className="form-input view-switcher-select"
          value={currentViewId ?? ''}
          onChange={(e) => handleChange(Number(e.target.value))}
          disabled={views.length === 0}
          aria-label="选择当前视图"
        >
          {views.length === 0 && <option value="">暂无视图</option>}
          {views.map(view => (
            <option key={view.id} value={view.id}>
              {view.name} · {layoutLabels[view.layout_type] || '表格'}
            </option>
          ))}
        </select>
        <button
          className="view-add-button"
          type="button"
          onClick={() => setShowCreate(value => !value)}
          title="新建个人视图"
        >
          +
        </button>
      </div>
      {showCreate && (
        <div className="view-create-form">
          <input
            className="form-input"
            value={name}
            onChange={(e) => setName(e.target.value)}
            onKeyDown={(e) => { if (e.key === 'Enter') void handleCreate() }}
            placeholder="视图名称"
            autoFocus
          />
          <div className="view-create-actions">
            <button className="btn btn-primary btn-sm" type="button" onClick={() => void handleCreate()} disabled={creating}>
              创建
            </button>
            <button className="btn btn-ghost btn-sm" type="button" onClick={() => setShowCreate(false)}>
              取消
            </button>
          </div>
        </div>
      )}
    </div>
  )
}
