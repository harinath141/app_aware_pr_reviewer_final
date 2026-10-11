import { useState } from 'react'
import { cn } from '../../lib/cn'
import { count, humanize, shortSha, when } from '../../lib/format'
import { useFindings, useRepositoryCommits, useReviews } from '../../lib/hooks'
import { riskTone } from '../../lib/tones'
import type { FindingSort, Repository } from '../../types'
import { FindingCard } from '../findings/FindingCard'
import { Badge } from '../ui/Badge'
import { Card, CardHeader } from '../ui/Card'
import { Select } from '../ui/Field'
import { ResultCount } from '../ui/Filters'
import { SkeletonRows } from '../ui/States'
import { ExternalIcon } from '../ui/icons'

const SORTS: Array<{ value: FindingSort; label: string }> = [
  { value: 'severity', label: 'Severity' },
  { value: 'recent', label: 'Newest first' },
  { value: 'oldest', label: 'Oldest first' },
  { value: 'file', label: 'File' },
  { value: 'category', label: 'Category' },
]

const HEAD = 'px-3 py-2 text-[10px] font-semibold tracking-[0.08em] text-ink-muted uppercase'
const CELL = 'px-3 py-2.5 align-top text-xs text-ink-soft'

/**
 * One commit's reviews and findings.
 *
 * Mounted only once a commit is chosen, so its two requests are not issued for commits nobody
 * looked at.
 */
