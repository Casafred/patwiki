import type { Tag } from '../types'

export function tagPath(tag: Tag, tags: Tag[]): string {
  const parts: string[] = []
  const seen = new Set<number>()
  let current: Tag | undefined = tag
  while (current && !seen.has(current.id)) {
    seen.add(current.id)
    parts.unshift(current.name)
    current = tags.find(item => item.id === current?.parent_id)
  }
  return parts.join(' / ')
}
