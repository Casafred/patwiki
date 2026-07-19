import { create } from 'zustand'
import type { Patent, Product, CustomField, Tag, Project, PatentDatabase } from '../types'

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
