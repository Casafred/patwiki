function stableValue(value: unknown): string {
  const sortKeys = (item: unknown): unknown => {
    if (Array.isArray(item)) return item.map(sortKeys)
    if (item && typeof item === 'object') {
      return Object.fromEntries(
        Object.entries(item as Record<string, unknown>)
          .sort(([left], [right]) => left.localeCompare(right))
          .map(([key, nested]) => [key, sortKeys(nested)]),
      )
    }
    return item
  }
  return JSON.stringify(sortKeys(value)) ?? String(value)
}

export function mergeImportedCollectionValues(fieldKey: string, existing: unknown[], incoming: unknown[]) {
  if (fieldKey === 'original_links') {
    const merged: Record<string, unknown>[] = []
    const byIdentity = new Map<string, Record<string, unknown>>()
    for (const item of [...existing, ...incoming]) {
      if (!item || typeof item !== 'object' || Array.isArray(item)) continue
      const link = item as Record<string, unknown>
      const identity = stableValue([link.identifier_type ?? null, link.identifier_value ?? null])
      let target = byIdentity.get(identity)
      if (!target) {
        target = { ...link, urls: [], source_columns: [] }
        merged.push(target)
        byIdentity.set(identity, target)
      }
      for (const [key, values] of [
        ['urls', link.urls],
        ['source_columns', link.source_columns],
      ] as const) {
        const storedValues = target[key]
        const current: unknown[] = Array.isArray(storedValues) ? [...storedValues] : []
        const seen = new Set(current.map(stableValue))
        for (const value of Array.isArray(values) ? values : []) {
          const marker = stableValue(value)
          if (!seen.has(marker)) {
            current.push(value)
            seen.add(marker)
          }
        }
        target[key] = current
      }
    }
    return merged
  }

  const merged = [...existing]
  const seen = new Set(existing.map(stableValue))
  for (const value of incoming) {
    const marker = stableValue(value)
    if (!seen.has(marker)) {
      merged.push(value)
      seen.add(marker)
    }
  }
  return merged
}
