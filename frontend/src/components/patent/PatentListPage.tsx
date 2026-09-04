import { Fragment, useState, useEffect, useCallback, useRef } from 'react'
import { useLocation, useSearchParams } from 'react-router-dom'
import {
  patentService as patentApi,
  fieldService as fieldApi,
  aiService as aiApi,
  customFieldService as customFieldApi,
  analyticsService as analyticsApi,
  viewService as viewApi,
  relationService as linkApi,
  searchService as searchApi,
  tagService as tagApi,
} from '../../services'
import { useAppStore } from '../../store'
import type {
  Patent, FieldMeta, CustomField, AITask, PatentView, ViewGroup,
  ViewGroupField, ViewColumnConfig, ConditionalFormatRule, JsonObject, JsonValue, LinkRecord, LinkTarget, SearchSuggestion,
  Tag,
} from '../../types'
import { getErrorMessage } from '../../lib/errors'
import { formatApiDate, parseApiDate } from '../../lib/date'
import Icon from '../common/Icon'
import GroupConfigPanel from '../views/GroupConfigPanel'
import ViewColumnConfigPanel from '../views/ViewColumnConfigPanel'
import ColumnConfigPanel from '../views/ColumnConfigPanel'
import ConditionalFormatPanel from '../views/ConditionalFormatPanel'
import KanbanView from '../views/KanbanView'
import FormView from '../views/FormView'
import GanttView from '../views/GanttView'
import ExportDialog from '../common/ExportDialog'
import WorkFileDialog from '../common/WorkFileDialog'
import AttachmentField from '../common/AttachmentField'
import AIQuickAnalyzeModal from '../ai/AIQuickAnalyzeModal'

interface PatentListPageProps {
  onPatentClick: (id: number) => void
  viewId?: number | null
  onOpenImport?: () => void
  onOpenSidebar?: () => void
}

type SortOrder = 'asc' | 'desc'
type FilterOperator = 'contains' | 'eq' | 'starts_with' | 'ends_with' | 'is_empty' | 'is_not_empty'
interface FilterCondition {
  operator: FilterOperator
  value?: string
}
type FilterState = Record<string, FilterCondition>
type RelationCellData = { links?: LinkRecord[]; value?: JsonValue; aggregation?: string }
type BulkTransferAction = 'move_database' | 'move_view' | 'duplicate'
type TableViewMode = 'pagination' | 'continuous'
type RowHeightLimit = 'auto' | 56 | 72 | 96 | 120

const TABLE_VIEW_MODE_STORAGE_KEY = 'patwiki_table_view_mode'
const ROW_HEIGHT_LIMIT_STORAGE_KEY = 'patwiki_row_height_limit'
const CHECKBOX_COLUMN_WIDTH = 40
const INDEX_COLUMN_WIDTH = 56
const ACTION_COLUMN_WIDTH = 70
const PUBLICATION_REFERENCE_RE = /(?<![A-Za-z0-9])([A-Za-z]{2}\d+[A-Za-z]{1,3}\d{0,2})(?![A-Za-z0-9])/g
const TABLE_POSITION_STORAGE_PREFIX = 'patwiki_table_position:'

interface TablePositionSnapshot {
  page: number
  continuousPage: number
  scrollTop: number
  scrollLeft: number
  savedAt: number
}

interface TableDataSnapshot {
  items: Patent[]
  total: number
  continuousPage: number
  hasMore: boolean
  savedAt: number
}

// Keep a small in-memory cache for the current browser session. Returning from
// a Wiki detail page should render the previous result immediately instead of
// replaying every page that was loaded before navigation.
const tableDataCache = new Map<string, TableDataSnapshot>()
const TABLE_DATA_CACHE_LIMIT = 8

function saveTableDataSnapshot(key: string, snapshot: TableDataSnapshot) {
  tableDataCache.delete(key)
  tableDataCache.set(key, snapshot)
  while (tableDataCache.size > TABLE_DATA_CACHE_LIMIT) {
    const oldestKey = tableDataCache.keys().next().value
    if (!oldestKey) break
    tableDataCache.delete(oldestKey)
  }
}

function readTableViewMode(): TableViewMode {
  try {
    return localStorage.getItem(TABLE_VIEW_MODE_STORAGE_KEY) === 'continuous' ? 'continuous' : 'pagination'
  } catch {
    return 'pagination'
  }
}

function readRowHeightLimit(): RowHeightLimit {
  try {
    const value = localStorage.getItem(ROW_HEIGHT_LIMIT_STORAGE_KEY)
    if (value === 'auto') return 'auto'
    const parsed = Number(value)
    return [56, 72, 96, 120].includes(parsed) ? parsed as RowHeightLimit : 72
  } catch {
    return 72
  }
}

function readPageParam(params: URLSearchParams): number {
  const page = Number(params.get('page'))
  return Number.isInteger(page) && page > 0 ? page : 1
}

const FILTER_OPERATOR_LABELS: Record<FilterOperator, string> = {
  contains: '包含',
  eq: '等于',
  starts_with: '开头是',
  ends_with: '结尾是',
  is_empty: '为空',
  is_not_empty: '不为空',
}

function readFilterParam(params: URLSearchParams): FilterState {
  const raw = params.get('filters')
  if (!raw) return {}
  try {
    const parsed: unknown = JSON.parse(raw)
    if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) return {}
    const result: FilterState = {}
    Object.entries(parsed).forEach(([key, value]) => {
      if (typeof value === 'string' && value.trim()) {
        // Compatibility with URLs generated before structured filters.
        result[key] = { operator: 'contains', value }
        return
      }
      if (!value || typeof value !== 'object' || Array.isArray(value)) return
      const candidate = value as Record<string, unknown>
      const operator = (candidate.operator || Object.keys(candidate).find(item => item in FILTER_OPERATOR_LABELS)) as FilterOperator | undefined
      if (!operator || !(operator in FILTER_OPERATOR_LABELS)) return
      const candidateValue = candidate.value ?? candidate[operator]
      result[key] = { operator, ...(typeof candidateValue === 'string' ? { value: candidateValue } : {}) }
    })
    return result
  } catch {
    return {}
  }
}

function filterConditionHasValue(condition?: FilterCondition): boolean {
  if (!condition) return false
  return condition.operator === 'is_empty' || condition.operator === 'is_not_empty' || !!condition.value?.trim()
}

function PatentReferenceText({
  value,
  onOpen,
}: {
  value: string
  onOpen: (publicationNumber: string) => void
}) {
  const parts: React.ReactNode[] = []
  let lastIndex = 0
  const publicationReferencePattern = new RegExp(PUBLICATION_REFERENCE_RE.source, 'g')
  let match: RegExpExecArray | null
  while ((match = publicationReferencePattern.exec(value)) !== null) {
    if (match.index > lastIndex) parts.push(value.slice(lastIndex, match.index))
    const reference = match[1]
    parts.push(
      <button
        type="button"
        key={`${reference}-${match.index}`}
        className="cell-action-btn"
        title="打开此公开号对应的 PatWiki"
        onClick={(event) => {
          event.stopPropagation()
          onOpen(reference)
        }}
        style={{ border: 0, padding: 0, background: 'transparent', color: '#2563eb', cursor: 'pointer', textDecoration: 'underline', font: 'inherit' }}
      >
        {reference.toUpperCase().replace(/^JP0+(?=\d)/, 'JP')}
      </button>,
    )
    lastIndex = match.index + match[0].length
  }
  if (lastIndex < value.length) parts.push(value.slice(lastIndex))
  return <>{parts.length > 0 ? parts : value}</>
}

const DEFAULT_COLUMN_WIDTH = 150

function getViewGroupFields(view?: PatentView): ViewGroupField[] {
  const config = view?.group_by_config
  if (Array.isArray(config)) return config as ViewGroupField[]
  return (config as { fields?: ViewGroupField[] } | undefined)?.fields || []
}

function buildViewColumnConfig(view: PatentView, fields: FieldMeta[]): ViewColumnConfig[] {
  const configured = view.column_config || []
  const byKey = new Map(configured.map(column => [column.key, column]))
  const known = fields.map((field, index) => {
    const column = byKey.get(field.key)
    return {
      key: field.key,
      // 关系原始列属于信息中心的正式只读投影。历史视图没有保存这些新列
      // 时默认展示；用户明确隐藏后仍以视图配置为准。
      visible: column?.visible ?? (configured.length === 0 || ['family_members', 'cited_patents', 'citing_patents'].includes(field.key)
        ? field.visible !== false
        : false),
      width: column?.width ?? field.width ?? DEFAULT_COLUMN_WIDTH,
      order: column?.order ?? configured.length + index,
    }
  })
  const knownKeys = new Set(known.map(column => column.key))
  return [...known, ...configured.filter(column => !knownKeys.has(column.key))]
    .sort((a, b) => (a.order ?? 0) - (b.order ?? 0))
}

function flattenGroups(groups: ViewGroup[]): Patent[] {
  return groups.flatMap(group => group.subgroups
    ? flattenGroups(group.subgroups)
    : (group.patents || []))
}

interface GroupPresentation {
  visibleIds: Set<number>
  headerIds: Set<number>
  headers: Map<number, { id: string; label: string; field: string; count: number; depth: number }[]>
}

function getGroupPresentation(groups: ViewGroup[], collapsedKeys: Set<string>): GroupPresentation {
  const visibleIds = new Set<number>()
  const headerIds = new Set<number>()
  const headers = new Map<number, { id: string; label: string; field: string; count: number; depth: number }[]>()
  const firstLeafPatent = (items: ViewGroup[]): Patent | undefined => {
    for (const item of items) {
      if (item.patents?.[0]) return item.patents[0]
      const nested = firstLeafPatent(item.subgroups || [])
      if (nested) return nested
    }
    return undefined
  }
  const walk = (items: ViewGroup[], path: string[], parentCollapsed: boolean) => {
    items.forEach(group => {
      const id = [...path, `${group.field}:${group.key ?? '__empty__'}`].join('|')
      const isCollapsed = parentCollapsed || collapsedKeys.has(id)
      const children = group.subgroups || []
      const leafPatents = group.patents || []
      const firstPatent = leafPatents[0] || firstLeafPatent(children)
      if (firstPatent) {
        headerIds.add(firstPatent.id)
        const currentHeaders = headers.get(firstPatent.id) || []
        headers.set(firstPatent.id, [...currentHeaders, { id, label: group.label, field: group.field, count: group.count, depth: path.length }])
      }
      if (isCollapsed) return
      if (children.length > 0) walk(children, [...path, id], false)
      leafPatents.forEach(patent => visibleIds.add(patent.id))
    })
  }
  walk(groups, [], false)
  return { visibleIds, headerIds, headers }
}

function getDefaultCollapsedKeys(groups: ViewGroup[], path: string[] = []): string[] {
  return groups.flatMap(group => {
    const id = [...path, `${group.field}:${group.key ?? '__empty__'}`].join('|')
    const nested = getDefaultCollapsedKeys(group.subgroups || [], [...path, id])
    return [ ...(group.collapsed ? [id] : []), ...nested ]
  })
}

interface LinkFieldEditorProps {
  patentId: number
  field: FieldMeta
  currentLinks: LinkRecord[]
  onChanged: (links: LinkRecord[]) => void
  onCancel: () => void
}

function LinkFieldEditor({ patentId, field, currentLinks, onChanged, onCancel }: LinkFieldEditorProps) {
  const [selectedLinks, setSelectedLinks] = useState<LinkRecord[]>(currentLinks)
  const [targets, setTargets] = useState<LinkTarget[]>([])
  const [search, setSearch] = useState('')
  const [savingTargetId, setSavingTargetId] = useState<number | null>(null)
  const allowMultiple = field.link_config?.allow_multiple !== false

  useEffect(() => {
    let cancelled = false
    const loadTargets = async () => {
      try {
        const result = await linkApi.search(field.key, search, 20)
        if (!cancelled) setTargets(result)
      } catch (error: unknown) {
        if (!cancelled) console.error('Failed to load link targets:', error)
      }
    }
    void loadTargets()
    return () => { cancelled = true }
  }, [field.key, search])

  const addLink = async (target: LinkTarget) => {
    if (selectedLinks.some(link => link.target_record_id === target.id)) return
    setSavingTargetId(target.id)
    try {
      const created = await linkApi.create({
        field_key: field.key,
        source_record_id: patentId,
        target_record_id: target.id,
      })
      const next = allowMultiple ? [...selectedLinks, created] : [created]
      setSelectedLinks(next)
      onChanged(next)
      if (!allowMultiple) setSearch('')
    } catch (error: unknown) {
      alert('添加关联失败: ' + getErrorMessage(error))
    } finally {
      setSavingTargetId(null)
    }
  }

  const removeLink = async (link: LinkRecord) => {
    try {
      await linkApi.delete({
        field_key: field.key,
        source_record_id: patentId,
        target_record_id: link.target_record_id,
      })
      const next = selectedLinks.filter(item => item.id !== link.id)
      setSelectedLinks(next)
      onChanged(next)
    } catch (error: unknown) {
      alert('移除关联失败: ' + getErrorMessage(error))
    }
  }

  return (
    <div
      style={{ minWidth: 250, padding: 4 }}
      onClick={event => event.stopPropagation()}
    >
      <div style={{ display: 'flex', flexWrap: 'wrap', gap: 4, marginBottom: 6 }}>
        {selectedLinks.map(link => (
          <span key={link.id} style={{ display: 'inline-flex', alignItems: 'center', gap: 4, padding: '2px 6px', borderRadius: 4, background: '#eff6ff', color: '#1d4ed8', fontSize: 12 }}>
            <span>{link.label}</span>
            <button
              type="button"
              className="cell-action-btn"
              title="移除关联"
              onClick={() => void removeLink(link)}
              style={{ border: 'none', background: 'transparent', color: '#1d4ed8', cursor: 'pointer', padding: 0, lineHeight: 1 }}
            >
              ×
            </button>
          </span>
        ))}
        {selectedLinks.length === 0 && <span style={{ color: '#94a3b8', fontSize: 12 }}>尚未关联记录</span>}
      </div>
      {(allowMultiple || selectedLinks.length === 0) && (
        <>
          <input
            className="form-input"
            autoFocus
            value={search}
            placeholder="搜索目标记录..."
            onChange={event => setSearch(event.target.value)}
            style={{ width: '100%', fontSize: 12, padding: '4px 6px' }}
          />
          <div style={{ maxHeight: 120, overflowY: 'auto', marginTop: 4, border: '1px solid #e5e7eb', borderRadius: 4, background: '#fff' }}>
            {targets.map(target => (
              <button
                type="button"
                key={target.id}
                className="cell-action-btn"
                disabled={savingTargetId === target.id || selectedLinks.some(link => link.target_record_id === target.id)}
                onClick={() => void addLink(target)}
                style={{ display: 'block', width: '100%', textAlign: 'left', border: 'none', background: 'transparent', padding: '5px 7px', cursor: selectedLinks.some(link => link.target_record_id === target.id) ? 'default' : 'pointer', color: selectedLinks.some(link => link.target_record_id === target.id) ? '#94a3b8' : '#374151', fontSize: 12 }}
              >
                {target.label}
              </button>
            ))}
            {targets.length === 0 && <div style={{ padding: '6px 7px', color: '#94a3b8', fontSize: 12 }}>没有匹配记录</div>}
          </div>
        </>
      )}
      <div style={{ display: 'flex', justifyContent: 'flex-end', marginTop: 6 }}>
        <button type="button" className="btn btn-xs btn-secondary cell-action-btn" onClick={onCancel}>完成</button>
      </div>
    </div>
  )
}

