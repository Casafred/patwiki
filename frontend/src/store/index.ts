import { create } from 'zustand'
import type { Patent, Product, CustomField, Tag, Project, PatentDatabase, User, PatentView } from '../types'

const CURRENT_USER_STORAGE_KEY = 'patwiki_current_user'
const CURRENT_VIEW_STORAGE_KEY_PREFIX = 'patwiki_current_view_'
const GROUP_BY_FAMILY_STORAGE_KEY = 'patwiki_group_by_family'

interface AppState {
  patents: Patent[]
  totalPatents: number
  products: Product[]
  customFields: CustomField[]
  tags: Tag[]
  projects: Project[]
  // P0-11：库相关
  databases: PatentDatabase[]
  currentDatabaseId: number | null
  setDatabases: (databases: PatentDatabase[]) => void
  setCurrentDatabaseId: (id: number | null) => void
  // P0-14：视图相关
  views: PatentView[]
  currentViewId: number | null  // null = 显示大表（无视图筛选）
  setViews: (views: PatentView[]) => void
  setCurrentViewId: (id: number | null) => void
  currentProductId: number | null
  loading: boolean
  selectedIds: number[]
  filters: Record<string, any>
  // 权限管理 MVP：当前用户（localStorage 持久化）
  currentUser: User | null
  setCurrentUser: (user: User | null) => void
  // P2-8：同族聚拢（列表页"一键聚拢同族"切换，localStorage 持久化）
  groupByFamily: boolean
  setGroupByFamily: (v: boolean) => void
  setPatents: (patents: Patent[], total: number) => void
  setProducts: (products: Product[]) => void
  setCustomFields: (fields: CustomField[]) => void
  setTags: (tags: Tag[]) => void
  setProjects: (projects: Project[]) => void
  setCurrentProductId: (id: number | null) => void
  setLoading: (loading: boolean) => void
  setSelectedIds: (ids: number[]) => void
  setFilters: (filters: Record<string, any>) => void
  toggleSelect: (id: number) => void
  clearSelection: () => void
}

function loadCurrentUserFromStorage(): User | null {
  try {
    const raw = localStorage.getItem(CURRENT_USER_STORAGE_KEY)
    if (!raw) return null
    return JSON.parse(raw) as User
  } catch {
    return null
  }
}

// P0-14：当前视图 ID 按库 ID 持久化（每个库记住上次切到的视图）
function loadCurrentViewIdFromStorage(databaseId: number | null): number | null {
  if (databaseId == null) return null
  try {
    const raw = localStorage.getItem(CURRENT_VIEW_STORAGE_KEY_PREFIX + String(databaseId))
    if (!raw) return null
    const parsed = JSON.parse(raw)
    return typeof parsed === 'number' ? parsed : null
  } catch {
    return null
  }
}

function saveCurrentViewIdToStorage(databaseId: number | null, viewId: number | null) {
  if (databaseId == null) return
  const key = CURRENT_VIEW_STORAGE_KEY_PREFIX + String(databaseId)
  try {
    if (viewId == null) {
      localStorage.removeItem(key)
    } else {
      localStorage.setItem(key, JSON.stringify(viewId))
    }
  } catch {}
}

export const useAppStore = create<AppState>((set, get) => ({
  patents: [],
  totalPatents: 0,
  products: [],
  customFields: [],
  tags: [],
  projects: [],
  databases: [],
  currentDatabaseId: null,
  setDatabases: (databases) => set({ databases }),
  setCurrentDatabaseId: (currentDatabaseId) => set({
    currentDatabaseId,
    // 切换库时重置当前视图：先恢复该库上次记住的视图 ID，由调用方后续 setViews 后再决定是否有效
    currentViewId: loadCurrentViewIdFromStorage(currentDatabaseId),
    views: [],
  }),
  // P0-14：视图状态
  views: [],
  currentViewId: null,
  setViews: (views) => set({ views }),
  setCurrentViewId: (viewId) => {
    const { currentDatabaseId } = get()
    saveCurrentViewIdToStorage(currentDatabaseId, viewId)
    set({ currentViewId: viewId })
  },
  currentProductId: null,
  loading: false,
  selectedIds: [],
  filters: {},
  currentUser: loadCurrentUserFromStorage(),
  setCurrentUser: (user) => {
    if (user) {
      try { localStorage.setItem(CURRENT_USER_STORAGE_KEY, JSON.stringify(user)) } catch {}
    } else {
      try { localStorage.removeItem(CURRENT_USER_STORAGE_KEY) } catch {}
    }
    set({ currentUser: user })
  },

  // P2-8：同族聚拢 —— 默认关闭，localStorage 持久化用户偏好
  groupByFamily: (() => {
    try { return localStorage.getItem(GROUP_BY_FAMILY_STORAGE_KEY) === 'true' } catch { return false }
  })(),
  setGroupByFamily: (v) => {
    try { localStorage.setItem(GROUP_BY_FAMILY_STORAGE_KEY, String(v)) } catch {}
    set({ groupByFamily: v })
  },

  setPatents: (patents, total) => set({ patents, totalPatents: total }),
  setProducts: (products) => set({ products }),
  setCustomFields: (customFields) => set({ customFields }),
  setTags: (tags) => set({ tags }),
  setProjects: (projects) => set({ projects }),
  setCurrentProductId: (currentProductId) => set({ currentProductId }),
  setLoading: (loading) => set({ loading }),
  setSelectedIds: (selectedIds) => set({ selectedIds }),
  setFilters: (filters) => set({ filters }),

  toggleSelect: (id) => {
    const { selectedIds } = get()
    if (selectedIds.includes(id)) {
      set({ selectedIds: selectedIds.filter((i) => i !== id) })
    } else {
      set({ selectedIds: [...selectedIds, id] })
    }
  },

  clearSelection: () => set({ selectedIds: [] }),
}))
