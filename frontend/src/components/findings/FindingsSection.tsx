import { useMemo, useState } from 'react'
import { humanize, shortSha } from '../../lib/format'
import { useFindings } from '../../lib/hooks'
import type { FindingFilters, FindingSort } from '../../types'
import { Card } from '../ui/Card'
import { Select } from '../ui/Field'
import { ClearFilters, FilterRow, NO_FILTER, ResultCount, activeFilterCount, orderOptions } from '../ui/Filters'
import { EmptyState, ErrorState, SkeletonRows } from '../ui/States'
import { FindingCard } from './FindingCard'

const NO_FINDING_FILTER: FindingFilters = {
  repo: NO_FILTER,
  language: NO_FILTER,
  commit: NO_FILTER,
  status: NO_FILTER,
  severity: NO_FILTER,
}

// Preferred display order; anything the database returns that is not listed is appended.
const STATUS_ORDER = ['open', 'resolved', 'invalid']
const SEVERITY_ORDER = ['critical', 'high', 'medium', 'low', 'info']

const SORTS: Array<{ value: FindingSort; label: string }> = [
  { value: 'severity', label: 'Severity' },
  { value: 'recent', label: 'Newest first' },
  { value: 'oldest', label: 'Oldest first' },
  { value: 'file', label: 'File' },
  { value: 'category', label: 'Category' },
  { value: 'project', label: 'Project' },
]

/**
 * Findings with server-side filtering and ordering.
 *
 * Every control here runs in SQL, not over a fetched array. `/api/dashboard` caps findings at the
 * 20 most severe rows, so filtering its payload would silently miss most matches - and language
 * and commit are not in that payload at all.
 *
 * Options come from the whole table, not the current result, so picking one filter never removes
 * the choices from the others.
 */
export function FindingsSection() {
  const [filters, setFilters] = useState<FindingFilters>(NO_FINDING_FILTER)
  const [sort, setSort] = useState<FindingSort>('severity')
  const { data, loading, error, reload } = useFindings(filters, sort)
  const options = data?.options

  const statuses = useMemo(() => orderOptions(options?.statuses ?? [], STATUS_ORDER), [options])
  const severities = useMemo(() => orderOptions(options?.severities ?? [], SEVERITY_ORDER), [options])

  const set = (key: keyof FindingFilters, value: string) =>
    setFilters((current) => ({ ...current, [key]: value }))
  const active = activeFilterCount(filters)

  return (
    <div className="space-y-3">
      <FilterRow>
        <Select label="Project" value={filters.repo} onChange={(e) => set('repo', e.target.value)}>
          <option value={NO_FILTER}>All projects</option>
          {(options?.projects ?? []).map((project) => (
            <option key={project} value={project}>
              {project}
            </option>
          ))}
        </Select>

        <Select
          label="Language"
          value={filters.language}
          onChange={(e) => set('language', e.target.value)}
        >
          <option value={NO_FILTER}>All languages</option>
          {(options?.languages ?? []).map((language) => (
            <option key={language} value={language}>
              {language}
            </option>
          ))}
        </Select>

        <Select label="Commit" value={filters.commit} onChange={(e) => set('commit', e.target.value)}>
          <option value={NO_FILTER}>All commits</option>
          {(options?.commits ?? []).map((entry) => (
            <option key={entry.sha} value={entry.sha}>
              {shortSha(entry.sha)} · {entry.repo}
            </option>
          ))}
        </Select>

        <Select label="Status" value={filters.status} onChange={(e) => set('status', e.target.value)}>
          <option value={NO_FILTER}>All statuses</option>
          {statuses.map((value) => (
            <option key={value} value={value}>
              {humanize(value)}
            </option>
          ))}
        </Select>

        <Select
          label="Severity"
          value={filters.severity}
          onChange={(e) => set('severity', e.target.value)}
        >
          <option value={NO_FILTER}>All severities</option>
          {severities.map((value) => (
            <option key={value} value={value}>
              {value}
            </option>
          ))}
        </Select>

        <Select
          label="Sort findings by"
          value={sort}
          onChange={(e) => setSort(e.target.value as FindingSort)}
        >
          {SORTS.map((option) => (
            <option key={option.value} value={option.value}>
              Sort: {option.label}
            </option>
          ))}
        </Select>

        <ClearFilters count={active} onClear={() => setFilters(NO_FINDING_FILTER)} />
      </FilterRow>

      {error && !data ? (
        <ErrorState message={error} onRetry={reload} />
      ) : loading && !data ? (
        <Card className="p-4">
          <SkeletonRows rows={4} />
        </Card>
      ) : !data || data.findings.length === 0 ? (
        <EmptyState
          title="No findings match these filters."
          hint={
            active > 0
              ? 'Try widening or clearing a filter.'
              : 'Findings appear here after a pull request is reviewed.'
          }
        />
      ) : (
        <>
          <ResultCount
            returned={data.returned}
            total={data.total}
            noun="finding"
            filtered={active > 0}
          />
          <Card>
            {data.findings.map((finding) => (
              <FindingCard key={finding.id} finding={finding} />
            ))}
          </Card>
        </>
      )}
    </div>
  )
}