export default function PatentListPage({ onPatentClick, viewId = null, onOpenImport, onOpenSidebar }: PatentListPageProps) {
  const {
    patents, totalPatents, currentProductId, currentDatabaseId, loading, databases, products,
    setPatents, setLoading, selectedIds, toggleSelect, clearSelection, setSelectedIds,
    groupByFamily, setGroupByFamily, views, setViews, setCurrentProductId,
    dataVersion,
  } = useAppStore()

  // 用 ref 保存 views，避免 views 变化时 loadPatents 被重建触发重渲染循环。
  // 原因：App.tsx 的视图加载 effect 依赖 searchParamsString，每次 URL 变化（含
  // 翻页）都会重跑并 setViews(新数组) → loadPatents 因依赖 views 被重建 →
  // loadPatents effect 重跑 → 又触发 URL 同步 → 又导致 searchParamsString 变化
  // → 死循环。改用 ref 后 loadPatents 不再依赖 views，循环被打破。
  const viewsRef = useRef(views)
  useEffect(() => {
    viewsRef.current = views
  }, [views])

  const location = useLocation()
  const [searchParams, setSearchParams] = useSearchParams()
  const searchParamsString = searchParams.toString()
  const routeDatabaseId = Number(location.pathname.match(/^\/db\/(\d+)(?:\/|$)/)?.[1])
  const queryDatabaseId = Number(searchParams.get('db'))
  const activeDatabaseId = Number.isInteger(routeDatabaseId) && routeDatabaseId > 0
    ? routeDatabaseId
    : Number.isInteger(queryDatabaseId) && queryDatabaseId > 0
      ? queryDatabaseId
      : currentDatabaseId
  const activeView = views.find(view => view.id === viewId && view.database_id === activeDatabaseId)
  const [page, setPage] = useState(() => readPageParam(searchParams))
  const [pageSize] = useState(50)
  const [tableViewMode, setTableViewMode] = useState<TableViewMode>(() => readTableViewMode())
  const [rowHeightLimit, setRowHeightLimit] = useState<RowHeightLimit>(() => readRowHeightLimit())
  const [continuousLoading, setContinuousLoading] = useState(false)
  const [searchText, setSearchText] = useState(() => searchParams.get('q') || '')
  const [searchInputText, setSearchInputText] = useState(() => searchParams.get('q') || '')
  const [searchSuggestions, setSearchSuggestions] = useState<SearchSuggestion[]>([])
  const [activeSuggestionIndex, setActiveSuggestionIndex] = useState(-1)
  const [sortField, setSortField] = useState<string>(() => searchParams.get('sort') || 'filing_date')
  const [sortOrder, setSortOrder] = useState<SortOrder>(() => searchParams.get('order') === 'asc' ? 'asc' : 'desc')
  const [fields, setFields] = useState<FieldMeta[]>([])
  const [columnWidths, setColumnWidths] = useState<Record<string, number>>({})
  const [undoStack, setUndoStack] = useState<Array<{ patentId: number; fieldKey: string; before: JsonValue; after: JsonValue }>>([])
  const [redoStack, setRedoStack] = useState<Array<{ patentId: number; fieldKey: string; before: JsonValue; after: JsonValue }>>([])
  const [activeHeaderMenu, setActiveHeaderMenu] = useState<string | null>(null)
  const [showTableTools, setShowTableTools] = useState(false)
  const [headerFilterText, setHeaderFilterText] = useState<string>('')
  const [headerFilterOperator, setHeaderFilterOperator] = useState<FilterOperator>('contains')
  const [editingCell, setEditingCell] = useState<{ patentId: number; fieldKey: string } | null>(null)
  const [resizing, setResizing] = useState<{ fieldKey: string; startX: number; startWidth: number } | null>(null)
  const [showFieldConfig, setShowFieldConfig] = useState(false)
  const [showTableSettings, setShowTableSettings] = useState(false)
  const [viewConfigNotice, setViewConfigNotice] = useState('')
  const [showBulkEdit, setShowBulkEdit] = useState(false)
  const [showBulkTag, setShowBulkTag] = useState(false)
  const [bulkTransferAction, setBulkTransferAction] = useState<BulkTransferAction | null>(null)
  const [bulkTargetDatabaseId, setBulkTargetDatabaseId] = useState<number | null>(null)
  const [bulkTargetViewId, setBulkTargetViewId] = useState<number | null>(null)
  const [showQuickAnalyze, setShowQuickAnalyze] = useState(false)
  const [quickAnalyzePatentIds, setQuickAnalyzePatentIds] = useState<number[]>([])
  const [quickAnalyzeInputFields, setQuickAnalyzeInputFields] = useState<string[]>([])
  const [showInsertAIColumn, setShowInsertAIColumn] = useState(false)
  const [insertColType, setInsertColType] = useState<'text' | 'longtext' | 'number' | 'date' | 'select' | 'boolean' | 'attachment'>('text')
  const [insertAnchorFieldKey, setInsertAnchorFieldKey] = useState<string | null>(null)
  const [insertSide, setInsertSide] = useState<'before' | 'after'>('after')
  const [insertColFrozen, setInsertColFrozen] = useState(false)
  const [newAIColumnName, setNewAIColumnName] = useState('')
  const [newColumnOptions, setNewColumnOptions] = useState('')
  const [creatingAIColumn, setCreatingAIColumn] = useState(false)
  const [frozenFields, setFrozenFields] = useState<Set<string>>(new Set())
  const [showColumnStats, setShowColumnStats] = useState(false)
  const [statsFieldKey, setStatsFieldKey] = useState('')
  const [statsData, setStatsData] = useState<{ value: string; count: number; percentage: number }[]>([])
  const [statsLoading, setStatsLoading] = useState(false)
  const [showStatsToTags, setShowStatsToTags] = useState(false)
  const [tagGroupName, setTagGroupName] = useState('自动分类')
  const [autoApplyTags, setAutoApplyTags] = useState(true)
  const [convertingTags, setConvertingTags] = useState(false)
  const [bulkModule, setBulkModule] = useState('')
  const [bulkRiskLevel, setBulkRiskLevel] = useState('')
  const [bulkCategory, setBulkCategory] = useState('')
  const [bulkLegalStatus, setBulkLegalStatus] = useState('')
  const [bulkCountry, setBulkCountry] = useState('')
  const [bulkApplicant, setBulkApplicant] = useState('')
  const [bulkFieldKey, setBulkFieldKey] = useState('')
  const [bulkFieldValue, setBulkFieldValue] = useState('')
  // 批量打标签
  const [tagsList, setTagsList] = useState<Tag[]>([])
  const [bulkTagIds, setBulkTagIds] = useState<number[]>([])
  const [bulkTagMode, setBulkTagMode] = useState<'add' | 'remove' | 'replace'>('add')
  const [bulkTagLoading, setBulkTagLoading] = useState(false)
  const [filterValues, setFilterValues] = useState<FilterState>(() => readFilterParam(searchParams))
  const [customFields, setCustomFields] = useState<CustomField[]>([])
  const [relationData, setRelationData] = useState<Record<string, Record<number, RelationCellData>>>({})
  const [pageInputValue, setPageInputValue] = useState('')
  const [aiProcessingRow, setAiProcessingRow] = useState<number | null>(null)
  // AI 任务透明化：跟踪所有运行中的任务
  const [activeAITasks, setActiveAITasks] = useState<AITask[]>([])
  const [aiPanelOpen, setAiPanelOpen] = useState(true)
  // 任务 → 触发时记录的元信息（field name、prompt、引用列、输出位置）
  const [taskMeta, setTaskMeta] = useState<Record<number, {
    fieldName: string
    fieldKey: string
    prompt: string
    referencedColumns: string[]
    outputLocation: string
    targetCount: number
  }>>({})
  // 最近完成的任务（保留几秒用于显示成功提示）
  const [recentCompleted, setRecentCompleted] = useState<{ taskId: number; meta: typeof taskMeta[number] | undefined; task: AITask | undefined } | null>(null)
  // 右键上下文菜单
  const [contextMenu, setContextMenu] = useState<{
    x: number
    y: number
    type: 'row' | 'header'
    patentId?: number
    fieldKey?: string
  } | null>(null)
  const [groupedGroups, setGroupedGroups] = useState<ViewGroup[]>([])
  const [collapsedGroupKeys, setCollapsedGroupKeys] = useState<Set<string>>(new Set())
  const [collapsedFamilyKeys, setCollapsedFamilyKeys] = useState<Set<string>>(new Set())
  const [showGroupConfig, setShowGroupConfig] = useState(false)
  const [showConditionalConfig, setShowConditionalConfig] = useState(false)
  const [showExportDialog, setShowExportDialog] = useState(false)
  const [showWorkFileDialog, setShowWorkFileDialog] = useState(false)

  // 用于丢弃快速翻页/切库时旧请求的响应：每次发起 loadPatents 自增，
  // 返回时若 ID 不等于最新值，说明已有更新请求在路上，直接丢弃结果。
  const loadPatentsRequestId = useRef(0)
  const patentsRef = useRef(patents)
  const totalPatentsRef = useRef(totalPatents)
  const continuousPageRef = useRef(1)
  const continuousLoadingRef = useRef(false)
  const continuousHasMoreRef = useRef(true)
  const tableWrapperRef = useRef<HTMLDivElement>(null)
  const tableToolsRef = useRef<HTMLDivElement>(null)
  const restoredScopeRef = useRef<string | null>(null)
  const [activeCell, setActiveCell] = useState<{ patentId: number; fieldKey: string } | null>(null)

  const tableScopeKey = `${TABLE_POSITION_STORAGE_PREFIX}${JSON.stringify({
    databaseId: activeDatabaseId ?? null,
    viewId: viewId ?? null,
    productId: currentProductId ?? null,
    search: searchText.trim(),
    filters: filterValues,
    sortField,
    sortOrder,
    groupByFamily,
    mode: tableViewMode,
    page: tableViewMode === 'pagination' ? page : null,
  })}`

  const readTablePosition = useCallback((): TablePositionSnapshot | null => {
    try {
      const raw = sessionStorage.getItem(tableScopeKey)
      if (!raw) return null
      const parsed = JSON.parse(raw) as Partial<TablePositionSnapshot>
      if (!Number.isFinite(parsed.scrollTop) || !Number.isFinite(parsed.continuousPage)) return null
      return {
        page: Number.isInteger(parsed.page) && (parsed.page as number) > 0 ? parsed.page as number : 1,
        continuousPage: Math.max(1, Math.floor(parsed.continuousPage as number)),
        scrollTop: Math.max(0, parsed.scrollTop as number),
        scrollLeft: Math.max(0, Number(parsed.scrollLeft) || 0),
        savedAt: Number(parsed.savedAt) || 0,
      }
    } catch {
      return null
    }
  }, [tableScopeKey])

  const saveTablePosition = useCallback(() => {
    const element = tableWrapperRef.current
    if (!element) return
    const snapshot: TablePositionSnapshot = {
      page,
      continuousPage: continuousPageRef.current,
      scrollTop: element.scrollTop,
      scrollLeft: element.scrollLeft,
      savedAt: Date.now(),
    }
    try { sessionStorage.setItem(tableScopeKey, JSON.stringify(snapshot)) } catch { /* session storage is optional */ }
  }, [page, tableScopeKey])

  const openPatent = useCallback((patentId: number) => {
    saveTablePosition()
    onPatentClick(patentId)
  }, [onPatentClick, saveTablePosition])

  const openContextPatent = useCallback(() => {
    const patentId = contextMenu?.patentId
    if (patentId) openPatent(patentId)
    setContextMenu(null)
  }, [contextMenu?.patentId, openPatent])

  useEffect(() => {
    patentsRef.current = patents
  }, [patents])

  useEffect(() => {
    totalPatentsRef.current = totalPatents
  }, [totalPatents])

  const handleTableViewModeChange = (mode: TableViewMode) => {
    try { localStorage.setItem(TABLE_VIEW_MODE_STORAGE_KEY, mode) } catch { /* storage is optional */ }
    continuousPageRef.current = 1
    continuousHasMoreRef.current = true
    continuousLoadingRef.current = false
    restoredScopeRef.current = null
    setContinuousLoading(false)
    setPage(1)
    setTableViewMode(mode)
  }

  const handleRowHeightLimitChange = (limit: RowHeightLimit) => {
    try { localStorage.setItem(ROW_HEIGHT_LIMIT_STORAGE_KEY, String(limit)) } catch { /* storage is optional */ }
    setRowHeightLimit(limit)
  }

  const loadRelationData = useCallback(async () => {
    const relationFields = fields.filter(field => ['link', 'lookup', 'rollup'].includes(field.field_type))
    const recordIds = patents.map(patent => patent.id)
    if (relationFields.length === 0 || recordIds.length === 0) {
      setRelationData({})
      return
    }
    const entries = await Promise.all(relationFields.map(async field => {
      try {
        const result = await linkApi.batch(field.key, recordIds)
        const byRecord: Record<number, RelationCellData> = {}
        result.forEach(item => {
          byRecord[item.record_id] = {
            links: item.links,
            value: item.value,
            aggregation: item.aggregation,
          }
        })
        return [field.key, byRecord] as const
      } catch (error: unknown) {
        console.error(`Failed to load relation field ${field.key}:`, error)
        return [field.key, {}] as const
      }
    }))
    setRelationData(Object.fromEntries(entries))
  }, [fields, patents])

  useEffect(() => {
    // Relation values are loaded from the API when the visible records change.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    void loadRelationData()
  }, [loadRelationData])

  const loadFields = useCallback(async (refresh = false) => {
    try {
      const fieldsData = await fieldApi.list(refresh)
      // 保存视图有独立的字段投影；只有未进入视图时才应用旧的浏览器级配置。
      // 这样一个视图隐藏字段不会影响其他视图，也不会把字段状态写回主数据。
      if (viewId === null) {
        try {
          const hiddenRaw = localStorage.getItem('patwiki_hidden_fields')
          if (hiddenRaw) {
            const hiddenKeys: string[] = JSON.parse(hiddenRaw)
            fieldsData.forEach(f => {
              if (hiddenKeys.includes(f.key)) f.visible = false
            })
          }
        } catch (error) { console.error('Failed to read hidden fields:', error) }
      }
      setFields(fieldsData)
      try {
        const savedOrder = JSON.parse(localStorage.getItem('patwiki_field_order') || '[]') as unknown
        if (Array.isArray(savedOrder)) {
          const orderMap = new Map(savedOrder.map((key, index) => [String(key), index]))
          fieldsData.sort((a, b) => (orderMap.get(a.key) ?? Number.MAX_SAFE_INTEGER) - (orderMap.get(b.key) ?? Number.MAX_SAFE_INTEGER))
          setFields([...fieldsData])
        }
      } catch { /* column order is optional */ }
      try {
        const savedFrozen = JSON.parse(localStorage.getItem('patwiki_frozen_fields') || 'null') as unknown
        const frozen = Array.isArray(savedFrozen) ? savedFrozen.map(String) : []
        setFrozenFields(new Set(frozen))
      } catch {
        setFrozenFields(new Set())
      }
      const widths: Record<string, number> = {}
      fieldsData.forEach(f => {
        widths[f.key] = f.width || DEFAULT_COLUMN_WIDTH
      })
      if (viewId === null) {
        try {
          const saved = JSON.parse(localStorage.getItem('patwiki_column_widths') || '{}') as Record<string, unknown>
          Object.entries(saved).forEach(([key, value]) => {
            if (typeof value === 'number' && value >= 80 && value <= 1200 && key in widths) widths[key] = value
          })
        } catch (error) { console.error('Failed to read column widths:', error) }
      }
      setColumnWidths(widths)
    } catch (e) {
      console.error('Failed to load fields:', e)
    }
  }, [viewId])

  const loadCustomFields = useCallback(async () => {
    try {
      const cf = await customFieldApi.list()
      setCustomFields(cf)
    } catch (e) {
      console.error('Failed to load custom fields:', e)
    }
  }, [])

  const loadPatents = useCallback(async (
    requestedPage = tableViewMode === 'continuous' ? 1 : page,
    append = false,
    requestedPageSize = pageSize,
    preserveVisible = false,
  ): Promise<boolean> => {
    const myRequestId = ++loadPatentsRequestId.current
    const effectivePage = requestedPage
    if (!append) {
      if (!preserveVisible) setLoading(true)
      if (!preserveVisible) patentsRef.current = []
      if (!preserveVisible) {
        continuousPageRef.current = effectivePage
        continuousHasMoreRef.current = true
        if (tableViewMode === 'continuous') tableWrapperRef.current?.scrollTo({ top: 0 })
      }
    }
    const applyItems = (items: Patent[], total: number) => {
      totalPatentsRef.current = total
      if (!append && !preserveVisible) {
        patentsRef.current = items
        setPatents(items, total)
        saveTableDataSnapshot(tableScopeKey, {
          items,
          total,
          continuousPage: continuousPageRef.current,
          hasMore: items.length < total,
          savedAt: Date.now(),
        })
        return
      }
      const merged = Array.from(new Map([...patentsRef.current, ...items].map(item => [item.id, item])).values())
      patentsRef.current = merged
      setPatents(merged, total)
      saveTableDataSnapshot(tableScopeKey, {
        items: merged,
        total,
        continuousPage: continuousPageRef.current,
        hasMore: merged.length < total,
        savedAt: Date.now(),
      })
    }
    try {
      const viewFilters: JsonObject = {}
      Object.entries(filterValues).forEach(([key, condition]) => {
        if (filterConditionHasValue(condition)) viewFilters[key] = condition as unknown as JsonValue
      })

      // 视图查询路径：仅当 viewId 与当前库匹配时才走视图接口。
      // 若视图尚未加载完成（views 为旧库数据）或 viewId 与当前库不一致，
      // 不再清空表格——而是降级走大表直查，避免“切库/翻页后数据消失”。
      // 这样在 loadViews 异步加载新视图的间隙，用户仍能看到目标库的数据。
      if (viewId !== null) {
        const activeViewForLoad = viewsRef.current.find(view => view.id === viewId)
        const viewMatchesDb = !!activeViewForLoad && activeViewForLoad.database_id === activeDatabaseId
        if (viewMatchesDb) {
          if (activeViewForLoad?.layout_type === 'kanban') {
            setGroupedGroups([])
            setPatents([], 0)
            return true
          }
          const groupFields = getViewGroupFields(activeViewForLoad!)
          if (groupFields.length > 0 && !groupByFamily && !append && tableViewMode === 'pagination') {
            const result = await viewApi.grouped(viewId, {
              page: effectivePage,
              page_size: requestedPageSize,
              search: searchText || undefined,
              sort_by: sortField,
              sort_order: sortOrder,
              group_by_family: groupByFamily,
              extra_filters: viewFilters,
            })
            if (myRequestId !== loadPatentsRequestId.current) return false
            setGroupedGroups(result.groups)
            setCollapsedGroupKeys(new Set(getDefaultCollapsedKeys(result.groups)))
            applyItems(flattenGroups(result.groups), result.total)
            return true
          }
          if (!append) {
            setGroupedGroups([])
            setCollapsedGroupKeys(new Set())
          }
          const result = await viewApi.listPatents(viewId, {
            page: effectivePage,
            page_size: requestedPageSize,
            search: searchText || undefined,
            sort_by: sortField,
            sort_order: sortOrder,
            group_by_family: groupByFamily,
            extra_filters: viewFilters,
          })
          if (myRequestId !== loadPatentsRequestId.current) return false
          applyItems(result.items as Patent[], result.total)
          return true
        }
        // 视图不匹配：降级到大表直查，避免数据消失
      }

      const params: JsonObject = {
        page: effectivePage,
        page_size: requestedPageSize,
        sort_by: sortField,
        sort_order: sortOrder,
      }
      if (searchText) params.search = searchText
      if (activeDatabaseId !== null && activeDatabaseId !== undefined) {
        params.database_id = activeDatabaseId
      }
      if (currentProductId) params.product_id = currentProductId
      // P2-8：大表直查（无产品筛选）时透传同族聚拢开关
      if (groupByFamily) {
        params.group_by_family = true
      }

      const allFilters: JsonObject = {}
      Object.entries(filterValues).forEach(([key, condition]) => {
        if (filterConditionHasValue(condition)) allFilters[key] = condition as unknown as JsonValue
      })
      if (Object.keys(allFilters).length > 0) {
        params.filters = JSON.stringify(allFilters)
      }

      const result = await patentApi.list(params)
      if (myRequestId !== loadPatentsRequestId.current) return false
      applyItems(result.items, result.total)
      return true
    } catch (e) {
      if (myRequestId !== loadPatentsRequestId.current) return false
      console.error('Failed to load patents:', e)
      return false
    } finally {
      if (myRequestId === loadPatentsRequestId.current) setLoading(false)
    }
  }, [page, pageSize, searchText, currentProductId, activeDatabaseId, sortField, sortOrder, filterValues, groupByFamily, tableViewMode, viewId, tableScopeKey, setPatents, setLoading])

  const loadNextContinuousPage = useCallback(() => {
    if (tableViewMode !== 'continuous' || continuousLoadingRef.current || !continuousHasMoreRef.current) return
    const total = totalPatentsRef.current
    if (total <= 0 || patentsRef.current.length >= total) {
      continuousHasMoreRef.current = false
      return
    }

    const nextPage = continuousPageRef.current + 1
    continuousLoadingRef.current = true
    setContinuousLoading(true)
    void loadPatents(nextPage, true).then(success => {
      if (success) {
        continuousPageRef.current = nextPage
        continuousHasMoreRef.current = patentsRef.current.length < totalPatentsRef.current
      } else {
        continuousHasMoreRef.current = false
      }
    }).finally(() => {
      continuousLoadingRef.current = false
      setContinuousLoading(false)
    })
  }, [loadPatents, tableViewMode])

  const handleTableScroll = (event: React.UIEvent<HTMLDivElement>) => {
    setActiveHeaderMenu(null)
    const element = event.currentTarget
    try {
      sessionStorage.setItem(tableScopeKey, JSON.stringify({
        page,
        continuousPage: continuousPageRef.current,
        scrollTop: element.scrollTop,
        scrollLeft: element.scrollLeft,
        savedAt: Date.now(),
      } satisfies TablePositionSnapshot))
    } catch { /* session storage is optional */ }
    if (tableViewMode !== 'continuous') return
    const remaining = element.scrollHeight - element.scrollTop - element.clientHeight
    if (remaining < 320) loadNextContinuousPage()
  }

  const restoreContinuousPosition = useCallback(async (snapshot: TablePositionSnapshot | null) => {
    const targetPage = Math.max(1, Math.min(snapshot?.continuousPage || 1, 2000))
    const targetRowCount = targetPage * pageSize
    const chunkSize = 1000
    // The API caps one response at 1,000 rows. Replay in bounded chunks so
    // returning from a deep detail view never silently stops at the first
    // 1,000 filtered records.
    const firstPageSize = Math.min(targetRowCount, chunkSize)
    const firstPageLoaded = await loadPatents(1, false, firstPageSize)
    if (!firstPageLoaded) return
    let nextBackendPage = 2
    let previousLoadedCount = patentsRef.current.length
    while (patentsRef.current.length < targetRowCount && nextBackendPage <= 2000) {
      const loaded = await loadPatents(nextBackendPage, true, chunkSize)
      if (!loaded || patentsRef.current.length <= previousLoadedCount) break
      previousLoadedCount = patentsRef.current.length
      nextBackendPage += 1
    }
    continuousPageRef.current = Math.max(1, Math.ceil(patentsRef.current.length / pageSize))
    continuousHasMoreRef.current = patentsRef.current.length < totalPatentsRef.current
    if (snapshot) {
      window.requestAnimationFrame(() => {
        const element = tableWrapperRef.current
        if (!element) return
        element.scrollLeft = snapshot.scrollLeft
        element.scrollTop = snapshot.scrollTop
      })
    }
  }, [loadPatents, pageSize])

  // Browser back/forward rehydrates list state from the URL.
  useEffect(() => {
    const params = new URLSearchParams(searchParamsString)
    const urlProductId = Number(params.get('product'))
    if (params.has('product') && Number.isInteger(urlProductId) && urlProductId > 0 && urlProductId !== currentProductId) {
      setCurrentProductId(urlProductId)
    }
    const urlFamily = params.get('family') === '1'
    if (params.has('family') && urlFamily !== groupByFamily) setGroupByFamily(urlFamily)
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setPage(readPageParam(params))
    setSearchText(params.get('q') || '')
    setSearchInputText(params.get('q') || '')
    setSortField(params.get('sort') || 'filing_date')
    setSortOrder(params.get('order') === 'asc' ? 'asc' : 'desc')
    setFilterValues(readFilterParam(params))
  }, [currentProductId, groupByFamily, searchParamsString, setCurrentProductId, setGroupByFamily])

  useEffect(() => {
    const next = new URLSearchParams(searchParams)
    const setOrDelete = (key: string, value: string | null) => {
      if (value) next.set(key, value)
      else next.delete(key)
    }
    setOrDelete('db', activeDatabaseId === null ? null : String(activeDatabaseId))
    setOrDelete('view', viewId === null ? null : String(viewId))
    setOrDelete('product', currentProductId === null ? null : String(currentProductId))
    setOrDelete('q', searchText.trim() || null)
    setOrDelete('page', page > 1 ? String(page) : null)
    setOrDelete('sort', sortField !== 'filing_date' ? sortField : null)
    setOrDelete('order', sortOrder !== 'desc' ? sortOrder : null)
    setOrDelete('family', groupByFamily ? '1' : null)
    setOrDelete('filters', Object.keys(filterValues).length > 0 ? JSON.stringify(filterValues) : null)
    if (next.toString() !== searchParamsString) setSearchParams(next, { replace: true })
  }, [activeDatabaseId, currentProductId, filterValues, groupByFamily, page, searchParams, searchParamsString, searchText, setSearchParams, sortField, sortOrder, viewId])

  const saveViewColumnConfig = useCallback(async (columnConfig: ViewColumnConfig[]) => {
    if (!activeView) return
    const updated = await viewApi.update(activeView.id, { column_config: columnConfig })
    const nextViews = viewsRef.current.map(view => view.id === updated.id ? updated : view)
    viewsRef.current = nextViews
    setViews(nextViews)
    const widths: Record<string, number> = {}
    columnConfig.forEach(column => {
      if (column.width) widths[column.key] = column.width
    })
    setColumnWidths(previous => ({ ...previous, ...widths }))
    setViewConfigNotice('当前视图列配置已保存')
    window.setTimeout(() => setViewConfigNotice(''), 3000)
    await loadPatents()
  }, [activeView, loadPatents, setViews])

  useEffect(() => {
    if (!activeView?.column_config) return
    const configuredWidths: Record<string, number> = {}
    activeView.column_config.forEach(column => {
      if (column.width) configuredWidths[column.key] = column.width
    })
    // View configuration is external state loaded asynchronously after the field registry.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setColumnWidths(previous => ({ ...previous, ...configuredWidths }))
  }, [activeView])

  useEffect(() => {
    // Field metadata is loaded asynchronously when the page mounts.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    void loadFields()
    void loadCustomFields()
  }, [loadFields, loadCustomFields])

  useEffect(() => {
    // Imports and field-management changes alter the column registry. Reload it
    // before the refreshed records render so mapped fields appear in the grid.
    if (dataVersion > 0) {
      // The registry refresh is an external synchronization triggered by import/field changes.
      // eslint-disable-next-line react-hooks/set-state-in-effect
      void loadFields(true)
      void loadCustomFields()
    }
  }, [dataVersion, loadCustomFields, loadFields])

  // 打开批量打标签弹窗时加载标签列表
  useEffect(() => {
    if (!showBulkTag) return
    if (tagsList.length > 0) return
    // Loading state begins an asynchronous request and is intentionally local to this effect.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setBulkTagLoading(true)
    tagApi.list().then(setTagsList).catch(console.error).finally(() => setBulkTagLoading(false))
  }, [showBulkTag, tagsList.length])

  useEffect(() => {
    if (fields.length > 0) {
      const cached = tableDataCache.get(tableScopeKey)
      const position = readTablePosition()
      if (cached) {
        patentsRef.current = cached.items
        totalPatentsRef.current = cached.total
        continuousPageRef.current = cached.continuousPage
        continuousHasMoreRef.current = cached.hasMore
        restoredScopeRef.current = tableScopeKey
        // The store update is intentionally synchronous with the cache hit so
        // the table never flashes an empty loading state after detail->back.
        setPatents(cached.items, cached.total)
        window.requestAnimationFrame(() => {
          const element = tableWrapperRef.current
          if (!element || !position) return
          element.scrollLeft = position.scrollLeft
          element.scrollTop = position.scrollTop
        })
        // Refresh only the loaded window and keep cached rows visible while it
        // is in flight. A fresh cache is already the latest list response.
        if (tableViewMode === 'pagination' && Date.now() - cached.savedAt > 15000) {
          window.setTimeout(() => {
            void loadPatents(
              page,
              false,
              Math.min(cached.items.length || pageSize, 1000),
              true,
            )
          }, 0)
        }
        return
      }
      if (tableViewMode === 'continuous') {
        if (restoredScopeRef.current === tableScopeKey) return
        restoredScopeRef.current = tableScopeKey
        // Restore the loaded page count before restoring scrollTop. This keeps
        // the same filtered rows available when returning from a detail page.
        void restoreContinuousPosition(readTablePosition())
        return
      }
      const snapshot = position
      // Loading the external table source also updates the loading and patent stores.
      // eslint-disable-next-line react-hooks/set-state-in-effect
      void loadPatents(page, false).then(success => {
        if (!success || !snapshot) return
        window.requestAnimationFrame(() => {
          const element = tableWrapperRef.current
          if (!element) return
          element.scrollLeft = snapshot.scrollLeft
          element.scrollTop = snapshot.scrollTop
        })
      })
    }
  }, [fields.length, loadPatents, page, pageSize, readTablePosition, restoreContinuousPosition, setPatents, tableScopeKey, tableViewMode])

  useEffect(() => {
    // Reset selection and pagination when the active data scope changes.
    clearSelection()
    // The history belongs to the active database/view scope.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setUndoStack([])
    setRedoStack([])
    setPage(1)
    restoredScopeRef.current = null
    setActiveCell(null)
  }, [viewId, activeDatabaseId, clearSelection])

  useEffect(() => {
    // Keep the input display in sync with pagination state.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setPageInputValue(String(page))
  }, [page])

  useEffect(() => {
    const query = searchInputText.trim()
    if (query.length < 2) return

    let cancelled = false
    const timer = window.setTimeout(() => {
      void searchApi.suggest(query, activeDatabaseId).then(items => {
        if (!cancelled) {
          setSearchSuggestions(items)
          setActiveSuggestionIndex(-1)
        }
      }).catch(error => {
        if (!cancelled) {
          console.error('Failed to load search suggestions:', error)
          setSearchSuggestions([])
        }
      })
    }, 220)

    return () => {
      cancelled = true
      window.clearTimeout(timer)
    }
  }, [activeDatabaseId, searchInputText])

  useEffect(() => {
    const handlePointerMove = (e: PointerEvent) => {
      if (resizing) {
        const diff = e.clientX - resizing.startX
        const newWidth = Math.max(80, resizing.startWidth + diff)
        setColumnWidths(prev => ({ ...prev, [resizing.fieldKey]: newWidth }))
      }
    }
    const handlePointerUp = () => {
      if (resizing) {
        setColumnWidths(widths => {
          if (activeView) {
            const configured = activeView.column_config || []
            const nextConfig: ViewColumnConfig[] = (configured.length > 0 ? configured : fields.map((field, order) => ({
              key: field.key,
              visible: field.visible !== false,
              width: field.width || DEFAULT_COLUMN_WIDTH,
              order,
            }))).map(column => ({
              ...column,
              width: widths[column.key] || column.width || DEFAULT_COLUMN_WIDTH,
            }))
            void saveViewColumnConfig(nextConfig)
          } else {
            try { localStorage.setItem('patwiki_column_widths', JSON.stringify(widths)) } catch (error) { console.error('Failed to save column widths:', error) }
          }
          return widths
        })
      }
      setResizing(null)
    }
    if (resizing) {
      document.addEventListener('pointermove', handlePointerMove)
      document.addEventListener('pointerup', handlePointerUp)
      document.addEventListener('pointercancel', handlePointerUp)
      document.body.style.cursor = 'col-resize'
      document.body.style.userSelect = 'none'
    }
    return () => {
      document.removeEventListener('pointermove', handlePointerMove)
      document.removeEventListener('pointerup', handlePointerUp)
      document.removeEventListener('pointercancel', handlePointerUp)
      document.body.style.cursor = ''
      document.body.style.userSelect = ''
    }
  }, [activeView, fields, resizing, saveViewColumnConfig])

  useEffect(() => {
    const handleClickOutside = (e: MouseEvent) => {
      if (activeHeaderMenu) {
        const target = e.target as HTMLElement
        if (!target.closest('.col-header-menu') && !target.closest('.col-header-trigger')) {
          setActiveHeaderMenu(null)
          setHeaderFilterText('')
        }
      }
    }
    document.addEventListener('click', handleClickOutside)
    return () => document.removeEventListener('click', handleClickOutside)
  }, [activeHeaderMenu])

  useEffect(() => {
    if (!showTableTools) return
    const handleClickOutside = (event: MouseEvent) => {
      if (!tableToolsRef.current?.contains(event.target as Node)) setShowTableTools(false)
    }
    document.addEventListener('click', handleClickOutside)
    return () => document.removeEventListener('click', handleClickOutside)
  }, [showTableTools])

  // 右键菜单：点击其他位置或按 Esc 关闭
  useEffect(() => {
    if (!contextMenu) return
    const close = () => setContextMenu(null)
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') close() }
    const onClick = (e: MouseEvent) => {
      const target = e.target as HTMLElement
      if (!target.closest('.context-menu')) close()
    }
    document.addEventListener('click', onClick)
    const onContextMenu = (e: MouseEvent) => {
      // 在菜单已打开时，右键其他位置应直接切换菜单位置而不是叠加
      const target = e.target as HTMLElement
      if (!target.closest('.context-menu')) {
        // 让目标元素的 onContextMenu 重新接管
        close()
      }
    }
    document.addEventListener('contextmenu', onContextMenu)
    document.addEventListener('keydown', onKey)
    return () => {
      document.removeEventListener('click', onClick)
      document.removeEventListener('contextmenu', onContextMenu)
      document.removeEventListener('keydown', onKey)
    }
  }, [contextMenu])

  const handleSearch = (e: React.FormEvent) => {
    e.preventDefault()
    setSearchText(searchInputText)
    setSearchSuggestions([])
    setActiveSuggestionIndex(-1)
    setPage(1)
  }

  const handleSearchInputChange = (value: string) => {
    setSearchInputText(value)
    setSearchSuggestions([])
    setActiveSuggestionIndex(-1)
  }

  const applySearchSuggestion = (suggestion: SearchSuggestion) => {
    setSearchInputText(suggestion.value)
    setSearchText(suggestion.value)
    setSearchSuggestions([])
    setActiveSuggestionIndex(-1)
    setPage(1)
  }

  const handleSearchKeyDown = (event: React.KeyboardEvent<HTMLInputElement>) => {
    if (event.key === 'Escape') {
      setSearchSuggestions([])
      setActiveSuggestionIndex(-1)
      return
    }
    if (searchSuggestions.length === 0) return
    if (event.key === 'ArrowDown') {
      event.preventDefault()
      setActiveSuggestionIndex(index => (index + 1) % searchSuggestions.length)
    } else if (event.key === 'ArrowUp') {
      event.preventDefault()
      setActiveSuggestionIndex(index => index <= 0 ? searchSuggestions.length - 1 : index - 1)
    } else if (event.key === 'Enter' && activeSuggestionIndex >= 0) {
      event.preventDefault()
      applySearchSuggestion(searchSuggestions[activeSuggestionIndex])
    }
  }

  const handleExport = () => setShowExportDialog(true)

  const handleFamilyGrouping = async () => {
    const nextValue = !groupByFamily
    setShowTableTools(false)
    if (nextValue && activeDatabaseId) {
      try {
        const result = await patentApi.rebuildFamilies(activeDatabaseId)
        setViewConfigNotice(`已重建 ${result.family_count} 个同族组，覆盖 ${result.grouped_patent_count} 件专利`)
      } catch (error: unknown) {
        setViewConfigNotice(getErrorMessage(error, '同族关系重建失败'))
      }
    }
    setGroupByFamily(nextValue)
    setPage(1)
  }

  // 批量删除选中的专利
  const handleBulkDelete = async () => {
    if (selectedIds.length === 0) return
    if (!confirm(`确定要删除选中的 ${selectedIds.length} 条专利吗？此操作不可恢复！`)) return
    try {
      const result = await patentApi.bulkDelete(selectedIds)
      alert(`已删除 ${result.deleted_count} 条专利`)
      clearSelection()
      setPage(1)
      loadPatents()
    } catch (error: unknown) {
      alert(getErrorMessage(error, '删除失败'))
    }
  }

  const openBulkTransfer = (action: BulkTransferAction) => {
    setBulkTransferAction(action)
    setBulkTargetDatabaseId(action === 'duplicate' ? activeDatabaseId ?? null : null)
    setBulkTargetViewId(null)
  }

  const handleBulkTransfer = async () => {
    if (!bulkTransferAction || selectedIds.length === 0) return
    if (activeDatabaseId == null || !Number.isInteger(activeDatabaseId) || activeDatabaseId <= 0) {
      alert('当前没有明确的数据库范围，批量操作已取消')
      return
    }
    const sourceDatabaseId = activeDatabaseId
    try {
      if (bulkTransferAction === 'move_database') {
        if (bulkTargetDatabaseId == null) {
          alert('请选择目标数据库')
          return
        }
        const result = await patentApi.bulkMoveDatabase(selectedIds, bulkTargetDatabaseId, {
          sourceDatabaseId,
          sourceViewId: viewId ?? null,
        })
        alert(`已移库 ${result.moved_count} 条专利`)
      } else if (bulkTransferAction === 'move_view') {
        const result = await patentApi.bulkMoveView(selectedIds, bulkTargetViewId, {
          sourceDatabaseId,
          sourceViewId: viewId ?? null,
        })
        alert(result.target_view_id == null ? `已将 ${result.moved_count} 条专利移回库主表` : `已移动 ${result.moved_count} 条专利到目标视图`)
      } else {
        const options = bulkTargetDatabaseId == null ? {} : { target_database_id: bulkTargetDatabaseId }
        const result = await patentApi.bulkDuplicate(selectedIds, options)
        alert(`已创建 ${result.created_count} 条工作副本。副本不带官方号码，不会与原专利混淆。`)
      }
      setBulkTransferAction(null)
      clearSelection()
      await loadPatents()
    } catch (error: unknown) {
      alert('批量操作失败: ' + getErrorMessage(error))
    }
  }

  const handleSelectAll = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.checked) {
      setSelectedIds(patents.map(p => p.id))
    } else {
      clearSelection()
    }
  }

  const handleSort = (fieldKey: string) => {
    const field = fields.find(f => f.key === fieldKey)
    if (!field?.sortable) return
    if (sortField === fieldKey) {
      setSortOrder(prev => prev === 'asc' ? 'desc' : 'asc')
    } else {
      setSortField(fieldKey)
      setSortOrder('desc')
    }
    setActiveHeaderMenu(null)
  }

  const handleCellClick = (patentId: number, fieldKey: string, e: React.MouseEvent) => {
    if ((e.target as HTMLElement).closest('.cell-action-btn')) return
    const field = fields.find(f => f.key === fieldKey)
    if (!field?.editable || field.field_type === 'lookup' || field.field_type === 'rollup') {
      openPatent(patentId)
      return
    }
    if ((e.target as HTMLElement).tagName === 'INPUT' || (e.target as HTMLElement).tagName === 'SELECT') {
      return
    }
    setEditingCell({ patentId, fieldKey })
  }

  const handlePatentReferenceClick = useCallback(async (publicationNumber: string) => {
    try {
      const result = await patentApi.resolvePublicationNumber(publicationNumber)
      if (result.found && result.patent_id) {
        openPatent(result.patent_id)
        return
      }
      alert(`库中未找到公开号 ${publicationNumber}`)
    } catch (error: unknown) {
      alert('解析专利公开号失败: ' + getErrorMessage(error))
    }
  }, [openPatent])

  const handleCellSave = async (patentId: number, fieldKey: string, value: JsonValue) => {
    const before = getFieldValue(patents.find(patent => patent.id === patentId) || ({} as Patent), fieldKey)
    try {
      if (viewId !== null) {
        await viewApi.updateSharedField(viewId, patentId, fieldKey, value)
      } else {
        await patentApi.updateCell(patentId, fieldKey, value)
      }
      setEditingCell(null)
      if (JSON.stringify(before) !== JSON.stringify(value)) {
        setUndoStack(prev => [...prev.slice(-49), { patentId, fieldKey, before, after: value }])
        setRedoStack([])
      }
      loadPatents()
    } catch (error: unknown) {
      alert('保存失败: ' + getErrorMessage(error))
    }
  }

  const handleToggleFieldVisible = (fieldKey: string) => {
    if (activeView) {
      const next = buildViewColumnConfig(activeView, fields).map(column =>
        column.key === fieldKey ? { ...column, visible: column.visible === false } : column,
      )
      void saveViewColumnConfig(next).catch(error => alert('视图列配置保存失败: ' + getErrorMessage(error)))
      setActiveHeaderMenu(null)
      return
    }
    setFields(prev => {
      const next = prev.map(f =>
        f.key === fieldKey ? { ...f, visible: f.visible === false } : f
      )
      // localStorage 持久化
      try {
        const hidden = next.filter(f => f.visible === false).map(f => f.key)
        localStorage.setItem('patwiki_hidden_fields', JSON.stringify(hidden))
      } catch (error) { console.error('Failed to save hidden fields:', error) }
      return next
    })
    setActiveHeaderMenu(null)
  }

  const handleHeaderFilterApply = (fieldKey: string) => {
    if (headerFilterOperator !== 'is_empty' && headerFilterOperator !== 'is_not_empty' && !headerFilterText.trim()) {
      handleHeaderFilterClear(fieldKey)
      return
    }
    setFilterValues(prev => ({
      ...prev,
      [fieldKey]: {
        operator: headerFilterOperator,
        ...(headerFilterOperator === 'is_empty' || headerFilterOperator === 'is_not_empty'
          ? {}
          : { value: headerFilterText.trim() }),
      },
    }))
    setPage(1)
    setActiveHeaderMenu(null)
    setHeaderFilterText('')
    setHeaderFilterOperator('contains')
  }

  const handleHeaderFilterClear = (fieldKey: string) => {
    setFilterValues(prev => {
      const next = { ...prev }
      delete next[fieldKey]
      return next
    })
    setHeaderFilterText('')
    setHeaderFilterOperator('contains')
    setPage(1)
  }

  const handleClearAllFilters = () => {
    setFilterValues({})
    setSearchText('')
    setSearchInputText('')
    setSearchSuggestions([])
    setActiveSuggestionIndex(-1)
    setPage(1)
  }

  const applyEditCommand = async (command: { patentId: number; fieldKey: string; before: JsonValue; after: JsonValue }, value: JsonValue) => {
    if (viewId !== null) await viewApi.updateSharedField(viewId, command.patentId, command.fieldKey, value)
    else await patentApi.updateCell(command.patentId, command.fieldKey, value)
  }

  const handleUndo = async () => {
    const command = undoStack[undoStack.length - 1]
    if (!command) return
    try {
      await applyEditCommand(command, command.before)
      setUndoStack(prev => prev.slice(0, -1))
      setRedoStack(prev => [...prev, command])
      await loadPatents()
    } catch (error: unknown) { alert('撤回失败: ' + getErrorMessage(error)) }
  }

  const handleRedo = async () => {
    const command = redoStack[redoStack.length - 1]
    if (!command) return
    try {
      await applyEditCommand(command, command.after)
      setRedoStack(prev => prev.slice(0, -1))
      setUndoStack(prev => [...prev, command])
      await loadPatents()
    } catch (error: unknown) { alert('重做失败: ' + getErrorMessage(error)) }
  }

  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      if (!(event.ctrlKey || event.metaKey) || event.key.toLowerCase() !== 'z') return
      if ((event.target as HTMLElement)?.closest('input, textarea, select')) return
      event.preventDefault()
      if (event.shiftKey) void handleRedo()
      else void handleUndo()
    }
    const onRedo = (event: KeyboardEvent) => {
      if (!(event.ctrlKey || event.metaKey) || event.key.toLowerCase() !== 'y') return
      if ((event.target as HTMLElement)?.closest('input, textarea, select')) return
      event.preventDefault()
      void handleRedo()
    }
    document.addEventListener('keydown', onKeyDown)
    document.addEventListener('keydown', onRedo)
    return () => { document.removeEventListener('keydown', onKeyDown); document.removeEventListener('keydown', onRedo) }
  })

  // 轮询所有运行中的 AI 任务
  useEffect(() => {
    if (activeAITasks.length === 0) return
    const interval = setInterval(async () => {
      const stillRunning: AITask[] = []
      const justCompleted: AITask[] = []
      for (const t of activeAITasks) {
        try {
          const latest = await aiApi.getTask(t.id)
          if (latest.status === 'running' || latest.status === 'pending' || latest.status === 'processing') {
            stillRunning.push(latest)
          } else {
            justCompleted.push(latest)
          }
        } catch {
          // 查询失败，保留任务（下次再试）
          stillRunning.push(t)
        }
      }
      setActiveAITasks(stillRunning)
      if (justCompleted.length > 0) {
        // 保留最近完成的任务几秒用于显示
        const lastDone = justCompleted[justCompleted.length - 1]
        setRecentCompleted({ taskId: lastDone.id, meta: taskMeta[lastDone.id], task: lastDone })
        setTimeout(() => setRecentCompleted(null), 5000)
        loadPatents()  // AI 任务完成后立即回填刷新
      }
    }, 1500)
    return () => clearInterval(interval)
  }, [activeAITasks, taskMeta, loadPatents])

  const handleQuickAI = (patentId: number) => {
    // 打开 AI 快速分析弹窗，让用户配置输入列、提示词、抽取目标
    setQuickAnalyzePatentIds([patentId])
    setQuickAnalyzeInputFields([])
    setShowQuickAnalyze(true)
  }

  const handleCellQuickAI = (patentId: number, fieldKey: string) => {
    // Capture both the record and source column at invocation time. Later
    // selection changes in the table must not change an already opened task.
    setQuickAnalyzePatentIds([patentId])
    setQuickAnalyzeInputFields([fieldKey])
    setShowQuickAnalyze(true)
    setContextMenu(null)
  }

  const handleQuickAnalyzeStarted = (task: AITask) => {
    setShowQuickAnalyze(false)
    setActiveAITasks(prev => [...prev, task])
    setTaskMeta(prev => ({
      ...prev,
      [task.id]: {
        fieldName: 'AI 快速分析',
        fieldKey: 'quick_analyze',
        prompt: '按本次快速分析弹窗中的模板、输入列和抽取目标执行',
        referencedColumns: quickAnalyzeInputFields.map(key => fields.find(field => field.key === key)?.name || key),
        outputLocation: '按本次抽取目标回填字段',
        targetCount: task.total_items,
      },
    }))
    setAiPanelOpen(true)
    // 若是单行触发，设置行 loading
    if (quickAnalyzePatentIds.length === 1) {
      setAiProcessingRow(quickAnalyzePatentIds[0])
    }
  }

  // 当没有运行中的任务时，清除行 loading
  useEffect(() => {
    if (activeAITasks.length === 0 && aiProcessingRow !== null) {
      // The task monitor is the external source of truth for this loading state.
      // eslint-disable-next-line react-hooks/set-state-in-effect
      setAiProcessingRow(null)
    }
  }, [activeAITasks.length, aiProcessingRow])

  const handleInsertAIColumn = async () => {
    if (!newAIColumnName.trim()) {
      alert('请输入新列名称')
      return
    }
    if ((insertColType === 'select') && !newColumnOptions.trim()) {
      alert('单选列必须填写候选项（每行一个）')
      return
    }
    setCreatingAIColumn(true)
    try {
      const key = 'cf_' + Date.now().toString(36)
      const payload: Partial<CustomField> = {
        key,
        name: newAIColumnName.trim(),
        field_type: insertColType,
        is_active: true,
        sort_order: fields.length,
      }
      if (insertColType === 'select' && newColumnOptions.trim()) {
        payload.options = newColumnOptions.split('\n').map(s => s.trim()).filter(Boolean)
      }
      const createdField = await customFieldApi.create(payload)
      const createdKey = createdField.key || key
      const insertIntoKeys = (currentKeys: string[]) => {
        const next = currentKeys.filter(item => item !== createdKey)
        const anchorIndex = insertAnchorFieldKey ? next.indexOf(insertAnchorFieldKey) : -1
        const index = anchorIndex < 0 ? next.length : anchorIndex + (insertSide === 'after' ? 1 : 0)
        next.splice(index, 0, createdKey)
        return next
      }

      if (activeView) {
        const currentConfig = buildViewColumnConfig(activeView, fields)
        const currentKeys = currentConfig.map(column => column.key)
        const nextKeys = insertIntoKeys(currentKeys)
        const columnByKey = new Map(currentConfig.map(column => [column.key, column]))
        const nextConfig = nextKeys.map((fieldKey, order) => ({
          ...(columnByKey.get(fieldKey) || { key: fieldKey, visible: true, width: DEFAULT_COLUMN_WIDTH }),
          order,
        }))
        await saveViewColumnConfig(nextConfig)
      }
      // 记录冻结状态
      if (insertColFrozen) {
        setFrozenFields(prev => new Set(prev).add(createdKey))
      }
      await loadFields()
      await loadCustomFields()
      if (!activeView) {
        setFields(current => {
          const nextKeys = insertIntoKeys(current.map(field => field.key))
          const orderMap = new Map(nextKeys.map((fieldKey, index) => [fieldKey, index]))
          try { localStorage.setItem('patwiki_field_order', JSON.stringify(nextKeys)) } catch { /* storage is optional */ }
          return [...current].sort((a, b) => (orderMap.get(a.key) ?? Number.MAX_SAFE_INTEGER) - (orderMap.get(b.key) ?? Number.MAX_SAFE_INTEGER))
        })
      }
      alert(`新列"${newAIColumnName.trim()}"已创建`)
      setShowInsertAIColumn(false)
      setNewAIColumnName('')
      setNewColumnOptions('')
      setInsertColType('text')
      setInsertColFrozen(false)
      loadPatents()
    } catch (error: unknown) {
      alert('创建列失败: ' + getErrorMessage(error))
    } finally {
      setCreatingAIColumn(false)
    }
  }

  const openInsertAIDialog = (
    mode: typeof insertColType = 'text',
    anchorFieldKey: string | null = null,
    side: 'before' | 'after' = 'after',
  ) => {
    setActiveHeaderMenu(null)
    setContextMenu(null)
    setInsertColType(mode)
    setInsertAnchorFieldKey(anchorFieldKey)
    setInsertSide(side)
    setNewAIColumnName('')
    setNewColumnOptions('')
    setShowInsertAIColumn(true)
  }

  const handleReorderFields = (keys: string[]) => {
    const orderMap = new Map(keys.map((key, index) => [key, index]))
    setFields(current => [...current].sort((a, b) => (orderMap.get(a.key) ?? Number.MAX_SAFE_INTEGER) - (orderMap.get(b.key) ?? Number.MAX_SAFE_INTEGER)))
    try { localStorage.setItem('patwiki_field_order', JSON.stringify(keys)) } catch { /* storage is optional */ }
  }

  const handleToggleFreeze = (fieldKey: string) => {
    setActiveHeaderMenu(null)
    setFrozenFields(prev => {
      const next = new Set(prev)
      if (next.has(fieldKey)) {
        next.delete(fieldKey)
      } else {
        next.add(fieldKey)
      }
      try {
        localStorage.setItem('patwiki_frozen_fields', JSON.stringify([...next]))
      } catch (error) { console.error('Failed to save frozen fields:', error) }
      return next
    })
  }

  const openColumnStats = async (fieldKey: string) => {
    setActiveHeaderMenu(null)
    setStatsFieldKey(fieldKey)
    setShowColumnStats(true)
    setStatsLoading(true)
    setStatsData([])
    try {
      const result = await analyticsApi.columnStats({
        field_key: fieldKey,
        database_id: activeDatabaseId ?? undefined,
        product_id: currentProductId || undefined,
      })
      setStatsData(result.items)
    } catch (error: unknown) {
      alert('统计失败: ' + getErrorMessage(error))
    } finally {
      setStatsLoading(false)
    }
  }

  const handleStatsToTags = async () => {
    if (!statsFieldKey) return
    setConvertingTags(true)
    try {
      const result = await analyticsApi.statsToTags({
        field_key: statsFieldKey,
        group_name: tagGroupName.trim() || '自动分类',
        auto_apply_to_patents: autoApplyTags,
        database_id: activeDatabaseId ?? undefined,
        product_id: currentProductId || undefined,
      })
      alert(`已创建标签组"${result.group.name}"，共 ${result.total_tags} 个标签${autoApplyTags ? `，已为 ${result.applied_count} 条专利打标` : ''}`)
      setShowStatsToTags(false)
      setShowColumnStats(false)
    } catch (error: unknown) {
      alert('转换失败: ' + getErrorMessage(error))
    } finally {
      setConvertingTags(false)
    }
  }

  // 从当前表格移除列。列移除只改变视图/浏览器列配置，不删除专利主数据。
  const handleDeleteColumnByKey = async (fieldKey: string) => {
    const field = fields.find(f => f.key === fieldKey)
    if (!field) {
      alert('未找到该列信息')
      return
    }
    const confirmText = `确定要从当前表格移除列"${field.name}"吗？\n\n• 只移除当前表格的显示配置\n• 专利主数据和该列已有内容都会保留\n• 之后可在列管理中重新显示`
    if (!confirm(confirmText)) return
    try {
      if (activeView) {
        const next = buildViewColumnConfig(activeView, fields).map(column =>
          column.key === fieldKey ? { ...column, visible: false } : column,
        )
        await saveViewColumnConfig(next)
      } else {
        setFields(previous => {
          const next = previous.map(item => item.key === fieldKey ? { ...item, visible: false } : item)
          try {
            localStorage.setItem('patwiki_hidden_fields', JSON.stringify(next.filter(item => item.visible === false).map(item => item.key)))
          } catch (error) { console.error('Failed to save hidden fields:', error) }
          return next
        })
      }
      setContextMenu(null)
    } catch (error: unknown) {
      alert('移除列失败: ' + getErrorMessage(error))
    }
  }

  // 删除单行专利
  const handleDeletePatent = async (patentId: number) => {
    const patent = patents.find(p => p.id === patentId)
    if (!patent) return
    const title = patent.title || `#${patentId}`
    const confirmText = `确定要删除专利"${title}"吗？\n\n• 申请号：${patent.application_number || '无'}\n• 公开号：${patent.publication_number || '无'}\n• 此操作不可撤销，删除后数据无法恢复`
    if (!confirm(confirmText)) return
    // 二次确认（防误删）
    if (!confirm('再次确认删除？此操作不可撤销！')) return
    try {
      await patentApi.delete(patentId)
      // 从已选中移除
      if (selectedIds.includes(patentId)) {
        setSelectedIds(selectedIds.filter(id => id !== patentId))
      }
      await loadPatents()
    } catch (error: unknown) {
      alert('删除失败: ' + getErrorMessage(error))
    }
  }

  // 右键菜单触发（行/列）
  const handleContextMenu = (e: React.MouseEvent, type: 'row' | 'header', data: { patentId?: number; fieldKey?: string }) => {
    e.preventDefault()
    e.stopPropagation()
    setContextMenu({
      x: e.clientX,
      y: e.clientY,
      type,
      patentId: data.patentId,
      fieldKey: data.fieldKey,
    })
  }

  // 复制单元格值到剪贴板
  const handleCopyCell = (patentId: number, fieldKey: string) => {
    const patent = patents.find(p => p.id === patentId)
    if (!patent) return
    const value = getFieldValue(patent, fieldKey)
    const text = value === null || value === undefined ? '' : String(value)
    navigator.clipboard?.writeText(text).then(
      () => { /* 复制成功，不弹窗 */ },
      () => { alert('复制失败：' + text) }
    )
  }

  const handleBulkEditSave = async () => {
    const updates: Partial<Patent> = {}
    if (bulkModule) updates.module = bulkModule
    if (bulkRiskLevel) {
      updates.risk_level = bulkRiskLevel
      if (bulkRiskLevel !== 'none') updates.has_risk = true
      else updates.has_risk = false
    }
    if (bulkCategory) updates.category = bulkCategory
    if (bulkLegalStatus) updates.legal_status = bulkLegalStatus
    if (bulkCountry) updates.country = bulkCountry
    if (bulkApplicant) updates.applicant = bulkApplicant
    if (bulkFieldKey) {
      const field = fields.find(item => item.key === bulkFieldKey)
      if (!field) {
        alert('请选择有效字段')
        return
      }
      const typedValue: JsonValue = field.field_type === 'boolean'
        ? bulkFieldValue === 'true'
        : bulkFieldValue
      if (field.is_system) {
        ;(updates as Record<string, JsonValue>)[field.key] = typedValue
      } else {
        updates.custom_fields = { [field.key]: typedValue }
      }
    }
    if (Object.keys(updates).length === 0) {
      alert('请至少填写一个要修改的字段')
      return
    }
    try {
      await patentApi.bulkUpdate(selectedIds, updates)
      alert(`成功更新 ${selectedIds.length} 条专利`)
      setShowBulkEdit(false)
      setBulkModule('')
      setBulkRiskLevel('')
      setBulkCategory('')
      setBulkLegalStatus('')
      setBulkCountry('')
      setBulkApplicant('')
      setBulkFieldKey('')
      setBulkFieldValue('')
      clearSelection()
      loadPatents()
    } catch (error: unknown) {
      alert('批量更新失败: ' + getErrorMessage(error))
    }
  }

  const handleBulkTagSave = async () => {
    if (bulkTagIds.length === 0) {
      alert('请至少选择一个标签')
      return
    }
    try {
      const result = await patentApi.bulkTag(selectedIds, bulkTagIds, bulkTagMode)
      const actionText = bulkTagMode === 'add' ? '添加' : bulkTagMode === 'remove' ? '移除' : '替换'
      alert(`已为 ${result.updated_count} 条专利${actionText}标签`)
      setShowBulkTag(false)
      setBulkTagIds([])
      setBulkTagMode('add')
      clearSelection()
      loadPatents()
    } catch (error: unknown) {
      alert('批量打标签失败: ' + getErrorMessage(error))
    }
  }

  const toggleBulkTagId = (tagId: number) => {
    setBulkTagIds(prev => prev.includes(tagId) ? prev.filter(id => id !== tagId) : [...prev, tagId])
  }

  const handlePageJump = () => {
    const p = parseInt(pageInputValue)
    if (!isNaN(p) && p >= 1 && p <= totalPages) {
      setPage(p)
    } else {
      setPageInputValue(String(page))
    }
  }

  const getFieldValue = (patent: Patent, fieldKey: string): JsonValue => {
    const field = fields.find(f => f.key === fieldKey)
    if (!field) return null
    // 关系原始列是系统注册字段，但实际值保存在 custom_fields，
    // 以保留来源单元格而不把关系实体 ID 写进 Patent 主表。
    if (['family_members', 'cited_patents', 'citing_patents'].includes(fieldKey)) {
      return patent.custom_fields?.[fieldKey] ?? null
    }
    if (field.is_system) {
      return (patent as unknown as Record<string, JsonValue>)[fieldKey] ?? null
    }
    return patent.custom_fields?.[fieldKey] ?? patent.ai_fields?.[fieldKey] ?? null
  }

  const formatValue = (value: JsonValue, field: FieldMeta): string => {
    if (value === null || value === undefined || value === '') return '-'
    if (field.field_type === 'date' && value) {
      return formatApiDate(String(value))
    }
    if (field.field_type === 'boolean') {
      return value ? '是' : '否'
    }
    if (Array.isArray(value)) {
      return value.join(', ')
    }
    return String(value)
  }

  const getStatusText = (status?: string) => {
    const map: Record<string, string> = {
      granted: '授权', examining: '实审中', published: '公开',
      rejected: '驳回', withdrawn: '撤回', deemed_withdrawn: '视撤',
      expired: '终止', abandoned: '放弃', pending: '待审', unknown: '未知',
    }
    return map[status || 'unknown'] || status || '未知'
  }

  const getRiskText = (level?: string, hasRisk?: boolean) => {
    if (!hasRisk) return '-'
    const map: Record<string, string> = {
      critical: '严重', high: '高', medium: '中', low: '低', none: '无',
    }
    return map[level || 'none'] || '-'
  }

  const groupPresentation = groupedGroups.length > 0
    ? getGroupPresentation(groupedGroups, collapsedGroupKeys)
    : null
  const displayPatents = groupPresentation
    ? patents.filter(patent => groupPresentation.visibleIds.has(patent.id) || groupPresentation.headerIds.has(patent.id))
    : patents
  const familyFirstIds = new Set<number>()
  if (groupByFamily) {
    let previousFamilyKey: string | null = null
    displayPatents.forEach(patent => {
      const familyKey = patent.family_id ? `family:${patent.family_id}` : null
      if (familyKey && familyKey !== previousFamilyKey) familyFirstIds.add(patent.id)
      previousFamilyKey = familyKey
    })
  }
  const familyDisplayPatents = displayPatents
  const saveGroupConfig = async (fields: ViewGroupField[]) => {
    if (!activeView) return
    const result = await viewApi.updateGroupConfig(activeView.id, { fields })
    setViews(views.map(view => view.id === activeView.id
      ? { ...view, group_by_config: result.group_by_config }
      : view))
    setPage(1)
  }

  const saveConditionalFormatting = async (rules: ConditionalFormatRule[]) => {
    if (!activeView) return
    const result = await viewApi.updateConditionalFormatting(activeView.id, rules)
    setViews(views.map(view => view.id === activeView.id
      ? { ...view, conditional_formatting: result.conditional_formatting }
      : view))
  }

  const handleViewChange = (updatedView: PatentView) => {
    setViews(views.map(view => view.id === updatedView.id ? updatedView : view))
  }

  const handleKanbanTotalChange = useCallback((total: number) => {
    setPatents([], total)
  }, [setPatents])

  const getConditionalCellStyle = (fieldKey: string, value: JsonValue): React.CSSProperties => {
    const rule = activeView?.conditional_formatting?.find(item => item.field === fieldKey)
    const condition = rule?.conditions?.find(item => {
      const empty = value === null || value === undefined || value === ''
      if (item.op === 'is_empty') return empty
      if (item.op === 'is_not_empty') return !empty
      if (empty) return false
      const expected = item.value
      if (item.op === 'contains') return String(value).toLowerCase().includes(String(expected).toLowerCase())
      if (item.op === 'starts_with') return String(value).toLowerCase().startsWith(String(expected).toLowerCase())
      if (item.op === 'ends_with') return String(value).toLowerCase().endsWith(String(expected).toLowerCase())
      if (['>', '<', '>=', '<='].includes(item.op)) {
        const left = Number(value)
        const right = Number(expected)
        if (Number.isNaN(left) || Number.isNaN(right)) return false
        return item.op === '>' ? left > right : item.op === '<' ? left < right : item.op === '>=' ? left >= right : left <= right
      }
      if (item.op === 'date_within') {
        const actual = parseApiDate(String(value))?.getTime() ?? Number.NaN
        const days = Number(expected)
        const multiplier = item.unit === 'week' ? 7 : item.unit === 'month' ? 30 : 1
        return !Number.isNaN(actual) && !Number.isNaN(days) && actual >= Date.now() && actual <= Date.now() + days * multiplier * 86400000
      }
      if (item.op === 'date_before' || item.op === 'date_after') {
        const actual = parseApiDate(String(value))?.getTime() ?? Number.NaN
        const target = parseApiDate(String(expected))?.getTime() ?? Number.NaN
        return item.op === 'date_before' ? actual < target : actual > target
      }
      return item.op === '!=' ? String(value).toLowerCase() !== String(expected).toLowerCase() : String(value).toLowerCase() === String(expected).toLowerCase()
    })
    const style = condition?.style
    if (!style) return {}
    return {
      backgroundColor: style.bgColor,
      color: style.color,
      fontWeight: style.fontWeight,
      fontStyle: style.fontStyle,
      textDecoration: style.textDecoration,
      opacity: style.opacity,
    }
  }
  const visibleFields = (() => {
    const baseFields = activeView?.column_config?.length ? fields : fields.filter(f => f.visible !== false)
    const columnConfig = activeView?.column_config || []
    if (columnConfig.length === 0) return baseFields

    const configByKey = new Map(columnConfig.map(column => [column.key, column]))
    return baseFields
      // Explicit view configuration is authoritative. Newly imported fields are
      // available in column management but do not silently enter this work table.
      .filter(field => {
        const configuredColumn = configByKey.get(field.key)
        return configuredColumn?.visible === true || (
          configuredColumn === undefined
          && ['family_members', 'cited_patents', 'citing_patents'].includes(field.key)
          && field.visible !== false
        )
      })
      .sort((a, b) => {
        const aOrder = configByKey.get(a.key)?.order ?? Number.MAX_SAFE_INTEGER
        const bOrder = configByKey.get(b.key)?.order ?? Number.MAX_SAFE_INTEGER
        return aOrder - bOrder
      })
  })()
  const totalPages = Math.ceil(totalPatents / pageSize)
  const allSelected = patents.length > 0 && selectedIds.length === patents.length
  const hasActiveFilters = Object.values(filterValues).some(filterConditionHasValue) || !!searchText

  useEffect(() => {
    // Put the cursor on the first usable cell after the first data load. Keep
    // a user's current position when more continuous-scroll rows arrive or a
    // detail page returns to the same filtered scope.
    if (activeCell && patents.some(patent => patent.id === activeCell.patentId) && visibleFields.some(field => field.key === activeCell.fieldKey)) {
      return
    }
    if (patents.length > 0 && visibleFields.length > 0) {
      // This synchronizes the keyboard/mouse cursor with the first external
      // data load; later row loads preserve the user's selected cell.
      // eslint-disable-next-line react-hooks/set-state-in-effect
      setActiveCell({ patentId: patents[0].id, fieldKey: visibleFields[0].key })
    } else if (patents.length === 0 || visibleFields.length === 0) {
      setActiveCell(null)
    }
  }, [activeCell, patents, visibleFields])

  const pageNumbers = () => {
    const pages: (number | string)[] = []
    const maxVisible = 5
    if (totalPages <= maxVisible + 2) {
      for (let i = 1; i <= totalPages; i++) pages.push(i)
    } else {
      pages.push(1)
      const start = Math.max(2, page - 2)
      const end = Math.min(totalPages - 1, page + 2)
      if (start > 2) pages.push('...')
      for (let i = start; i <= end; i++) pages.push(i)
      if (end < totalPages - 1) pages.push('...')
      pages.push(totalPages)
    }
    return pages
  }

  const renderCellEditor = (patent: Patent, field: FieldMeta, value: JsonValue) => {
    const save = (v: JsonValue) => handleCellSave(patent.id, field.key, v)
    const cancel = () => setEditingCell(null)

    if (field.field_type === 'link') {
      return (
        <LinkFieldEditor
          patentId={patent.id}
          field={field}
          currentLinks={relationData[field.key]?.[patent.id]?.links || []}
          onChanged={() => void loadRelationData()}
          onCancel={cancel}
        />
      )
    }

    const commonStyle: React.CSSProperties = {
      width: '100%',
      padding: '4px 8px',
      border: '1px solid #3b82f6',
      borderRadius: 3,
      fontSize: 13,
      outline: 'none',
      background: '#fff',
    }

    if (field.field_type === 'select' && field.options) {
      return (
        <select
          style={commonStyle}
          autoFocus
          defaultValue={String(value ?? '')}
          onBlur={(e) => save(e.target.value || null)}
          onChange={(e) => {
            if (e.target.value) save(e.target.value)
          }}
        >
          <option value="">-</option>
          {field.options.map(opt => (
            <option key={opt} value={opt}>{opt}</option>
          ))}
        </select>
      )
    }

    if (field.field_type === 'boolean') {
      return (
        <select
          style={commonStyle}
          autoFocus
          defaultValue={value ? 'true' : value === false ? 'false' : ''}
          onBlur={(e) => save(e.target.value === 'true' ? true : e.target.value === 'false' ? false : null)}
        >
          <option value="">-</option>
          <option value="true">是</option>
          <option value="false">否</option>
        </select>
      )
    }

    if (field.field_type === 'longtext') {
      return (
        <textarea
          style={{ ...commonStyle, minHeight: 60, resize: 'vertical' }}
          autoFocus
          defaultValue={String(value ?? '')}
          onBlur={(e) => save(e.target.value || null)}
          onKeyDown={(e) => {
            if (e.key === 'Escape') cancel()
            if (e.key === 'Enter' && e.ctrlKey) save((e.target as HTMLTextAreaElement).value)
          }}
        />
      )
    }

    return (
      <input
        type={field.field_type === 'number' ? 'number' : field.field_type === 'date' ? 'date' : 'text'}
        style={commonStyle}
        autoFocus
        defaultValue={String(value ?? '')}
        onBlur={(e) => save(e.target.value || null)}
        onKeyDown={(e) => {
          if (e.key === 'Escape') cancel()
          if (e.key === 'Enter') save((e.target as HTMLInputElement).value)
        }}
      />
    )
  }

  const renderCellContent = (patent: Patent, field: FieldMeta) => {
    const value = getFieldValue(patent, field.key)
    const isEditing = editingCell?.patentId === patent.id && editingCell?.fieldKey === field.key

    if (isEditing) {
      return renderCellEditor(patent, field, value)
    }

    if (field.field_type === 'attachment') {
      return <AttachmentField patentId={patent.id} databaseId={activeDatabaseId} fieldKey={field.key} value={value} />
    }

    if (field.field_type === 'link') {
      const links = relationData[field.key]?.[patent.id]?.links || []
      return links.length > 0 ? (
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 4 }}>
          {links.map(link => (
            <span key={link.id} style={{ display: 'inline-block', padding: '2px 6px', borderRadius: 4, background: '#eff6ff', color: '#1d4ed8', fontSize: 12 }}>
              <PatentReferenceText value={link.label} onOpen={(number) => void handlePatentReferenceClick(number)} />
            </span>
          ))}
        </div>
      ) : <span style={{ color: '#94a3b8', fontSize: 12 }}>-</span>
    }

    if (field.field_type === 'lookup' || field.field_type === 'rollup') {
      const relationValue = relationData[field.key]?.[patent.id]?.value
      const displayValue = formatValue(relationValue ?? null, field)
      return (
        <span style={{ color: displayValue === '-' ? '#94a3b8' : '#374151', display: 'block', whiteSpace: 'normal', wordBreak: 'break-word', overflowWrap: 'anywhere', lineHeight: 1.5 }}>
          <PatentReferenceText value={displayValue} onOpen={(number) => void handlePatentReferenceClick(number)} />
        </span>
      )
    }

    if (field.key === 'product_id') {
      const product = products.find(item => item.id === patent.product_id)
      return <span style={{ color: product ? '#334155' : '#94a3b8' }}><PatentReferenceText value={product?.name || (patent.product_id ? `产品 #${patent.product_id}` : '-')} onOpen={(number) => void handlePatentReferenceClick(number)} /></span>
    }

    if (field.key === 'projects') {
      const linkedProjects = patent.projects || []
      return linkedProjects.length > 0
        ? <span style={{ color: '#1d4ed8' }}><PatentReferenceText value={linkedProjects.map(project => project.name || `项目 #${project.id}`).join('、')} onOpen={(number) => void handlePatentReferenceClick(number)} /></span>
        : <span style={{ color: '#94a3b8' }}>未关联项目</span>
    }

    if (field.key === 'legal_status') {
      const status = value as string
      return (
        <span className={`status-badge status-${status || 'unknown'}`}>
          {getStatusText(status)}
        </span>
      )
    }

    if (field.key === 'risk_level' || field.key === 'has_risk') {
      const hasRisk = patent.has_risk
      const level = patent.risk_level
      if (!hasRisk) return <span style={{ color: '#94a3b8', fontSize: 12 }}>-</span>
      return (
        <span className={`risk-badge risk-${level || 'low'}`}>
          {getRiskText(level, hasRisk)}
        </span>
      )
    }

    if (field.key === 'title') {
      return (
        <div>
          <div style={{ fontWeight: 500, color: '#2563eb', cursor: 'pointer' }}
           onClick={(e) => { e.stopPropagation(); openPatent(patent.id) }}
               onMouseEnter={(e) => { (e.currentTarget as HTMLElement).style.textDecoration = 'underline' }}
               onMouseLeave={(e) => { (e.currentTarget as HTMLElement).style.textDecoration = 'none' }}
          >
            <PatentReferenceText
              value={String(value ?? '-')}
              onOpen={(number) => void handlePatentReferenceClick(number)}
            />
          </div>
          {(patent.category || patent.subcategory) && (
            <div style={{ fontSize: 11, color: '#94a3b8', marginTop: 2 }}>
              {patent.category}{patent.subcategory ? ` / ${patent.subcategory}` : ''}
            </div>
          )}
        </div>
      )
    }

    if (field.key === 'application_number' || field.key === 'publication_number') {
      return (
        <span
          style={{ fontFamily: 'monospace', fontSize: 12, cursor: 'pointer', color: '#2563eb' }}
           onClick={(e) => { e.stopPropagation(); openPatent(patent.id) }}
          onMouseEnter={(e) => { (e.currentTarget as HTMLElement).style.textDecoration = 'underline' }}
          onMouseLeave={(e) => { (e.currentTarget as HTMLElement).style.textDecoration = 'none' }}
        >
          {String(value ?? '-')}
        </span>
      )
    }

    const displayValue = formatValue(value, field)

    return (
      <span
        style={{
          color: displayValue === '-' ? '#94a3b8' : '#374151',
          display: 'block',
          whiteSpace: 'normal',
          wordBreak: 'break-word',
          overflowWrap: 'anywhere',
          lineHeight: 1.5,
        }}
      >
        <PatentReferenceText value={displayValue} onOpen={(number) => void handlePatentReferenceClick(number)} />
      </span>
    )
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%', background: '#f3f4f6' }}>
      <div className="datagrid-toolbar">
        <div className="datagrid-toolbar-heading">
          {onOpenSidebar && (
            <button
              type="button"
              className="mobile-nav-toggle patent-mobile-nav-toggle"
              onClick={onOpenSidebar}
              aria-label="打开导航"
              title="打开导航"
            >
              <Icon name="menu" />
            </button>
          )}
          <h2 style={{ margin: 0, fontSize: 18, fontWeight: 600, color: '#111827' }}>
            {activeView?.name || '专利列表'}
          </h2>
          <span className="datagrid-toolbar-count">
            共 {totalPatents} 件{currentProductId ? ' · 当前产品筛选中' : ''}
          </span>
        </div>
        <div className="datagrid-toolbar-actions">
          {onOpenImport && (
            <button
              type="button"
              className="btn btn-primary datagrid-import-button"
              onClick={onOpenImport}
              aria-label="导入数据"
              title="导入 Excel、CSV 或粘贴的表格数据"
            >
              <Icon name="plus" size={17} />
            </button>
          )}
          <div className="search-suggest-wrap">
            <form className="datagrid-search-form" onSubmit={handleSearch}>
              <input
                type="text"
                className="form-input datagrid-search-input"
                placeholder="搜索专利号、标题、申请人..."
                value={searchInputText}
                onChange={(e) => handleSearchInputChange(e.target.value)}
                onKeyDown={handleSearchKeyDown}
                aria-autocomplete="list"
                aria-controls="patent-search-suggestions"
              />
            </form>
            {searchSuggestions.length > 0 && (
              <div id="patent-search-suggestions" className="search-suggest-menu" role="listbox">
                {searchSuggestions.map((suggestion, index) => (
                  <button
                    type="button"
                    key={`${suggestion.kind}-${suggestion.value}`}
                    className={`search-suggest-item ${index === activeSuggestionIndex ? 'active' : ''}`}
                    onMouseDown={event => event.preventDefault()}
                    onClick={() => applySearchSuggestion(suggestion)}
                    role="option"
                    aria-selected={index === activeSuggestionIndex}
                  >
                    <span className="search-suggest-kind">{suggestion.kind_label}</span>
                    <span className="search-suggest-value">{suggestion.label}</span>
                    {suggestion.kind !== 'title' && <span className="search-suggest-title">{suggestion.patent_title}</span>}
                  </button>
                ))}
              </div>
            )}
          </div>
          <button
            className={`btn btn-sm ${hasActiveFilters ? 'btn-primary' : 'btn-secondary'} datagrid-clear-filters`}
            onClick={handleClearAllFilters}
            style={{ display: hasActiveFilters ? 'inline-flex' : 'none' }}
          >
            清除筛选
          </button>
          <div className="datagrid-view-actions">
            {activeView && activeView.layout_type === 'table' && (
              <>
                <button
                  type="button"
                  className={`btn btn-sm ${getViewGroupFields(activeView).length > 0 ? 'btn-primary' : 'btn-secondary'}`}
                  onClick={() => setShowGroupConfig(true)}
                  title="按字段分组并折叠展示"
                >
                  <Icon name="table" size={14} /> 分组
                </button>
                <button
                  type="button"
                  className={`btn btn-sm ${activeView.conditional_formatting?.length ? 'btn-primary' : 'btn-secondary'}`}
                  onClick={() => setShowConditionalConfig(true)}
                  title="按条件突出显示单元格"
                >
                  <Icon name="filter" size={14} /> 条件格式
                </button>
                {getViewGroupFields(activeView).length > 0 && (
                  <span className="view-tools-summary">
                    已按 {getViewGroupFields(activeView).map(item => fields.find(field => field.key === item.field)?.name || item.field).join(' / ')} 分组
                  </span>
                )}
              </>
            )}
            {(activeView?.layout_type === 'table' || !activeView) && (
              <button type="button" className="btn btn-sm btn-secondary datagrid-view-settings-button" onClick={() => setShowTableSettings(true)} title="设置查看模式和行高">
                <Icon name="sliders" size={14} /> 查看设置
                <span className="datagrid-view-settings-hint">
                  {tableViewMode === 'continuous' ? '连续' : '分页'} · {rowHeightLimit === 'auto' ? '自适应' : `${rowHeightLimit}px`}
                </span>
              </button>
            )}
          </div>
          <div className="datagrid-tool-menu-wrap" ref={tableToolsRef}>
            <button
              type="button"
              className="btn btn-sm btn-secondary datagrid-tool-trigger"
              onClick={event => { event.stopPropagation(); setShowTableTools(value => !value) }}
              aria-expanded={showTableTools}
              aria-haspopup="menu"
              title="打开表格操作"
            >
              <Icon name="sliders" /> 表格工具 <Icon name={showTableTools ? 'chevron-up' : 'chevron-down'} size={13} />
            </button>
            {showTableTools && (
              <div className="datagrid-tool-menu" role="menu">
                <div className="datagrid-tool-menu-heading">当前表格操作</div>
                <div className="datagrid-tool-row">
                  <button className="menu-item" onClick={() => { void handleUndo(); setShowTableTools(false) }} disabled={undoStack.length === 0} title="撤回最近一次单元格编辑"><Icon name="undo" /> 撤回</button>
                  <button className="menu-item" onClick={() => { void handleRedo(); setShowTableTools(false) }} disabled={redoStack.length === 0} title="重做最近一次单元格编辑"><Icon name="redo" /> 重做</button>
                </div>
                <button className={`menu-item ${groupByFamily ? 'is-active' : ''}`} onClick={() => void handleFamilyGrouping()} title="把同族专利聚拢显示"><Icon name="table" /> 同族聚拢 {groupByFamily ? '已开启' : '已关闭'}</button>
                <button className="menu-item" onClick={() => { setShowFieldConfig(true); setShowTableTools(false) }} title="管理显示字段、顺序和冻结列"><Icon name="columns" /> 列管理</button>
                <div className="menu-divider" />
                <button className="menu-item menu-item-ai" onClick={() => { setQuickAnalyzePatentIds(patents.map(p => p.id)); setShowQuickAnalyze(true); setShowTableTools(false) }} title="对当前已加载专利执行 AI 快速分析"><Icon name="sparkles" /> AI 快速分析</button>
                <button className="menu-item" onClick={() => { handleExport(); setShowTableTools(false) }}><Icon name="download" /> 导出数据</button>
                <button className="menu-item menu-item-primary" onClick={() => { setShowWorkFileDialog(true); setShowTableTools(false) }} title="按业务模板生成 Excel、Word 或 CSV 工作文件"><Icon name="file" /> 工作文件</button>
              </div>
            )}
          </div>
          {viewConfigNotice && <span style={{ fontSize: 12, color: '#047857' }}>{viewConfigNotice}</span>}
        </div>
      </div>

      {Object.keys(filterValues).length > 0 && (
        <div className="filter-bar">
          <span style={{ fontSize: 11, color: '#6b7280' }}>已筛选：</span>
           {Object.entries(filterValues).filter(([, condition]) => filterConditionHasValue(condition)).map(([key, condition]) => {
             const field = fields.find(f => f.key === key)
             return (
               <span key={key} className="filter-chip">
                 {field?.name || key}: {FILTER_OPERATOR_LABELS[condition.operator]}{condition.value ? ` ${condition.value}` : ''}
                 <span className="chip-remove" onClick={() => handleHeaderFilterClear(key)}>×</span>
               </span>
            )
          })}
        </div>
      )}

      {selectedIds.length > 0 && (
        <div className="selection-bar">
          <span className="selection-summary">
            已选中 {selectedIds.length} 件专利
          </span>
          <div className="selection-actions">
            <button className="btn btn-xs btn-secondary" onClick={() => setShowBulkEdit(true)}>批量编辑</button>
            <button className="btn btn-xs btn-secondary" onClick={() => setShowBulkTag(true)}>批量打标签</button>
            <button className="btn btn-xs btn-secondary" onClick={() => openBulkTransfer('move_view')}>移动到视图</button>
            <button className="btn btn-xs btn-secondary" onClick={() => openBulkTransfer('move_database')}>移库</button>
            <button className="btn btn-xs btn-secondary" onClick={() => openBulkTransfer('duplicate')}>复制为工作副本</button>
            <button className="btn btn-xs btn-primary" onClick={() => { setQuickAnalyzePatentIds(selectedIds); setShowQuickAnalyze(true) }}>
              <Icon name="sparkles" size={13} /> AI 快速分析
            </button>
            <button
              className="btn btn-xs btn-danger"
              onClick={handleBulkDelete}
              style={{ color: '#dc2626', borderColor: '#fecaca' }}
            >
              批量删除
            </button>
          </div>
          <button className="btn btn-xs btn-ghost selection-clear" onClick={clearSelection}>
            取消选择
          </button>
        </div>
      )}

      <div ref={tableWrapperRef} className="data-grid-wrapper" onScroll={handleTableScroll}>
        {activeView?.layout_type === 'kanban' ? (
          <KanbanView
            view={activeView}
            fields={fields}
            onPatentClick={onPatentClick}
            onViewChange={handleViewChange}
            onTotalChange={handleKanbanTotalChange}
          />
        ) : activeView?.layout_type === 'form' ? (
          <FormView view={activeView} onViewChange={handleViewChange} />
        ) : activeView?.layout_type === 'gantt' ? (
          <GanttView
            view={activeView}
            fields={fields}
            onPatentClick={onPatentClick}
            onViewChange={handleViewChange}
            onTotalChange={handleKanbanTotalChange}
          />
        ) : loading ? (
          <div className="loading-state">
            <div className="spinner" style={{ width: 24, height: 24, borderWidth: 2, marginBottom: 12 }}></div>
            <span style={{ fontSize: 13, color: '#6b7280' }}>加载中...</span>
          </div>
        ) : patents.length === 0 ? (
          <div className="empty-state patent-empty-state">
            <div className="empty-state-icon" aria-hidden="true">[ ]</div>
            <div style={{ fontSize: 15, fontWeight: 500, color: '#374151', marginBottom: 6 }}>暂无专利数据</div>
            <div style={{ fontSize: 13, color: '#9ca3af' }}>点击右上角"导入"按钮导入专利数据，或先在左侧创建产品分类</div>
          </div>
        ) : (
          <table className="data-grid" style={{ width: 'max-content', minWidth: '100%' }}>
            <colgroup>
              <col style={{ width: CHECKBOX_COLUMN_WIDTH }} />
              <col style={{ width: INDEX_COLUMN_WIDTH }} />
              <col style={{ width: ACTION_COLUMN_WIDTH }} />
              {visibleFields.map(field => <col key={field.key} style={{ width: columnWidths[field.key] || DEFAULT_COLUMN_WIDTH }} />)}
            </colgroup>
            <thead>
              <tr>
                <th className="col-checkbox" style={{ width: 40, minWidth: 40, maxWidth: 40 }}>
                  <input type="checkbox" checked={allSelected} onChange={handleSelectAll} />
                </th>
                <th className="col-sequence" style={{ width: INDEX_COLUMN_WIDTH, minWidth: INDEX_COLUMN_WIDTH, maxWidth: INDEX_COLUMN_WIDTH, position: 'sticky', left: CHECKBOX_COLUMN_WIDTH, zIndex: 17, background: '#f9fafb' }}>
                  <span style={{ fontSize: 12, color: '#6b7280' }}>序号</span>
                </th>
                <th className="col-action col-ai-action" style={{ width: ACTION_COLUMN_WIDTH, minWidth: ACTION_COLUMN_WIDTH, maxWidth: ACTION_COLUMN_WIDTH, position: 'sticky', left: CHECKBOX_COLUMN_WIDTH + INDEX_COLUMN_WIDTH, zIndex: 16, background: '#f9fafb' }}>
                  <span style={{ fontSize: 12, color: '#2563eb', padding: '0 10px' }}><Icon name="sparkles" size={13} /> AI</span>
                </th>
                {visibleFields.map(field => {
                  const hasFilter = filterConditionHasValue(filterValues[field.key])
                  const isFilterable = field.filterable !== false
                  const isFrozen = frozenFields.has(field.key)
                  // 冻结列从序号和 AI 操作列之后开始排列。
                  let leftOffset = CHECKBOX_COLUMN_WIDTH + INDEX_COLUMN_WIDTH + ACTION_COLUMN_WIDTH
                  if (isFrozen) {
                    for (const f of visibleFields) {
                      if (f.key === field.key) break
                      if (frozenFields.has(f.key)) {
                        leftOffset += columnWidths[f.key] || DEFAULT_COLUMN_WIDTH
                      }
                    }
                  }
                  return (
                    <th
                      key={field.key}
                      className={`${isFrozen ? 'col-frozen' : ''} ${sortField === field.key ? 'col-sorted' : ''} ${hasFilter ? 'col-filtered' : ''} ${activeCell?.fieldKey === field.key ? 'crosshair-column-header' : ''}`}
                      style={{
                        width: columnWidths[field.key] || DEFAULT_COLUMN_WIDTH,
                        minWidth: 80,
                        ...(isFrozen ? { position: 'sticky', left: leftOffset, zIndex: 15, background: '#f9fafb' } : {}),
                      }}
                      onContextMenu={(e) => handleContextMenu(e, 'header', { fieldKey: field.key })}
                    >
                      <div
                        style={{
                          display: 'flex',
                          alignItems: 'center',
                          justifyContent: 'space-between',
                          height: '100%',
                          padding: '0 10px',
                          cursor: field.sortable ? 'pointer' : 'default',
                          minHeight: 34,
                        }}
                        onClick={() => handleSort(field.key)}
                      >
                        <span style={{
                          fontSize: 12,
                          fontWeight: 500,
                          color: sortField === field.key ? '#111827' : hasFilter ? '#2563eb' : '#6b7280',
                          overflow: 'hidden',
                          textOverflow: 'ellipsis',
                          whiteSpace: 'nowrap',
                          flex: 1,
                        }}>
                          {field.name}
                          {sortField === field.key && (
                            <span style={{ marginLeft: 4, fontSize: 10, color: '#3b82f6' }}>
                              {sortOrder === 'asc' ? '↑' : '↓'}
                            </span>
                          )}
                          {hasFilter && (
                            <span style={{ marginLeft: 4, fontSize: 10, color: '#2563eb' }}>●</span>
                          )}
                        </span>
                        <button
                          className="col-header-trigger"
                          onClick={(e) => {
                            e.stopPropagation()
                            if (activeHeaderMenu === field.key) {
                              setActiveHeaderMenu(null)
                              setHeaderFilterText('')
                            } else {
                              setActiveHeaderMenu(field.key)
                              const existingFilter = filterValues[field.key]
                              setHeaderFilterOperator(existingFilter?.operator || 'contains')
                              setHeaderFilterText(existingFilter?.value || '')
                            }
                          }}
                          style={{
                            width: 20,
                            height: 20,
                            display: 'flex',
                            alignItems: 'center',
                            justifyContent: 'center',
                            border: 'none',
                            background: 'transparent',
                            cursor: 'pointer',
                            color: hasFilter ? '#2563eb' : '#9ca3af',
                            borderRadius: 3,
                            fontSize: 14,
                            flexShrink: 0,
                            marginLeft: 4,
                          }}
                          onMouseEnter={(e) => { (e.currentTarget as HTMLElement).style.background = '#e5e7eb' }}
                          onMouseLeave={(e) => { (e.currentTarget as HTMLElement).style.background = 'transparent' }}
                        >
                          ▾
                        </button>
                      </div>
                      <div
                        className="col-resize-handle"
                        onPointerDown={(e) => {
                          e.preventDefault()
                          e.stopPropagation()
                          setResizing({
                            fieldKey: field.key,
                            startX: e.clientX,
                            startWidth: columnWidths[field.key] || DEFAULT_COLUMN_WIDTH,
                          })
                        }}
                        title="拖动调整列宽"
                      />
                      {activeHeaderMenu === field.key && (
                        <div className="col-header-menu" onClick={e => e.stopPropagation()}>
                          {isFilterable && (
                            <div style={{ padding: '8px 10px', borderBottom: '1px solid #f3f4f6' }}>
                              <div style={{ fontSize: 10, color: '#9ca3af', marginBottom: 4 }}>筛选 {field.name}</div>
                              <div style={{ display: 'flex', gap: 4, alignItems: 'center' }}>
                                <select
                                  value={headerFilterOperator}
                                  onChange={(e) => setHeaderFilterOperator(e.target.value as FilterOperator)}
                                  style={{ padding: '4px 5px', border: '1px solid #d1d5db', borderRadius: 4, fontSize: 12, background: '#fff' }}
                                >
                                  {Object.entries(FILTER_OPERATOR_LABELS).map(([operator, label]) => (
                                    <option key={operator} value={operator}>{label}</option>
                                  ))}
                                </select>
                                <input
                                  type="text"
                                  placeholder={headerFilterOperator === 'is_empty' || headerFilterOperator === 'is_not_empty' ? '无需输入值' : '输入关键词...'}
                                  value={headerFilterText}
                                  onChange={(e) => setHeaderFilterText(e.target.value)}
                                  disabled={headerFilterOperator === 'is_empty' || headerFilterOperator === 'is_not_empty'}
                                  onKeyDown={(e) => {
                                    if (e.key === 'Enter') handleHeaderFilterApply(field.key)
                                    if (e.key === 'Escape') { setActiveHeaderMenu(null); setHeaderFilterText('') }
                                  }}
                                  autoFocus
                                  style={{
                                    flex: 1,
                                    padding: '4px 8px',
                                    border: '1px solid #d1d5db',
                                    borderRadius: 4,
                                    fontSize: 12,
                                    outline: 'none',
                                    minWidth: 120,
                                  }}
                                />
                                <button
                                  className="btn btn-xs btn-primary"
                                  onClick={() => handleHeaderFilterApply(field.key)}
                                >
                                  确定
                                </button>
                              </div>
                              {hasFilter && (
                                <button
                                  className="btn btn-xs btn-ghost"
                                  onClick={() => handleHeaderFilterClear(field.key)}
                                  style={{ fontSize: 11, padding: '2px 0', marginTop: 4, color: '#dc2626' }}
                                >
                                  清除此列筛选
                                </button>
                              )}
                            </div>
                          )}
                          <div
                            className="menu-item"
                            onClick={() => handleSort(field.key)}
                          >
                            <span>{sortField === field.key && sortOrder === 'asc' ? '↓ 降序排列' : '↑ 升序排列'}</span>
                          </div>
                          <div className="menu-divider" />
                          <div className="menu-item" onClick={() => openInsertAIDialog('text', field.key, 'before')}>
                            <span style={{ color: '#2563eb' }}><Icon name="columns" /> 左侧插入新列</span>
                          </div>
                          <div className="menu-item" onClick={() => openInsertAIDialog('text', field.key, 'after')}>
                            <span style={{ color: '#2563eb' }}><Icon name="columns" /> 右侧插入新列</span>
                          </div>
                          <div
                            className="menu-item"
                            onClick={() => handleToggleFreeze(field.key)}
                          >
                            <span><Icon name={frozenFields.has(field.key) ? 'unlock' : 'lock'} /> {frozenFields.has(field.key) ? '取消冻结' : '冻结此列'}</span>
                          </div>
                          <div
                            className="menu-item"
                            onClick={() => openColumnStats(field.key)}
                          >
                            <span style={{ color: '#0891b2' }}><Icon name="chart" /> 统计此列</span>
                          </div>
                          <div
                            className="menu-item"
                            onClick={() => handleToggleFieldVisible(field.key)}
                          >
                            <span>隐藏此列</span>
                          </div>
                        </div>
                      )}
                    </th>
                  )
                })}
              </tr>
            </thead>
            <tbody>
              {familyDisplayPatents.map((p, rowIdx) => {
                // P2-8：同族聚拢模式下，为同族组交替背景色 + 行首徽章
                const familyBgColors = ['#faf5ff', '#eff6ff', '#f0fdf4', '#fefce8', '#fff7ed', '#fdf2f8']
                let rowBg: string | undefined
                let familyBadge: React.ReactNode = null
                if (groupByFamily && p.family_id) {
                  // 同族组用 family_id 哈希到颜色槽，保证同族同色
                  const colorSlot = p.family_id % familyBgColors.length
                  rowBg = familyBgColors[colorSlot]
                  // 检测同族组首行（前一行 family_id 不同）
                  const prevFamilyId = rowIdx > 0 ? familyDisplayPatents[rowIdx - 1].family_id : undefined
                  const isGroupStart = prevFamilyId !== p.family_id
                  if (isGroupStart) {
                    familyBadge = (
                      <span
                        style={{
                          display: 'inline-block',
                          background: '#7c3aed',
                          color: '#fff',
                          fontSize: 10,
                          fontWeight: 600,
                          padding: '1px 5px',
                          borderRadius: 8,
                          marginRight: 4,
                          verticalAlign: 'middle',
                        }}
                        title={`同族 ${p.family_id}，共 ${p.family_size ?? 1} 件`}
                      >
                        族{p.family_id}{p.family_size ? `·${p.family_size}` : ''}
                      </span>
                    )
                  }
                }
                const groupHeaders = groupPresentation?.headers.get(p.id) || []
                const isGroupRowCollapsed = groupHeaders.some(header => collapsedGroupKeys.has(header.id))
                const familyKey = p.family_id ? `family:${p.family_id}` : null
                const isFamilyStart = groupByFamily && !!p.family_id && familyFirstIds.has(p.id)
                const isFamilyRowCollapsed = !!familyKey && collapsedFamilyKeys.has(familyKey)
                return (
                <Fragment key={p.id}>
                {groupHeaders.map(groupHeader => (
                  <tr
                    key={groupHeader.id}
                    className="view-group-header"
                    onClick={() => setCollapsedGroupKeys(previous => {
                      const next = new Set(previous)
                      if (next.has(groupHeader.id)) next.delete(groupHeader.id)
                      else next.add(groupHeader.id)
                      return next
                    })}
                  >
                    <td colSpan={visibleFields.length + 3} style={{ padding: '8px 12px', background: '#f8fafc', borderBottom: '1px solid #e2e8f0', color: '#334155', cursor: 'pointer', fontWeight: 600 }}>
                      <span style={{ display: 'inline-block', width: 18, color: '#64748b' }}>{collapsedGroupKeys.has(groupHeader.id) ? '›' : '⌄'}</span>
                      {groupHeader.label}
                      <span style={{ marginLeft: 8, color: '#94a3b8', fontWeight: 400 }}>{groupHeader.count} 条</span>
                    </td>
                  </tr>
                ))}
                {isFamilyStart && (
                  <tr
                    className="family-group-header"
                    onClick={() => setCollapsedFamilyKeys(previous => {
                      const next = new Set(previous)
                      if (familyKey && next.has(familyKey)) next.delete(familyKey)
                      else if (familyKey) next.add(familyKey)
                      return next
                    })}
                  >
                    <td colSpan={visibleFields.length + 3}>
                      <span className="family-group-toggle">{familyKey && collapsedFamilyKeys.has(familyKey) ? '›' : '⌄'}</span>
                      <strong>{p.family_key || `同族 ${p.family_id}`}</strong>
                      <span className="family-group-count">{p.family_size || 1} 件独立专利</span>
                    </td>
                  </tr>
                )}
                {!isGroupRowCollapsed && !isFamilyRowCollapsed && (
                <tr
                  key={p.id}
                  className={`${selectedIds.includes(p.id) ? 'row-selected ' : ''}${rowHeightLimit === 'auto' ? '' : 'row-height-capped'}${activeCell?.patentId === p.id ? ' crosshair-row' : ''}`}
                  onClick={(e) => {
                    if ((e.target as HTMLElement).closest('input') ||
                        (e.target as HTMLElement).closest('select') ||
                        (e.target as HTMLElement).closest('textarea') ||
                        (e.target as HTMLElement).closest('button') ||
                        (e.target as HTMLElement).closest('.cell-action-btn')) return
                    openPatent(p.id)
                  }}
                  onContextMenu={(e) => handleContextMenu(e, 'row', { patentId: p.id })}
                  style={{
                    cursor: 'pointer',
                    background: rowBg,
                    ...(rowHeightLimit === 'auto' ? {} : { '--row-max-height': `${rowHeightLimit}px` } as React.CSSProperties),
                  }}
                >
                  <td className="col-checkbox">
                    <input
                      type="checkbox"
                      checked={selectedIds.includes(p.id)}
                      onChange={() => toggleSelect(p.id)}
                      onClick={(e) => e.stopPropagation()}
                    />
                    {familyBadge}
                  </td>
                  <td
                    className="col-sequence"
                    style={{ width: INDEX_COLUMN_WIDTH, minWidth: INDEX_COLUMN_WIDTH, maxWidth: INDEX_COLUMN_WIDTH, position: 'sticky', left: CHECKBOX_COLUMN_WIDTH, zIndex: 7, background: '#fff', textAlign: 'center', color: '#64748b', fontVariantNumeric: 'tabular-nums' }}
                  >
                    {(tableViewMode === 'pagination' ? (page - 1) * pageSize : 0) + rowIdx + 1}
                  </td>
                  <td className="col-action" style={{ width: ACTION_COLUMN_WIDTH, minWidth: ACTION_COLUMN_WIDTH, maxWidth: ACTION_COLUMN_WIDTH, position: 'sticky', left: CHECKBOX_COLUMN_WIDTH + INDEX_COLUMN_WIDTH, zIndex: 6, background: '#fff', padding: '4px 6px' }}>
                    <div style={{ display: 'flex', gap: 2 }}>
                      <button
                        className="cell-action-btn"
                        onClick={(e) => {
                          e.stopPropagation()
                          handleQuickAI(p.id)
                        }}
                        disabled={aiProcessingRow === p.id}
                        style={{
                          width: 26,
                          height: 26,
                          border: '1px solid #bfdbfe',
                          background: aiProcessingRow === p.id ? '#dbeafe' : '#eff6ff',
                          color: aiProcessingRow === p.id ? '#93c5fd' : '#2563eb',
                          borderRadius: 4,
                          cursor: aiProcessingRow === p.id ? 'wait' : 'pointer',
                          fontSize: 12,
                          display: 'flex',
                          alignItems: 'center',
                          justifyContent: 'center',
                          padding: 0,
                        }}
                        title="AI快速分析"
                      >
                        <Icon name={aiProcessingRow === p.id ? 'refresh' : 'sparkles'} size={14} />
                      </button>
                    </div>
                  </td>
                  {visibleFields.map(field => {
                    const isFrozen = frozenFields.has(field.key)
                    const cellIsEditing = editingCell?.patentId === p.id && editingCell.fieldKey === field.key
                    let leftOffset = CHECKBOX_COLUMN_WIDTH + INDEX_COLUMN_WIDTH + ACTION_COLUMN_WIDTH
                    if (isFrozen) {
                      for (const f of visibleFields) {
                        if (f.key === field.key) break
                        if (frozenFields.has(f.key)) {
                          leftOffset += columnWidths[f.key] || DEFAULT_COLUMN_WIDTH
                        }
                      }
                    }
                    return (
                    <td
                      key={field.key}
                      className={`${isFrozen ? 'col-frozen' : ''} ${field.editable ? 'cell-editable' : ''} ${cellIsEditing ? 'cell-editing' : ''} ${activeCell?.patentId === p.id ? 'crosshair-row-cell' : ''} ${activeCell?.fieldKey === field.key ? 'crosshair-column-cell' : ''} ${activeCell?.patentId === p.id && activeCell?.fieldKey === field.key ? 'crosshair-cell' : ''}`}
                      style={{
                        width: columnWidths[field.key] || DEFAULT_COLUMN_WIDTH,
                        padding: field.field_type === 'longtext' ? '8px 10px' : '6px 10px',
                        whiteSpace: 'normal',
                        wordBreak: 'break-word',
                        overflowWrap: 'anywhere',
                        verticalAlign: 'top',
                        position: 'relative',
                        ...(isFrozen ? { position: 'sticky', left: leftOffset, zIndex: 5, background: '#fff' } : {}),
                        ...getConditionalCellStyle(field.key, getFieldValue(p, field.key)),
                      }}
                      onMouseDown={() => setActiveCell({ patentId: p.id, fieldKey: field.key })}
                      onClick={(e) => {
                        if (field.editable) {
                          e.stopPropagation()
                          handleCellClick(p.id, field.key, e)
                        }
                      }}
                      onContextMenu={(e) => handleContextMenu(e, 'row', { patentId: p.id, fieldKey: field.key })}
                    >
                      <div className={`cell-value-shell${cellIsEditing ? ' cell-value-shell-editing' : ''}`}>{renderCellContent(p, field)}</div>
                    </td>
                    )
                  })}
                </tr>
                )}
                </Fragment>
                )
              })}
            </tbody>
          </table>
        )}
      </div>

      {(activeView?.layout_type === 'table' || !activeView) && <div className="datagrid-footer">
        {tableViewMode === 'continuous' ? (
          <span style={{ fontSize: 12, color: '#6b7280' }}>
            已加载 {patents.length} / 共 {totalPatents} 条
            {continuousLoading && <span style={{ marginLeft: 8, color: '#0f766e' }}>正在加载...</span>}
            {!continuousLoading && patents.length >= totalPatents && totalPatents > 0 && <span style={{ marginLeft: 8, color: '#94a3b8' }}>已加载全部记录</span>}
          </span>
        ) : (
          <span style={{ fontSize: 12, color: '#6b7280' }}>
            第 {totalPatents === 0 ? 0 : (page - 1) * pageSize + 1} - {Math.min(page * pageSize, totalPatents)} 条，共 {totalPatents} 条
          </span>
        )}
        {tableViewMode === 'pagination' && <div style={{ display: 'flex', alignItems: 'center', gap: 2 }}>
          <button
            className="btn btn-xs btn-secondary"
            disabled={page <= 1}
            onClick={() => setPage(page - 1)}
          >
            上一页
          </button>
          {pageNumbers().map((p, idx) =>
            typeof p === 'number' ? (
              <button
                key={idx}
                className="btn btn-xs"
                onClick={() => setPage(p)}
                style={{
                  padding: '2px 7px',
                  minWidth: 24,
                  background: p === page ? '#2563eb' : '#fff',
                  color: p === page ? '#fff' : '#374151',
                  border: `1px solid ${p === page ? '#2563eb' : '#d1d5db'}`,
                  fontWeight: p === page ? 600 : 400,
                }}
              >
                {p}
              </button>
            ) : (
              <span key={idx} style={{ fontSize: 12, color: '#9ca3af', padding: '0 2px' }}>…</span>
            )
          )}
          <button
            className="btn btn-xs btn-secondary"
            disabled={page >= totalPages}
            onClick={() => setPage(page + 1)}
          >
            下一页
          </button>
          <div style={{ display: 'flex', alignItems: 'center', gap: 4, marginLeft: 8 }}>
            <span style={{ fontSize: 12, color: '#6b7280' }}>跳至</span>
            <input
              type="number"
              min={1}
              max={totalPages}
              value={pageInputValue}
              onChange={(e) => setPageInputValue(e.target.value)}
              onKeyDown={(e) => { if (e.key === 'Enter') handlePageJump() }}
              onBlur={handlePageJump}
              style={{
                width: 48,
                height: 24,
                padding: '0 6px',
                border: '1px solid #d1d5db',
                borderRadius: 4,
                fontSize: 12,
                textAlign: 'center',
                outline: 'none',
              }}
            />
            <span style={{ fontSize: 12, color: '#6b7280' }}>页</span>
          </div>
        </div>}
      </div>}

      {showFieldConfig && activeView && (
        <ViewColumnConfigPanel
          key={activeView.id}
          open
          view={activeView}
          fields={fields}
          onClose={() => setShowFieldConfig(false)}
          onSave={saveViewColumnConfig}
          onRemove={fieldKey => void handleDeleteColumnByKey(fieldKey)}
        />
      )}

      {showTableSettings && (
        <Modal title="查看设置" onClose={() => setShowTableSettings(false)} width={460}>
          <div className="table-settings-modal">
            <section>
              <h4>查看模式</h4>
              <div className="table-settings-choice-grid">
                {([
                  ['pagination', '分页模式', '适合逐页核对和批量处理'],
                  ['continuous', '连续滚动', '像 Excel 一样向下浏览并加载'],
                ] as const).map(([value, label, description]) => (
                  <button
                    key={value}
                    type="button"
                    className={`table-settings-choice ${tableViewMode === value ? 'active' : ''}`}
                    onClick={() => handleTableViewModeChange(value)}
                  >
                    <strong>{label}</strong>
                    <span>{description}</span>
                  </button>
                ))}
              </div>
            </section>
            <section>
              <h4>行高上限</h4>
              <div className="table-settings-row-height">
                {(['auto', 56, 72, 96, 120] as const).map(value => (
                  <button
                    key={String(value)}
                    type="button"
                    className={`btn btn-sm ${rowHeightLimit === value ? 'btn-primary' : 'btn-secondary'}`}
                    onClick={() => handleRowHeightLimitChange(value)}
                  >
                    {value === 'auto' ? '自适应' : `${value}px`}
                  </button>
                ))}
              </div>
              <p className="table-settings-note">限制单元格展开高度，完整内容仍可在详情页查看。</p>
            </section>
          </div>
        </Modal>
      )}

      {showFieldConfig && !activeView && (
        <ColumnConfigPanel
          open
          fields={fields}
          frozenFields={frozenFields}
          onClose={() => setShowFieldConfig(false)}
          onToggleVisible={handleToggleFieldVisible}
          onToggleFreeze={handleToggleFreeze}
          onRemove={fieldKey => void handleDeleteColumnByKey(fieldKey)}
          onReorder={handleReorderFields}
        />
      )}

      {showBulkEdit && (
        <Modal title={`批量编辑 ${selectedIds.length} 条专利`} onClose={() => setShowBulkEdit(false)} width={520}>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
            <p style={{ fontSize: 12, color: '#9ca3af', margin: 0 }}>
              只填写需要修改的字段，留空的字段保持不变。
            </p>
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
              <div>
                <label style={{ display: 'block', fontSize: 12, color: '#6b7280', marginBottom: 4 }}>关联模块</label>
                <input className="form-input" value={bulkModule} onChange={e => setBulkModule(e.target.value)} placeholder="如：摄像头模块" />
              </div>
              <div>
                <label style={{ display: 'block', fontSize: 12, color: '#6b7280', marginBottom: 4 }}>风险等级</label>
                <select className="form-input" value={bulkRiskLevel} onChange={e => setBulkRiskLevel(e.target.value)}>
                  <option value="">不修改</option>
                  <option value="none">无风险</option>
                  <option value="low">低风险</option>
                  <option value="medium">中风险</option>
                  <option value="high">高风险</option>
                  <option value="critical">严重风险</option>
                </select>
              </div>
              <div>
                <label style={{ display: 'block', fontSize: 12, color: '#6b7280', marginBottom: 4 }}>法律状态</label>
                <select className="form-input" value={bulkLegalStatus} onChange={e => setBulkLegalStatus(e.target.value)}>
                  <option value="">不修改</option>
                  <option value="unknown">未知</option>
                  <option value="pending">审查中</option>
                  <option value="granted">已授权</option>
                  <option value="rejected">驳回</option>
                  <option value="withdrawn">撤回</option>
                  <option value="expired">失效</option>
                </select>
              </div>
              <div>
                <label style={{ display: 'block', fontSize: 12, color: '#6b7280', marginBottom: 4 }}>国家/地区</label>
                <select className="form-input" value={bulkCountry} onChange={e => setBulkCountry(e.target.value)}>
                  <option value="">不修改</option>
                  <option value="CN">中国 (CN)</option>
                  <option value="US">美国 (US)</option>
                  <option value="EP">欧洲 (EP)</option>
                  <option value="JP">日本 (JP)</option>
                  <option value="KR">韩国 (KR)</option>
                  <option value="DE">德国 (DE)</option>
                  <option value="GB">英国 (GB)</option>
                  <option value="WO">PCT (WO)</option>
                </select>
              </div>
              <div>
                <label style={{ display: 'block', fontSize: 12, color: '#6b7280', marginBottom: 4 }}>技术分类</label>
                <input className="form-input" value={bulkCategory} onChange={e => setBulkCategory(e.target.value)} placeholder="如：光学/成像" />
              </div>
              <div>
                <label style={{ display: 'block', fontSize: 12, color: '#6b7280', marginBottom: 4 }}>申请人</label>
                <input className="form-input" value={bulkApplicant} onChange={e => setBulkApplicant(e.target.value)} placeholder="如：某科技公司" />
              </div>
            </div>
            <details style={{ borderTop: '1px solid #e5e7eb', paddingTop: 10 }}>
              <summary style={{ cursor: 'pointer', fontSize: 12, color: '#475569', fontWeight: 600 }}>选择其他字段批量赋值</summary>
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 8, marginTop: 8 }}>
                <select
                  className="form-input"
                  value={bulkFieldKey}
                  onChange={e => { setBulkFieldKey(e.target.value); setBulkFieldValue('') }}
                >
                  <option value="">不追加其他字段</option>
                  {fields.filter(field => field.editable && !['has_risk', 'risk_level', 'risk_description', 'family_members', 'cited_patents', 'citing_patents', 'projects'].includes(field.key)).map(field => (
                    <option key={field.key} value={field.key}>{field.name}</option>
                  ))}
                </select>
                {(() => {
                  const selectedField = fields.find(field => field.key === bulkFieldKey)
                  if (selectedField?.field_type === 'select' && selectedField.options) {
                    return <select className="form-input" value={bulkFieldValue} onChange={e => setBulkFieldValue(e.target.value)}><option value="">请选择值</option>{selectedField.options.map(option => <option key={option} value={option}>{option}</option>)}</select>
                  }
                  if (selectedField?.field_type === 'boolean') {
                    return <select className="form-input" value={bulkFieldValue} onChange={e => setBulkFieldValue(e.target.value)}><option value="">请选择值</option><option value="true">是</option><option value="false">否</option></select>
                  }
                  return <input className="form-input" value={bulkFieldValue} onChange={e => setBulkFieldValue(e.target.value)} placeholder="批量写入相同值" disabled={!bulkFieldKey} />
                })()}
              </div>
              <div style={{ marginTop: 4, fontSize: 11, color: '#94a3b8' }}>空值不参与批量更新；风险正式结论和关系原始列不能在这里修改。</div>
            </details>
            <div style={{ display: 'flex', gap: 8, justifyContent: 'flex-end', marginTop: 8 }}>
              <button className="btn btn-secondary" onClick={() => setShowBulkEdit(false)}>取消</button>
              <button className="btn btn-primary" onClick={handleBulkEditSave}>保存</button>
            </div>
          </div>
        </Modal>
      )}

      {bulkTransferAction && (
        <Modal
          title={bulkTransferAction === 'move_database' ? `移库 ${selectedIds.length} 条专利` : bulkTransferAction === 'move_view' ? `移动到视图 ${selectedIds.length} 条专利` : `复制 ${selectedIds.length} 条工作副本`}
          onClose={() => setBulkTransferAction(null)}
          width={520}
        >
          <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
            <div style={{ padding: '10px 12px', background: '#f8fafc', border: '1px solid #e2e8f0', borderRadius: 6, fontSize: 12, color: '#475569', lineHeight: 1.6 }}>
              {bulkTransferAction === 'duplicate'
                ? '复制会生成可继续加工的工作副本，副本清空申请号、公开号和授权号，并保留来源专利 ID。'
                : '整批操作会先校验全部记录和目标，校验失败时旧数据不改变。'}
            </div>
            {(bulkTransferAction === 'move_database' || bulkTransferAction === 'duplicate') && (
              <div>
                <label style={{ display: 'block', fontSize: 12, color: '#64748b', marginBottom: 4 }}>目标数据库</label>
                <select className="form-input" value={bulkTargetDatabaseId ?? ''} onChange={e => setBulkTargetDatabaseId(e.target.value ? Number(e.target.value) : null)}>
                  <option value="">请选择数据库</option>
                  {databases.filter(database => !database.is_archived).map(database => (
                    <option key={database.id} value={database.id}>{database.name}</option>
                  ))}
                </select>
              </div>
            )}
            {bulkTransferAction === 'move_view' && (
              <div>
                <label style={{ display: 'block', fontSize: 12, color: '#64748b', marginBottom: 4 }}>目标视图</label>
                <select className="form-input" value={bulkTargetViewId ?? ''} onChange={e => setBulkTargetViewId(e.target.value ? Number(e.target.value) : null)}>
                  <option value="">库主表（清除显式视图）</option>
                  {views.filter(view => view.database_id === activeDatabaseId && !view.is_archived && view.layout_type === 'table').map(view => (
                    <option key={view.id} value={view.id}>{view.name}</option>
                  ))}
                </select>
                <div style={{ marginTop: 4, fontSize: 11, color: '#94a3b8' }}>只能移动到当前数据库的表格视图。</div>
              </div>
            )}
            <div style={{ display: 'flex', gap: 8, justifyContent: 'flex-end' }}>
              <button className="btn btn-secondary" onClick={() => setBulkTransferAction(null)}>取消</button>
              <button className="btn btn-primary" onClick={handleBulkTransfer}>
                {bulkTransferAction === 'duplicate' ? '创建工作副本' : '执行批量操作'}
              </button>
            </div>
          </div>
        </Modal>
      )}

      {showBulkTag && (
        <Modal title={`批量打标签 ${selectedIds.length} 条专利`} onClose={() => setShowBulkTag(false)} width={480}>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
            <div>
              <label style={{ display: 'block', fontSize: 12, color: '#6b7280', marginBottom: 4 }}>操作模式</label>
              <div style={{ display: 'flex', gap: 8 }}>
                {(['add', 'replace', 'remove'] as const).map(m => (
                  <button
                    key={m}
                    className={`btn ${bulkTagMode === m ? 'btn-primary' : 'btn-secondary'}`}
                    style={{ fontSize: 12, padding: '4px 12px' }}
                    onClick={() => setBulkTagMode(m)}
                  >
                    {m === 'add' ? '追加标签' : m === 'replace' ? '替换全部' : '移除标签'}
                  </button>
                ))}
              </div>
              <p style={{ fontSize: 11, color: '#9ca3af', margin: '4px 0 0' }}>
                {bulkTagMode === 'add' && '把选中的标签追加到每条专利（保留原有标签）'}
                {bulkTagMode === 'replace' && '用选中的标签替换每条专利的全部标签'}
                {bulkTagMode === 'remove' && '从每条专利中移除选中的标签'}
              </p>
            </div>
            <div>
              <label style={{ display: 'block', fontSize: 12, color: '#6b7280', marginBottom: 4 }}>
                选择标签 {bulkTagLoading && '（加载中...）'}
              </label>
              {tagsList.length === 0 && !bulkTagLoading ? (
                <p style={{ fontSize: 12, color: '#9ca3af' }}>
                  暂无标签。请先在「管理」页面创建标签。
                </p>
              ) : (
                <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6, maxHeight: 240, overflowY: 'auto', padding: 4, border: '1px solid #e5e7eb', borderRadius: 6 }}>
                  {tagsList.map(t => {
                    const selected = bulkTagIds.includes(t.id)
                    return (
                      <button
                        key={t.id}
                        onClick={() => toggleBulkTagId(t.id)}
                        style={{
                          fontSize: 12, padding: '4px 10px', cursor: 'pointer',
                          border: selected ? '1px solid #3b82f6' : '1px solid #d1d5db',
                          borderRadius: 14, background: selected ? '#eff6ff' : '#fff',
                          color: selected ? '#1d4ed8' : '#374151',
                        }}
                      >
                        {t.color && (
                          <span style={{
                            display: 'inline-block', width: 8, height: 8, borderRadius: '50%',
                            background: t.color, marginRight: 4, verticalAlign: 'middle',
                          }} />
                        )}
                        {t.name}
                      </button>
                    )
                  })}
                </div>
              )}
            </div>
            {bulkTagIds.length > 0 && (
              <p style={{ fontSize: 12, color: '#6b7280', margin: 0 }}>
                已选 {bulkTagIds.length} 个标签
              </p>
            )}
            <div style={{ display: 'flex', gap: 8, justifyContent: 'flex-end' }}>
              <button className="btn btn-secondary" onClick={() => setShowBulkTag(false)}>取消</button>
              <button className="btn btn-primary" onClick={handleBulkTagSave} disabled={bulkTagIds.length === 0}>
                确认
              </button>
            </div>
          </div>
        </Modal>
      )}

      {showQuickAnalyze && (
        <AIQuickAnalyzeModal
          patentIds={quickAnalyzePatentIds}
          fields={fields}
          customFields={customFields}
          initialInputFields={quickAnalyzeInputFields}
          onClose={() => setShowQuickAnalyze(false)}
          onStarted={handleQuickAnalyzeStarted}
        />
      )}

      {showInsertAIColumn && (
        <Modal
          title="插入新列"
          width={680}
          onClose={() => {
            setShowInsertAIColumn(false)
            setNewAIColumnName('')
            setNewColumnOptions('')
            setInsertColType('text')
            setInsertColFrozen(false)
          }}
        >
          <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
            <div style={{
              padding: '10px 12px',
              background: '#eff6ff',
              border: '1px solid #bfdbfe',
              borderRadius: 6,
              fontSize: 12,
              color: '#1e40af',
              lineHeight: 1.6,
            }}>
              新建普通字段用于人工补充、筛选和导出。AI 分析请统一从“AI 快速分析”进入，并在那里选择可复用模板、输入列和处理范围。
            </div>

            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
              <div>
                <label style={{ display: 'block', fontSize: 12, color: '#64748b', marginBottom: 4, fontWeight: 500 }}>
                  新列名称 <span style={{ color: '#dc2626' }}>*</span>
                </label>
                <input
                  className="form-input"
                  value={newAIColumnName}
                  onChange={e => setNewAIColumnName(e.target.value)}
                  placeholder="例如：技术领域分类"
                />
              </div>
              <div>
                <label style={{ display: 'block', fontSize: 12, color: '#64748b', marginBottom: 4, fontWeight: 500 }}>
                  列类型
                </label>
                <select
                  className="form-input"
                  value={insertColType}
                  onChange={e => {
                    const value = e.target.value
                    if (['text', 'longtext', 'number', 'date', 'select', 'boolean', 'attachment'].includes(value)) {
                      setInsertColType(value as typeof insertColType)
                    }
                  }}
                >
                  <option value="text">文本（手动填写）</option>
                  <option value="longtext">长文本（手动填写）</option>
                  <option value="number">数字</option>
                  <option value="date">日期</option>
                  <option value="select">单选（下拉）</option>
                  <option value="boolean">是/否</option>
                  <option value="attachment">附件</option>
                </select>
              </div>
            </div>

            {insertColType === 'select' && (
              <div>
                <label style={{ display: 'block', fontSize: 12, color: '#64748b', marginBottom: 4, fontWeight: 500 }}>
                  候选项 <span style={{ color: '#dc2626' }}>*</span>（每行一个）
                </label>
                <textarea
                  className="form-input"
                  style={{ minHeight: 80, fontSize: 12 }}
                  value={newColumnOptions}
                  onChange={e => setNewColumnOptions(e.target.value)}
                  placeholder={'例如：\n机械\n电子\n软件\n化学'}
                />
              </div>
            )}

            <label style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 13, color: '#475569', cursor: 'pointer' }}>
              <input
                type="checkbox"
                checked={insertColFrozen}
                onChange={e => setInsertColFrozen(e.target.checked)}
              />
              冻结此列（始终显示在左侧）
            </label>

            <div style={{ display: 'flex', gap: 8, justifyContent: 'flex-end', marginTop: 4 }}>
              <button
                className="btn btn-secondary"
                onClick={() => {
                  setShowInsertAIColumn(false)
                  setNewAIColumnName('')
                  setNewColumnOptions('')
                  setInsertColType('text')
                  setInsertColFrozen(false)
                }}
              >
                取消
              </button>
              <button
                className="btn btn-primary"
                onClick={() => void handleInsertAIColumn()}
                disabled={creatingAIColumn}
              >
                {creatingAIColumn ? '创建中...' : '创建列'}
              </button>
            </div>
          </div>
        </Modal>
      )}

      {showColumnStats && (
        <Modal
          title={`列统计：${fields.find(f => f.key === statsFieldKey)?.name || statsFieldKey}`}
          width={680}
          onClose={() => {
            setShowColumnStats(false)
            setShowStatsToTags(false)
          }}
        >
          <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
            {statsLoading ? (
              <div style={{ textAlign: 'center', padding: 40, color: '#64748b' }}>
                <div className="spinner" style={{ width: 32, height: 32, margin: '0 auto 12px', borderWidth: 3 }}></div>
                统计中...
              </div>
            ) : statsData.length === 0 ? (
              <div style={{ textAlign: 'center', padding: 40, color: '#94a3b8' }}>无数据</div>
            ) : (
              <>
                <div style={{
                  display: 'flex', justifyContent: 'space-between', alignItems: 'center',
                  padding: '8px 12px', background: '#f0f9ff', borderRadius: 6, fontSize: 12, color: '#0369a1',
                }}>
                  <span>共 {statsData.length} 个去重值</span>
                  <button
                    className="btn btn-sm btn-primary"
                    style={{ fontSize: 12, padding: '4px 10px' }}
                    onClick={() => setShowStatsToTags(true)}
                  >
                    <Icon name="tag" /> 转为分类标签
                  </button>
                </div>

                {showStatsToTags && (
                  <div style={{
                    background: '#fefce8', border: '1px solid #fde68a', borderRadius: 6, padding: 12,
                  }}>
                    <div style={{ fontSize: 13, fontWeight: 600, marginBottom: 8 }}>把统计结果转为标签体系</div>
                    <div style={{ display: 'flex', gap: 8, marginBottom: 8 }}>
                      <input
                        className="form-input"
                        style={{ flex: 1, fontSize: 12 }}
                        value={tagGroupName}
                        onChange={e => setTagGroupName(e.target.value)}
                        placeholder="标签组名称"
                      />
                      <label style={{ display: 'flex', alignItems: 'center', gap: 4, fontSize: 12, color: '#475569', whiteSpace: 'nowrap' }}>
                        <input type="checkbox" checked={autoApplyTags} onChange={e => setAutoApplyTags(e.target.checked)} />
                        自动给原专利打标
                      </label>
                    </div>
                    <div style={{ display: 'flex', gap: 6 }}>
                      <button className="btn btn-primary" style={{ fontSize: 12, padding: '4px 12px' }} onClick={handleStatsToTags} disabled={convertingTags}>
                        {convertingTags ? '转换中...' : '确认转换'}
                      </button>
                      <button className="btn btn-secondary" style={{ fontSize: 12, padding: '4px 12px' }} onClick={() => setShowStatsToTags(false)}>
                        取消
                      </button>
                    </div>
                  </div>
                )}

                <div style={{ maxHeight: 400, overflowY: 'auto', border: '1px solid #e2e8f0', borderRadius: 6 }}>
                  <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 12 }}>
                    <thead style={{ position: 'sticky', top: 0, background: '#f8fafc', zIndex: 1 }}>
                      <tr>
                        <th style={{ padding: '8px 10px', textAlign: 'left', fontWeight: 600, borderBottom: '1px solid #e2e8f0' }}>值</th>
                        <th style={{ padding: '8px 10px', textAlign: 'right', fontWeight: 600, width: 80, borderBottom: '1px solid #e2e8f0' }}>计数</th>
                        <th style={{ padding: '8px 10px', textAlign: 'right', fontWeight: 600, width: 80, borderBottom: '1px solid #e2e8f0' }}>占比</th>
                        <th style={{ padding: '8px 10px', textAlign: 'left', fontWeight: 600, width: 120, borderBottom: '1px solid #e2e8f0' }}>分布</th>
                      </tr>
                    </thead>
                    <tbody>
                      {statsData.map((item, i) => (
                        <tr key={i} style={{ borderTop: '1px solid #f1f5f9' }}>
                          <td style={{ padding: '6px 10px', wordBreak: 'break-word' }}>{item.value}</td>
                          <td style={{ padding: '6px 10px', textAlign: 'right', fontFamily: 'monospace' }}>{item.count}</td>
                          <td style={{ padding: '6px 10px', textAlign: 'right', color: '#64748b' }}>{item.percentage}%</td>
                          <td style={{ padding: '6px 10px' }}>
                            <div style={{
                              height: 8, background: '#e2e8f0', borderRadius: 4, overflow: 'hidden',
                            }}>
                              <div style={{
                                height: '100%',
                                width: `${item.percentage}%`,
                                background: 'linear-gradient(90deg, #3b82f6, #60a5fa)',
                                borderRadius: 4,
                              }}></div>
                            </div>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </>
            )}
          </div>
        </Modal>
      )}

      {/* 右键上下文菜单 */}
      {contextMenu && (
        <div
          className="context-menu"
          style={{
            position: 'fixed',
            left: Math.max(8, Math.min(contextMenu.x, window.innerWidth - 240)),
            top: Math.max(8, Math.min(contextMenu.y, window.innerHeight - 260)),
            zIndex: 1100,
            background: '#fff',
            border: '1px solid #e5e7eb',
            borderRadius: 8,
            boxShadow: '0 10px 25px rgba(0,0,0,0.15)',
            minWidth: 200,
            padding: '4px 0',
            fontSize: 12,
          }}
          onClick={() => setContextMenu(null)}
        >
          {contextMenu.type === 'row' && (() => {
            const patent = patents.find(p => p.id === contextMenu.patentId)
            const fieldName = contextMenu.fieldKey ? fields.find(f => f.key === contextMenu.fieldKey)?.name : null
            return (
              <>
                {/* 行操作 */}
                {patent && (
                  <>
                    <div className="menu-heading">
                      {patent.title?.slice(0, 30) || `#${patent.id}`}
                    </div>
                    <div className="menu-item" onClick={openContextPatent}>
                      <Icon name="file" /> 查看详情
                    </div>
                    {fieldName && (
                      <div className="menu-item" onClick={() => handleCopyCell(contextMenu.patentId!, contextMenu.fieldKey!)}>
                        <Icon name="copy" /> 复制"{fieldName}"的值
                      </div>
                    )}
                    {contextMenu.fieldKey && (
                      <div className="menu-item menu-item-ai" onClick={() => handleCellQuickAI(contextMenu.patentId!, contextMenu.fieldKey!)}>
                        <Icon name="sparkles" /> 用此单元格作为 AI 输入
                      </div>
                    )}
                    <div className="menu-divider" />
                    <div className="menu-item" style={{ color: '#dc2626' }} onClick={() => handleDeletePatent(contextMenu.patentId!)}>
                      <Icon name="trash" /> 删除此行
                    </div>
                  </>
                )}
              </>
            )
          })()}
          {contextMenu.type === 'header' && (() => {
            const field = fields.find(f => f.key === contextMenu.fieldKey)
            if (!field) return null
            const isFrozen = frozenFields.has(field.key)
            return (
              <>
                <div className="menu-heading">
                  列：{field.name}
                  <span style={{ marginLeft: 6, fontSize: 10, padding: '1px 4px', background: '#eff6ff', color: '#1e40af', borderRadius: 2 }}>
                    {field.field_type}
                  </span>
                </div>
                <div className="menu-item" onClick={() => { setActiveHeaderMenu(null); handleSort(field.key) }}>
                  {sortField === field.key && sortOrder === 'asc' ? '↓ 降序排列' : '↑ 升序排列'}
                </div>
                <div className="menu-item" onClick={() => handleToggleFreeze(field.key)}>
                  <Icon name={isFrozen ? 'unlock' : 'lock'} /> {isFrozen ? '取消冻结' : '冻结此列'}
                </div>
                <div className="menu-item" onClick={() => handleToggleFieldVisible(field.key)}>
                  隐藏此列
                </div>
                <div className="menu-item" onClick={() => openColumnStats(field.key)}>
                  <Icon name="chart" /> 统计此列
                </div>
                <div className="menu-divider" />
                <div className="menu-item" style={{ color: '#2563eb' }} onClick={() => openInsertAIDialog('text', field.key, 'before')}>
                  <Icon name="columns" /> 左侧插入新列
                </div>
                <div className="menu-item" style={{ color: '#2563eb' }} onClick={() => openInsertAIDialog('text', field.key, 'after')}>
                  <Icon name="columns" /> 右侧插入新列
                </div>
                <div className="menu-divider" />
                <div className="menu-item" style={{ color: '#dc2626' }} onClick={() => void handleDeleteColumnByKey(field.key)}>
                  <Icon name="trash" /> 从当前表格移除
                </div>
              </>
            )
          })()}
        </div>
      )}

      {/* AI 任务透明化浮动面板 */}
      {(activeAITasks.length > 0 || recentCompleted) && (
        <div style={{
          position: 'fixed', right: 20, bottom: 20, zIndex: 1000,
          width: aiPanelOpen ? 480 : 'auto',
          maxWidth: 'calc(100vw - 40px)',
          background: '#fff',
          border: '1px solid #e5e7eb',
          borderRadius: 8,
          boxShadow: '0 10px 25px rgba(0,0,0,0.15)',
          fontSize: 12,
          overflow: 'hidden',
        }}>
          {/* 头部 */}
          <div
            style={{
              padding: '8px 12px',
              background: activeAITasks.length > 0 ? '#1e40af' : '#10b981',
              color: '#fff',
              display: 'flex',
              justifyContent: 'space-between',
              alignItems: 'center',
              cursor: 'pointer',
              userSelect: 'none',
            }}
            onClick={() => setAiPanelOpen(!aiPanelOpen)}
          >
            <span style={{ fontWeight: 600 }}>
              {activeAITasks.length > 0
                ? <><Icon name="sparkles" size={14} /> AI 任务运行中 ({activeAITasks.length})</>
                : <><Icon name="check" size={14} /> AI 任务已完成</>}
            </span>
            <Icon name={aiPanelOpen ? 'chevron-down' : 'chevron-up'} size={14} />
          </div>
          {aiPanelOpen && (
            <div style={{ maxHeight: 420, overflowY: 'auto' }}>
              {/* 运行中任务 */}
              {activeAITasks.map(task => {
                const meta = taskMeta[task.id]
                const progress = task.total_items > 0 ? (task.processed_items / task.total_items) * 100 : 0
                return (
                  <div key={task.id} style={{ padding: 12, borderBottom: '1px solid #f3f4f6' }}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 6 }}>
                      <strong style={{ color: '#1f2937', fontSize: 13 }}>
                        {meta?.fieldName || task.field_key}
                      </strong>
                      <span style={{ color: '#6b7280', fontSize: 11 }}>
                        #{task.id} · <span style={{ color: '#3b82f6', fontWeight: 500 }}>{task.status}</span>
                      </span>
                    </div>
                    {/* 进度条 */}
                    <div style={{ background: '#f3f4f6', borderRadius: 3, height: 6, marginBottom: 6, overflow: 'hidden' }}>
                      <div style={{
                        width: `${progress}%`,
                        height: '100%',
                        background: 'linear-gradient(90deg, #3b82f6, #60a5fa)',
                        borderRadius: 3,
                        transition: 'width 0.3s',
                      }} />
                    </div>
                    <div style={{ fontSize: 11, color: '#6b7280', marginBottom: 8 }}>
                      进度：{task.processed_items} / {task.total_items}
                      （成功 {task.success_count}，失败 {task.failed_count}）
                    </div>
                    {meta && (
                      <>
                        <div style={{ marginBottom: 4, lineHeight: 1.5 }}>
                          <span style={{ color: '#374151', fontWeight: 500 }}>纳入的列：</span>
                          {meta.referencedColumns.length > 0 ? (
                            <span style={{ color: '#1e40af' }}>
                              {meta.referencedColumns.join('、')}
                            </span>
                          ) : (
                            <span style={{ color: '#9ca3af', fontStyle: 'italic' }}>
                              默认（标题、摘要、申请人、发明人）
                            </span>
                          )}
                        </div>
                        <div style={{ marginBottom: 4, lineHeight: 1.5 }}>
                          <span style={{ color: '#374151', fontWeight: 500 }}>输出位置：</span>
                          <code style={{ background: '#f3f4f6', padding: '1px 4px', borderRadius: 2, fontSize: 11, color: '#7c3aed' }}>
                            {meta.outputLocation}
                          </code>
                        </div>
                        {meta.prompt && (
                          <details style={{ marginTop: 4 }}>
                            <summary style={{ cursor: 'pointer', color: '#6b7280', fontSize: 11 }}>查看 Prompt</summary>
                            <pre style={{
                              background: '#f9fafb',
                              padding: 8,
                              borderRadius: 3,
                              fontSize: 11,
                              maxHeight: 100,
                              overflow: 'auto',
                              whiteSpace: 'pre-wrap',
                              margin: '4px 0 0',
                              border: '1px solid #e5e7eb',
                            }}>
                              {meta.prompt}
                            </pre>
                          </details>
                        )}
                      </>
                    )}
                  </div>
                )
              })}
              {/* 最近完成的任务 */}
              {recentCompleted && (
                <div style={{
                  padding: 12,
                  background: '#ecfdf5',
                  borderBottom: '1px solid #d1fae5',
                }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 6 }}>
                    <strong style={{ color: '#065f46', fontSize: 13 }}>
                      <Icon name="check" size={14} /> {recentCompleted.meta?.fieldName || 'AI 字段'}
                    </strong>
                    <span style={{ color: '#047857', fontSize: 11 }}>
                      #{recentCompleted.taskId} · 完成
                    </span>
                  </div>
                  <div style={{ fontSize: 11, color: '#047857', marginBottom: 4 }}>
                    {recentCompleted.task?.success_count || 0} 件成功 · {recentCompleted.task?.failed_count || 0} 件失败
                  </div>
                  <div style={{ fontSize: 11, color: '#065f46' }}>
                    结果已回填到表格，下方列表已自动刷新。
                  </div>
                </div>
              )}
            </div>
          )}
        </div>
      )}

      {activeView && showGroupConfig && (
        <GroupConfigPanel
          open
          view={activeView}
          fields={fields}
          onClose={() => setShowGroupConfig(false)}
          onSave={saveGroupConfig}
        />
      )}
      {activeView && showConditionalConfig && (
        <ConditionalFormatPanel
          open
          view={activeView}
          fields={fields}
          onClose={() => setShowConditionalConfig(false)}
          onSave={saveConditionalFormatting}
        />
      )}
      {showExportDialog && (
        <ExportDialog
          fields={fields}
          databaseId={activeDatabaseId}
          viewId={viewId}
          selectedIds={selectedIds}
          search={searchText}
          filters={filterValues as unknown as JsonObject}
          onClose={() => setShowExportDialog(false)}
        />
      )}
      {showWorkFileDialog && (
        <WorkFileDialog
          databaseId={activeDatabaseId}
          selectedIds={selectedIds}
          search={searchText}
          filters={filterValues as unknown as JsonObject}
          onClose={() => setShowWorkFileDialog(false)}
        />
      )}
    </div>
  )
}

function Modal({ title, children, onClose, width = 480 }: {
  title: string
  children: React.ReactNode
  onClose: () => void
  width?: number
}) {
  return (
    <div
      style={{
        position: 'fixed', top: 0, left: 0, right: 0, bottom: 0,
        background: 'rgba(0,0,0,0.45)', display: 'flex', alignItems: 'center', justifyContent: 'center',
        zIndex: 1000, padding: 20,
      }}
      onClick={onClose}
    >
      <div
        style={{
          background: 'white', borderRadius: 8, padding: 20, width: '100%', maxWidth: width,
          maxHeight: '90vh', overflowY: 'auto',
          boxShadow: '0 20px 60px rgba(0,0,0,0.15)',
        }}
        onClick={e => e.stopPropagation()}
      >
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
          <h3 style={{ margin: 0, fontSize: 15, fontWeight: 600, color: '#111827' }}>{title}</h3>
          <button
            onClick={onClose}
            style={{
              border: 'none', background: 'transparent', fontSize: 20, cursor: 'pointer',
              color: '#9ca3af', padding: 4, lineHeight: 1,
            }}
          >
            ×
          </button>
        </div>
        {children}
      </div>
    </div>
  )
}
