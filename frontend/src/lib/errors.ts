function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null
}

export function getErrorMessage(error: unknown, fallback = ''): string {
  if (error instanceof Error && error.message) return error.message
  if (!isRecord(error)) return fallback

  const response = isRecord(error.response) ? error.response : null
  const data = response && isRecord(response.data) ? response.data : null
  const candidates = [data?.detail, data?.message, error.message]
  const message = candidates.find((value): value is string => typeof value === 'string' && value.length > 0)
  return message || fallback
}
