/** 本机当日「浏览 + 编辑」记录。
 *
 * 纯前端 localStorage 存储，用于帮助用户找回“今天看过 / 改过哪些专利的 Wiki
 * 详情”。按本地自然日归类：每次读取和写入都会剔除不在今天的记录，因此记录随
 * 次日自动清空，不会无限增长。跨标签页通过 storage 事件保持同步。
 */
import { useSyncExternalStore } from 'react'

const STORAGE_KEY = 'patwiki:daily-history:v1'
const MAX_RECORDS = 500

export interface DailyHistoryRecord {
  patentId: number
  title: string
  publicationNumber?: string
  applicationNumber?: string
  applicant?: string
  databaseId?: number | null
  /** 浏览时所在的详情页地址（含查询串），用于一键回到该专利。 */
  sourcePath?: string
  firstViewedAt: number
  /** 最近一次浏览时间（毫秒时间戳）。 */
  viewedAt: number
  viewCount: number
  /** 最近一次编辑时间，未编辑过为 null。 */
  editedAt?: number | null
  editCount: number
}

export interface DailyHistoryInput {
  patentId: number
  title: string
  publicationNumber?: string
  applicationNumber?: string
  applicant?: string
  databaseId?: number | null
  sourcePath?: string
}

function startOfToday(): number {
  const now = new Date()
  return new Date(now.getFullYear(), now.getMonth(), now.getDate()).getTime()
}

function isToday(timestamp: number | null | undefined, dayStart: number): boolean {
  return typeof timestamp === 'number' && timestamp >= dayStart
}

function lastActiveAt(record: DailyHistoryRecord): number {
  return Math.max(record.viewedAt || 0, record.editedAt || 0)
}

function normalizeStored(value: unknown): DailyHistoryRecord | null {
  if (!value || typeof value !== 'object') return null
  const item = value as Record<string, unknown>
  const patentId = Number(item.patentId)
  if (!Number.isInteger(patentId) || patentId <= 0) return null
  const viewedAt = Number(item.viewedAt)
  const firstViewedAt = Number(item.firstViewedAt)
  const editedAt = item.editedAt == null ? null : Number(item.editedAt)
  return {
    patentId,
    title: typeof item.title === 'string' ? item.title : `专利 #${patentId}`,
    publicationNumber: typeof item.publicationNumber === 'string' ? item.publicationNumber : undefined,
    applicationNumber: typeof item.applicationNumber === 'string' ? item.applicationNumber : undefined,
    applicant: typeof item.applicant === 'string' ? item.applicant : undefined,
    databaseId: item.databaseId == null ? null : Number(item.databaseId),
    sourcePath: typeof item.sourcePath === 'string' ? item.sourcePath : undefined,
    firstViewedAt: Number.isFinite(firstViewedAt) ? firstViewedAt : viewedAt,
    viewedAt: Number.isFinite(viewedAt) ? viewedAt : Date.now(),
    viewCount: Number.isFinite(Number(item.viewCount)) ? Math.max(1, Number(item.viewCount)) : 1,
    editedAt: editedAt != null && Number.isFinite(editedAt) ? editedAt : null,
    editCount: Number.isFinite(Number(item.editCount)) ? Math.max(0, Number(item.editCount)) : 0,
  }
}

function readRaw(): DailyHistoryRecord[] {
  if (typeof localStorage === 'undefined') return []
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    if (!raw) return []
    const parsed: unknown = JSON.parse(raw)
    if (!Array.isArray(parsed)) return []
    return parsed.map(normalizeStored).filter((record): record is DailyHistoryRecord => record !== null)
  } catch {
    return []
  }
}

function prune(records: DailyHistoryRecord[], dayStart: number): DailyHistoryRecord[] {
  return sortRecords(records.filter(record => isToday(lastActiveAt(record), dayStart))).slice(0, MAX_RECORDS)
}

function sortRecords(records: DailyHistoryRecord[]): DailyHistoryRecord[] {
  return [...records].sort((a, b) => lastActiveAt(b) - lastActiveAt(a))
}

