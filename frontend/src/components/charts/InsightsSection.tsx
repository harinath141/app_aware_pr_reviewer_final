import { when } from '../../lib/format'
import type { DashboardData } from '../../types'
import { Skeleton } from '../ui/States'
import { ChartCard } from './ChartCard'
import type { Datum } from './ChartCard'

const SERIES = 'var(--viz-series)'
const MAX_BARS = 8

function dayLabel(value: string | null): string {
  if (!value) return '—'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return '—'
  return date.toLocaleDateString([], { month: 'short', day: 'numeric' })
}

function timeLabel(value: string | null): string {
  if (!value) return '—'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return '—'
  return date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
}

/**
 * Every card here is built from data that is complete for its question.
 *
 * Two charts that used to sit here - findings by severity and by category - were removed rather
 * than fixed: they were derived from `/api/dashboard`'s findings array, which is capped at the 20
 * most severe rows, so a distribution over it would have overstated the severe end while reading
 * as the whole population. Use the filterable findings table for that, which queries the database
 * directly.
 */
export function InsightsSection({ data }: { data: DashboardData | null }) {
  // Placeholder cards keep the page height stable while the first response is in flight.
  if (!data) {
    return (
      <div className="grid gap-3 lg:grid-cols-2">
        {Array.from({ length: 4 }, (_, index) => (
          <Skeleton key={index} className="h-56" />
        ))}
      </div>
    )
  }

  const { stats, languages, repositories, reviews } = data

  // Complete: derived from SQL aggregates over the whole table.
  const triage: Datum[] = [
    { label: 'Resolved', value: stats.issues_fixed, color: 'var(--viz-resolved)' },
    { label: 'Open', value: stats.issues_open, color: 'var(--viz-open)' },
    { label: 'Invalid', value: stats.issues_invalid, color: 'var(--viz-invalid)' },
  ]

  const languageBars: Datum[] = languages
    .slice(0, MAX_BARS)
    .map((entry) => ({ label: entry.name || 'Unknown', value: entry.count, color: SERIES }))

  // Sorted oldest-first rather than assuming the response order, so time always runs left to right.
  const ordered = [...reviews].sort(
    (a, b) => Date.parse(a.reviewed_at ?? '') - Date.parse(b.reviewed_at ?? ''),
  )
  // Several review runs commonly land on the same day, which would print the same axis label
  // three times. Fall back to the clock time when the dates alone do not distinguish the points.
  const sameDay = new Set(ordered.map((review) => dayLabel(review.reviewed_at))).size < ordered.length
  const activity: Datum[] = ordered.map((review) => ({
    label: sameDay ? timeLabel(review.reviewed_at) : dayLabel(review.reviewed_at),
    value: review.findings,
    color: SERIES,
    hint: `${review.repo} PR #${review.pr_number} · ${when(review.reviewed_at)}`,
  }))

  return (
    <div className="grid items-start gap-3 lg:grid-cols-2">
      <ChartCard
        title="Finding triage"
        meta={`All ${stats.issues_found.toLocaleString()} findings`}
        data={triage}
        variant="stack"
        emptyText="No findings recorded yet."
        note="Every finding the reviewer has raised, split by whether a human has settled it. Status is set on GitHub, never here."
      />

      <ChartCard
        title="Repositories by language"
        meta={`${repositories.length.toLocaleString()} indexed`}
        data={languageBars}
        variant="bars"
        emptyText="No repositories indexed yet."
      />

      <ChartCard
        title="Findings raised per review"
        meta="Last 12 reviews"
        data={activity}
        variant="columns"
        emptyText="No reviews recorded yet."
        note={`A recent window, not full history — the API returns the twelve most recent review runs.${
          sameDay ? ' Times are shown because several runs share a date.' : ''
        }`}
      />

    </div>
  )
}
