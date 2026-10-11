import type { ReactNode } from 'react'
import { Button } from './Button'

/** Sentinel the UI and the API both read as "no filter". */
export const NO_FILTER = 'all'

/**
 * Preferred display order for a set of values, with anything unrecognised appended rather than
 * dropped - the database is the source of truth for which values exist, this only sorts them.
 */
export function orderOptions(available: string[], preferred: string[]): string[] {
  return [
    ...preferred.filter((value) => available.includes(value)),
    ...available.filter((value) => !preferred.includes(value)),
  ]
}

/**
 * Counts the filters actually applied, so "Clear" only appears when it would do something.
 * Takes `object` rather than `Record<string, string>`: a named interface has no implicit index
 * signature, so the narrower type would reject every filter shape passed to it.
 */
export function activeFilterCount(filters: object): number {
  return Object.values(filters).filter((value) => value !== NO_FILTER).length
}

export function FilterRow({ children }: { children: ReactNode }) {
  return <div className="flex flex-wrap items-center gap-2">{children}</div>
}

export function ClearFilters({ count, onClear }: { count: number; onClear: () => void }) {
  if (count === 0) return null
  return (
    <Button size="sm" onClick={onClear}>
      Clear {count} filter{count === 1 ? '' : 's'}
    </Button>
  )
}

/** The count line above a filtered list, phrased the same way everywhere. */
export function ResultCount({
  returned,
  total,
  noun,
  filtered,
}: {
  returned: number
  total: number
  noun: string
  filtered: boolean
}) {
  return (
    <p className="text-xs text-ink-muted">
      Showing {returned.toLocaleString()} of {total.toLocaleString()} {noun}
      {total === 1 ? '' : 's'}
      {filtered ? ' matching these filters' : ''}.
    </p>
  )
}
