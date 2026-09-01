/** Parse API timestamps consistently.
 *
 * Legacy SQLite rows are serialized without an offset even though the
 * backend writes them in UTC. Date-only patent facts are kept as calendar
 * dates and are not shifted through a timezone conversion.
 */
export function parseApiDate(value?: string | null): Date | null {
  if (!value) return null
  const text = value.trim()
  if (!text) return null
  const dateOnly = /^\d{4}-\d{2}-\d{2}$/.test(text)
  if (dateOnly) {
    const [year, month, day] = text.split('-').map(Number)
    const calendarDate = new Date(year, month - 1, day)
    return Number.isNaN(calendarDate.getTime()) ? null : calendarDate
  }
  const normalized = text.includes(' ') ? text.replace(' ', 'T') : text
  const hasTimezone = /(?:Z|[+-]\d{2}:?\d{2})$/i.test(normalized)
  const parsed = new Date(hasTimezone ? normalized : `${normalized}Z`)
  return Number.isNaN(parsed.getTime()) ? null : parsed
}

export function formatApiDateTime(value?: string | null): string {
  const date = parseApiDate(value)
  return date ? date.toLocaleString('zh-CN') : value || '-'
}

export function formatApiDate(value?: string | null): string {
  const date = parseApiDate(value)
  return date ? date.toLocaleDateString('zh-CN') : value || '-'
}

export function formatApiTime(value?: string | null): string {
  const date = parseApiDate(value)
  return date ? date.toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit', second: '2-digit' }) : value || '-'
}
