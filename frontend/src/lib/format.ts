/** Display helpers, ported from the original dashboard's inline script. */

const EM_DASH = '—'

export function when(value?: string | null): string {
  if (!value) return EM_DASH
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return EM_DASH
  return date.toLocaleString([], { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' })
}

export function shortSha(sha?: string | null): string {
  return sha ? sha.slice(0, 8) : 'Not available'
}

/** `review_required` -> `review required`, so enum-ish values read as prose. */
export function humanize(value?: string | null, fallback = EM_DASH): string {
  if (!value) return fallback
  return value.replaceAll('_', ' ')
}

export function count(value?: number | null): string {
  return Number(value ?? 0).toLocaleString()
}

export function truncate(value: string | null | undefined, max: number): string {
  if (!value) return ''
  return value.length > max ? `${value.slice(0, max)}…` : value
}

/** Whole-percent share, for chart labels and the table twin. */
export function share(value: number, total: number): string {
  if (!total) return '—'
  return `${Math.round((value / total) * 100)}%`
}

/**
 * Pull a human message out of a FastAPI error body.
 *
 * HTTPException puts its payload under `detail`, which is either a plain string
 * (`HTTPException(403, "X-Admin-Token required")`) or an object
 * (`HTTPException(400, {"error": ..., "detail": ...})`). The original dashboard read only the
 * object form, so every string detail - including the admin-token rejection - was discarded and
 * replaced by a generic message.
 */
export function errorDetail(body: unknown, fallback: string): string {
  if (typeof body === 'string' && body.trim()) return body
  if (!body || typeof body !== 'object') return fallback

  const detail = (body as { detail?: unknown }).detail
  if (typeof detail === 'string' && detail.trim()) return detail
  if (detail && typeof detail === 'object') {
    const inner = detail as { detail?: unknown; error?: unknown }
    if (typeof inner.detail === 'string' && inner.detail.trim()) return inner.detail
    if (typeof inner.error === 'string' && inner.error.trim()) return inner.error
  }
  return fallback
}
