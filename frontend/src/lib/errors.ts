function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null
}

export function getErrorMessage(error: unknown, fallback = ''): string {
  const record = isRecord(error) ? error : null
  const response = record && isRecord(record.response) ? record.response : null
  const data = response && isRecord(response.data) ? response.data : null
  const candidates = [data?.message, data?.detail, record?.message]
  const message = candidates.find((value): value is string => typeof value === 'string' && value.length > 0)
  if (message) return message
  if (error instanceof Error && error.message) return error.message
  return fallback
}
