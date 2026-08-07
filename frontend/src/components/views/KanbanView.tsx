import { useCallback, useEffect, useMemo, useState } from 'react'
import { viewApi } from '../../api'
import type { FieldMeta, KanbanCard, KanbanConfig, KanbanGroup, KanbanResponse, PatentView } from '../../types'

interface KanbanViewProps {
  view: PatentView
  fields: FieldMeta[]
  onPatentClick: (id: number) => void
  onViewChange: (view: PatentView) => void
  onTotalChange: (total: number) => void
}

const DEFAULT_CARD_FIELDS = ['application_number', 'title', 'legal_status']

function getConfig(view: PatentView): KanbanConfig {
  const config = view.kanban_config as Partial<KanbanConfig> | undefined
  const cardFields = config?.card_fields?.length ? config.card_fields : DEFAULT_CARD_FIELDS
  const titleField = config?.card_title_field || cardFields[0] || 'title'
  return {
    group_by_field: config?.group_by_field || 'legal_status',
    group_values: config?.group_values || [],
    card_fields: cardFields,
    card_title_field: titleField,
  }
}

function formatValue(value: unknown): string {
  if (value === null || value === undefined || value === '') return '未设置'
  if (typeof value === 'boolean') return value ? '是' : '否'
  if (Array.isArray(value)) return value.join('、')
  return String(value)
}

function sameValue(left: unknown, right: unknown): boolean {
  return JSON.stringify(left) === JSON.stringify(right)
}