let cache: DailyHistoryRecord[] | null = null
let cacheDayStart = 0
const listeners = new Set<() => void>()

function ensureCache(): DailyHistoryRecord[] {
  const dayStart = startOfToday()
  if (cache && cacheDayStart === dayStart) return cache
  cache = prune(readRaw(), dayStart)
  cacheDayStart = dayStart
  return cache
}

function getSnapshot(): DailyHistoryRecord[] {
  return ensureCache()
}

const EMPTY: DailyHistoryRecord[] = []
function getServerSnapshot(): DailyHistoryRecord[] {
  return EMPTY
}

function commit(next: DailyHistoryRecord[]): void {
  cache = prune(next, startOfToday())
  cacheDayStart = startOfToday()
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(cache))
  } catch {
    // 存储不可用（隐私模式 / 配额耗尽）时仍更新内存，保证当前会话可用。
  }
  listeners.forEach(listener => listener())
}

function upsert(input: DailyHistoryInput, mutate: (record: DailyHistoryRecord, now: number) => DailyHistoryRecord): void {
  const now = Date.now()
  const current = ensureCache().slice()
  const index = current.findIndex(record => record.patentId === input.patentId)
  if (index >= 0) {
    current[index] = mutate(current[index], now)
  } else {
    const created: DailyHistoryRecord = {
      patentId: input.patentId,
      title: input.title || `专利 #${input.patentId}`,
      publicationNumber: input.publicationNumber,
      applicationNumber: input.applicationNumber,
      applicant: input.applicant,
      databaseId: input.databaseId ?? null,
      sourcePath: input.sourcePath,
      firstViewedAt: now,
      viewedAt: now,
      viewCount: 1,
      editedAt: null,
      editCount: 0,
    }
    current.push(mutate(created, now))
  }
  commit(sortRecords(current))
}

/** 记录一次专利详情浏览（同一天重复浏览累加次数并刷新时间）。 */
export function recordBrowse(input: DailyHistoryInput): void {
  upsert(input, (record, now) => ({
    ...record,
    title: input.title || record.title,
    publicationNumber: input.publicationNumber ?? record.publicationNumber,
    applicationNumber: input.applicationNumber ?? record.applicationNumber,
    applicant: input.applicant ?? record.applicant,
    databaseId: input.databaseId ?? record.databaseId,
    sourcePath: input.sourcePath ?? record.sourcePath,
    viewedAt: now,
    viewCount: record.viewCount + 1,
  }))
}

/** 记录一次专利编辑（保存成功后调用）。 */
export function recordEdit(input: DailyHistoryInput): void {
  upsert(input, (record, now) => ({
    ...record,
    title: input.title || record.title,
    publicationNumber: input.publicationNumber ?? record.publicationNumber,
    applicationNumber: input.applicationNumber ?? record.applicationNumber,
    applicant: input.applicant ?? record.applicant,
    databaseId: input.databaseId ?? record.databaseId,
    sourcePath: input.sourcePath ?? record.sourcePath,
    editedAt: now,
    editCount: record.editCount + 1,
  }))
}

/** 清空当天记录（历史记录按天存储，清空即移除全部）。 */
export function clearDailyHistory(): void {
  commit([])
}

function handleStorage(event: StorageEvent): void {
  if (event.key !== null && event.key !== STORAGE_KEY) return
  cache = null
  listeners.forEach(listener => listener())
}

let storageBound = false

export function subscribe(listener: () => void): () => void {
  listeners.add(listener)
  if (!storageBound && typeof window !== 'undefined') {
    window.addEventListener('storage', handleStorage)
    storageBound = true
  }
  return () => {
    listeners.delete(listener)
  }
}

export function useDailyHistory(): DailyHistoryRecord[] {
  return useSyncExternalStore(subscribe, getSnapshot, getServerSnapshot)
}

/** 列表项展示用：返回该记录最近一次活跃时间。 */
export function recordLastActiveAt(record: DailyHistoryRecord): number {
  return lastActiveAt(record)
}