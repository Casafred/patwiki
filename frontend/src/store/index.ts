import { create } from 'zustand'
import type { Patent, Product, CustomField, Tag, Project, PatentDatabase, User } from '../types'

const CURRENT_USER_STORAGE_KEY = 'patwiki_current_user'
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
  currentProductId: number | null
  loading: boolean
  selectedIds: number[]
  filters: Record<string, any>
  // P2-8：同族聚拢开关（localStorage 持久化）
  groupByFamily: boolean
  setGroupByFamily: (v: boolean) => void
  // 权限管理 MVP：当前用户（localStorage 持久化）
  currentUser: User | null
  setCurrentUser: (user: User | null) => void
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
  setCurrentDatabaseId: (currentDatabaseId) => set({ currentDatabaseId }),
  currentProductId: null,
  loading: false,
  selectedIds: [],
  filters: {},
  // P2-8：同族聚拢开关，初始值从 localStorage 读取
  groupByFamily: (() => {
    try { return localStorage.getItem(GROUP_BY_FAMILY_STORAGE_KEY) === 'true' } catch { return false }
  })(),
  setGroupByFamily: (v) => {
    try { localStorage.setItem(GROUP_BY_FAMILY_STORAGE_KEY, String(v)) } catch {}
    set({ groupByFamily: v })
  },
  currentUser: loadCurrentUserFromStorage(),
  setCurrentUser: (user) => {
    if (user) {
      try { localStorage.setItem(CURRENT_USER_STORAGE_KEY, JSON.stringify(user)) } catch {}
    } else {
      try { localStorage.removeItem(CURRENT_USER_STORAGE_KEY) } catch {}
    }
    set({ currentUser: user })
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