export default function KanbanView({ view, fields, onPatentClick, onViewChange, onTotalChange }: KanbanViewProps) {
  const config = useMemo(() => getConfig(view), [view])
  const configKey = JSON.stringify(view.kanban_config || {})
  const [data, setData] = useState<KanbanResponse | null>(null)
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [draggingCard, setDraggingCard] = useState<KanbanCard | null>(null)
  const [dropTarget, setDropTarget] = useState<string | null>(null)

  const load = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const result = await viewApi.kanban(view.id, { page_size: 500 })
      setData(result)
      onTotalChange(result.total)
    } catch (e) {
      console.error('Failed to load kanban data:', e)
      setError('看板数据加载失败')
    } finally {
      setLoading(false)
    }
  }, [view.id, onTotalChange])

  useEffect(() => {
    // The request updates local loading/data state when it resolves.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    void load()
  }, [load, configKey])

  const availableFields = useMemo(() => {
    const configuredKeys = new Set(config.card_fields)
    const visibleFields = fields.filter(field => field.editable !== false)
    const configuredFields = config.card_fields
      .map(key => fields.find(field => field.key === key))
      .filter((field): field is FieldMeta => Boolean(field))
    const missingFields = visibleFields.filter(field => !configuredKeys.has(field.key))
    return [...configuredFields, ...missingFields].slice(0, 18)
  }, [config.card_fields, fields])

  const updateConfig = async (updates: Partial<KanbanConfig>) => {
    setSaving(true)
    try {
      const updated = await viewApi.update(view.id, {
        kanban_config: { ...config, ...updates },
      })
      onViewChange(updated)
    } catch (e) {
      console.error('Failed to update kanban config:', e)
      setError('看板配置保存失败')
    } finally {
      setSaving(false)
    }
  }

  const handleGroupFieldChange = (fieldKey: string) => {
    const nextCardFields = config.card_fields.includes(fieldKey)
      ? config.card_fields
      : [fieldKey, ...config.card_fields].slice(0, 12)
    void updateConfig({ group_by_field: fieldKey, card_fields: nextCardFields, card_title_field: config.card_title_field || fieldKey })
  }

  const toggleCardField = (fieldKey: string) => {
    const nextFields = config.card_fields.includes(fieldKey)
      ? config.card_fields.filter(key => key !== fieldKey)
      : [...config.card_fields, fieldKey].slice(0, 12)
    if (nextFields.length === 0) return
    const titleField = nextFields.includes(config.card_title_field) ? config.card_title_field : nextFields[0]
    void updateConfig({ card_fields: nextFields, card_title_field: titleField })
  }

  const handleDrop = async (group: KanbanGroup) => {
    if (!draggingCard || sameValue(draggingCard.group_value, group.key)) {
      setDraggingCard(null)
      setDropTarget(null)
      return
    }
    setSaving(true)
    setError(null)
    try {
      await viewApi.moveKanbanCard(view.id, {
        patent_id: draggingCard.id,
        from_value: draggingCard.group_value,
        to_value: group.key,
      })
      await load()
    } catch (e) {
      console.error('Failed to move kanban card:', e)
      setError('卡片移动失败，原字段值未改变')
    } finally {
      setSaving(false)
      setDraggingCard(null)
      setDropTarget(null)
    }
  }

  const fieldLabel = (key: string) => fields.find(field => field.key === key)?.name || key
  const groups = data?.groups || []

  return (
    <div className="kanban-view">
      <div className="kanban-toolbar">
        <div className="kanban-toolbar-group">
          <label htmlFor="kanban-group-field">分组字段</label>
          <select
            id="kanban-group-field"
            className="form-input kanban-select"
            value={config.group_by_field}
            onChange={event => handleGroupFieldChange(event.target.value)}
            disabled={saving}
          >
            {fields.filter(field => field.editable !== false).map(field => (
              <option key={field.key} value={field.key}>{field.name}</option>
            ))}
          </select>
        </div>
        <details className="kanban-fields-menu">
          <summary>卡片字段</summary>
          <div className="kanban-fields-panel">
            {availableFields.map(field => (
              <label key={field.key}>
                <input
                  type="checkbox"
                  checked={config.card_fields.includes(field.key)}
                  onChange={() => toggleCardField(field.key)}
                  disabled={saving}
                />
                {field.name}
              </label>
            ))}
          </div>
        </details>
        <span className="kanban-total">{data?.total ?? 0} 件</span>
        {data?.truncated && <span className="kanban-warning">当前仅加载前 500 件</span>}
        {saving && <span className="kanban-saving">保存中...</span>}
      </div>

      {error && <div className="kanban-error">{error}</div>}
      {loading ? (
        <div className="loading-state"><div className="spinner" />加载看板...</div>
      ) : groups.length === 0 ? (
        <div className="empty-state"><div className="empty-state-title">暂无看板数据</div></div>
      ) : (
        <div className="kanban-board">
          {groups.map(group => {
            const groupId = group.key === null ? '__empty__' : String(group.key)
            return (
              <section
                className={`kanban-column ${dropTarget === groupId ? 'kanban-column-drop-target' : ''}`}
                key={groupId}
                onDragOver={event => { event.preventDefault(); setDropTarget(groupId) }}
                onDragLeave={() => setDropTarget(null)}
                onDrop={event => { event.preventDefault(); void handleDrop(group) }}
              >
                <header className="kanban-column-header">
                  <span>{group.label}</span>
                  <span className="kanban-column-count">{group.count}</span>
                </header>
                <div className="kanban-card-list">
                  {group.cards.map(card => (
                    <article
                      className={`kanban-card ${draggingCard?.id === card.id ? 'kanban-card-dragging' : ''}`}
                      key={card.id}
                      draggable
                      onDragStart={event => {
                        event.dataTransfer.effectAllowed = 'move'
                        setDraggingCard(card)
                      }}
                      onDragEnd={() => { setDraggingCard(null); setDropTarget(null) }}
                      onClick={() => onPatentClick(card.id)}
                    >
                      <button className="kanban-card-title" onClick={() => onPatentClick(card.id)}>
                        {card.title}
                      </button>
                      {config.card_fields.filter(field => field !== config.card_title_field).map(field => (
                        <div className="kanban-card-field" key={field}>
                          <span>{fieldLabel(field)}</span>
                          <strong>{formatValue(card.fields[field])}</strong>
                        </div>
                      ))}
                    </article>
                  ))}
                  {group.cards.length === 0 && <div className="kanban-column-empty">拖拽卡片到这里</div>}
                </div>
              </section>
            )
          })}
        </div>
      )}
    </div>
  )
}