function CommitDetail({ repo, sha }: { repo: string; sha: string }) {
  const [sort, setSort] = useState<FindingSort>('severity')
  const [asTable, setAsTable] = useState(false)
  const reviews = useReviews({ repo, language: 'all', commit: sha, risk: 'all' })
  const findings = useFindings(
    { repo, language: 'all', commit: sha, status: 'all', severity: 'all' },
    sort,
  )

  return (
    <div className="space-y-3">
      <Card>
        <CardHeader title="Reviews on this commit" meta={`${count(reviews.data?.total ?? 0)} runs`} />
        {reviews.error ? (
          <p className="p-4 text-xs text-rose-700">{reviews.error}</p>
        ) : reviews.loading && !reviews.data ? (
          <div className="p-4">
            <SkeletonRows rows={2} />
          </div>
        ) : (reviews.data?.reviews.length ?? 0) === 0 ? (
          <p className="px-4 py-8 text-center text-xs text-ink-muted">
            No review runs recorded against this commit.
          </p>
        ) : (
          <ul>
            {reviews.data?.reviews.map((review) => (
              <li key={review.id} className="border-b border-line px-4 py-3 last:border-b-0">
                <div className="flex flex-wrap items-start justify-between gap-x-3 gap-y-1">
                  <div className="min-w-0">
                    <p className="text-xs font-medium text-ink">
                      PR #{review.pr_number} · {review.title || 'Untitled pull request'}
                    </p>
                    <p className="mt-0.5 text-[11px] text-ink-muted">
                      {when(review.reviewed_at)} · {count(review.findings)} findings ·{' '}
                      {humanize(review.recommendation, 'review required')}
                    </p>
                  </div>
                  <div className="flex items-center gap-2">
                    <Badge tone={riskTone(review.risk)}>{review.risk || 'unknown'}</Badge>
                    {review.url && (
                      <a
                        href={review.url}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="inline-flex items-center gap-1 text-[11px] font-medium text-accent hover:underline"
                      >
                        Open PR
                        <ExternalIcon />
                      </a>
                    )}
                  </div>
                </div>
              </li>
            ))}
          </ul>
        )}
      </Card>

      <Card>
        <CardHeader
          title="Findings on this commit"
          meta={
            <span className="flex items-center gap-2">
              <Select
                label="Sort findings by"
                className="py-1 text-[11px]"
                value={sort}
                onChange={(event) => setSort(event.target.value as FindingSort)}
              >
                {SORTS.map((option) => (
                  <option key={option.value} value={option.value}>
                    Sort: {option.label}
                  </option>
                ))}
              </Select>
              {findings.data && findings.data.findings.length > 0 && (
                <button
                  type="button"
                  onClick={() => setAsTable((value) => !value)}
                  aria-pressed={asTable}
                  className="rounded-md border border-line px-1.5 py-0.5 text-[10px] font-medium text-ink-muted transition-colors hover:bg-canvas hover:text-ink focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent"
                >
                  {asTable ? 'Cards' : 'Table'}
                </button>
              )}
            </span>
          }
        />

        {findings.error && !findings.data ? (
          <p className="p-4 text-xs text-rose-700">{findings.error}</p>
        ) : findings.loading && !findings.data ? (
          <div className="p-4">
            <SkeletonRows rows={4} />
          </div>
        ) : (findings.data?.findings.length ?? 0) === 0 ? (
          <p className="px-4 py-8 text-center text-xs text-ink-muted">
            No findings recorded against this commit.
          </p>
        ) : asTable ? (
          <div className="overflow-x-auto">
            <table className="w-full border-collapse text-left">
              <caption className="sr-only">Findings on this commit</caption>
              <thead>
                <tr className="border-b border-line bg-canvas/60">
                  {['Finding', 'Severity', 'Category', 'File', 'Status'].map((heading) => (
                    <th key={heading} scope="col" className={HEAD}>
                      {heading}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {findings.data?.findings.map((finding) => (
                  <tr key={finding.id} className="border-b border-line last:border-b-0">
                    <th scope="row" className={cn(CELL, 'font-medium text-ink')}>
                      {finding.title}
                    </th>
                    <td className={CELL}>
                      <Badge tone={riskTone(finding.severity)}>{finding.severity}</Badge>
                    </td>
                    <td className={CELL}>{humanize(finding.category, 'general')}</td>
                    <td className={cn(CELL, 'max-w-[14rem] truncate font-mono text-[11px]')}>
                      {finding.file || '—'}
                    </td>
                    <td className={CELL}>{finding.status}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <>
            <div className="px-4 pt-3">
              <ResultCount
                returned={findings.data?.returned ?? 0}
                total={findings.data?.total ?? 0}
                noun="finding"
                filtered={false}
              />
            </div>
            <div className="mt-1">
              {findings.data?.findings.map((finding) => (
                <FindingCard key={finding.id} finding={finding} />
              ))}
            </div>
          </>
        )}
      </Card>
    </div>
  )
}

export function ApplicationDetail({ repo }: { repo: Repository }) {
  const [commit, setCommit] = useState<string | null>(null)
  const { data, loading, error } = useRepositoryCommits(repo.name)

  const metrics = [
    { label: 'Files', value: count(repo.files) },
    { label: 'Knowledge chunks', value: count(repo.chunks) },
    { label: 'Code symbols', value: count(repo.symbols) },
    { label: 'Relationships', value: count(repo.edges) },
  ]

  return (
    <div className="space-y-3">
      <Card>
        <CardHeader
          title={repo.name}
          meta={<Badge tone="accent" caps={false}>{repo.language || 'Unknown'}</Badge>}
        />
        <div className="p-4">
          <p className="text-xs leading-relaxed text-ink-soft">
            {repo.description ||
              'No application description found. Add a README or manifest description to improve this profile.'}
          </p>
          <dl className="mt-4 grid grid-cols-2 gap-3 border-t border-line pt-3 sm:grid-cols-4">
            {metrics.map((metric) => (
              <div key={metric.label}>
                <dd className="text-sm font-semibold text-ink">{metric.value}</dd>
                <dt className="mt-0.5 text-[10px] leading-tight text-ink-muted">{metric.label}</dt>
              </div>
            ))}
          </dl>
          <p className="mt-3 text-[11px] text-ink-muted">
            Last indexed {when(repo.indexed_at)} · head <span className="font-mono">{shortSha(repo.latest_sha)}</span>
          </p>
        </div>
      </Card>

      <Card>
        <CardHeader title="Commits" meta="Newest first" />
        {error ? (
          <p className="p-4 text-xs text-rose-700">{error}</p>
        ) : loading && !data ? (
          <div className="p-4">
            <SkeletonRows rows={3} />
          </div>
        ) : (data?.commits.length ?? 0) === 0 ? (
          <p className="px-4 py-8 text-center text-xs text-ink-muted">
            No commits recorded for this application yet. They appear after a push is indexed or a
            pull request is reviewed.
          </p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full min-w-[620px] border-collapse text-left">
              <caption className="sr-only">Commits for this application, newest first</caption>
              <thead>
                <tr className="border-b border-line bg-canvas/60">
                  <th scope="col" className={HEAD}>
                    Commit
                  </th>
                  <th scope="col" className={HEAD}>
                    Reviewed
                  </th>
                  <th scope="col" className={HEAD}>
                    Indexed
                  </th>
                  <th scope="col" className={HEAD}>
                    Reviews
                  </th>
                  <th scope="col" className={HEAD}>
                    Findings
                  </th>
                </tr>
              </thead>
              <tbody>
                {data?.commits.map((entry) => {
                  const isActive = commit === entry.sha
                  return (
                    <tr
                      key={entry.sha}
                      onClick={() => setCommit(isActive ? null : entry.sha)}
                      className={cn(
                        'cursor-pointer border-b border-line last:border-b-0 transition-colors',
                        isActive ? 'bg-accent-soft' : 'hover:bg-canvas',
                      )}
                    >
                      <th scope="row" className={cn(CELL, 'font-mono font-normal text-ink')}>
                        {shortSha(entry.sha)}
                      </th>
                      <td className={cn(CELL, 'whitespace-nowrap')}>{when(entry.reviewed_at)}</td>
                      <td className={cn(CELL, 'whitespace-nowrap')}>{when(entry.indexed_at)}</td>
                      <td className={cn(CELL, 'tabular-nums')}>{count(entry.reviews)}</td>
                      <td className={cn(CELL, 'tabular-nums')}>
                        {entry.findings > 0 ? (
                          <span className="font-medium text-ink">{count(entry.findings)}</span>
                        ) : (
                          <span className="text-ink-muted">0</span>
                        )}
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        )}
        {data && data.commits.length > 0 && !commit && (
          <p className="border-t border-line px-4 py-3 text-[11px] text-ink-muted">
            Select a commit to see the reviews that ran against it and the findings they raised.
          </p>
        )}
      </Card>

      {commit && <CommitDetail key={commit} repo={repo.name} sha={commit} />}
    </div>
  )
}
