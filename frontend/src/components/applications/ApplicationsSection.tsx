import { useState } from 'react'
import { cn } from '../../lib/cn'
import { count, when } from '../../lib/format'
import type { Repository } from '../../types'
import { Badge } from '../ui/Badge'
import { Card } from '../ui/Card'
import { EmptyState, Skeleton } from '../ui/States'
import { ApplicationDetail } from './ApplicationDetail'

/**
 * Master-detail: pick an application on the left, and the right panel carries its profile, every
 * commit known for it (newest first), and - for whichever commit you pick - that commit's reviews
 * and findings. This is the only place reviews are shown; a review run belongs to a commit.
 */
export function ApplicationsSection({ repositories }: { repositories: Repository[] | null }) {
  const [selected, setSelected] = useState<string | null>(null)

  if (repositories === null) {
    return (
      <div className="grid gap-3 lg:grid-cols-[280px_minmax(0,1fr)]">
        <Skeleton className="h-72" />
        <Skeleton className="h-96" />
      </div>
    )
  }

  if (repositories.length === 0) {
    return (
      <EmptyState
        title="No indexed applications match these filters."
        hint="Connect a repository and push a commit to build its profile, or widen the filters above."
      />
    )
  }

  // Falls back to the first row when the selected application is filtered out.
  const active = repositories.find((repo) => repo.name === selected) ?? repositories[0]

  return (
    <div className="grid items-start gap-3 lg:grid-cols-[280px_minmax(0,1fr)]">
      <Card>
        <ul>
          {repositories.map((repo) => {
            const isActive = repo.name === active.name
            return (
              <li key={repo.name} className="border-b border-line last:border-b-0">
                <button
                  type="button"
                  onClick={() => setSelected(repo.name)}
                  aria-current={isActive ? 'true' : undefined}
                  className={cn(
                    'w-full px-3.5 py-3 text-left transition-colors',
                    'focus-visible:outline-2 focus-visible:-outline-offset-2 focus-visible:outline-accent',
                    isActive ? 'bg-accent-soft' : 'hover:bg-canvas',
                  )}
                >
                  <span className="flex items-start justify-between gap-2">
                    <span
                      className={cn(
                        'min-w-0 truncate text-sm font-medium',
                        isActive ? 'text-accent-strong' : 'text-ink',
                      )}
                      title={repo.name}
                    >
                      {repo.name}
                    </span>
                    <Badge tone="accent" caps={false} className="shrink-0">
                      {repo.language || 'Unknown'}
                    </Badge>
                  </span>
                  <span className="mt-1 block text-[11px] text-ink-muted">
                    {count(repo.files)} files · {count(repo.symbols)} symbols · {count(repo.edges)}{' '}
                    links
                  </span>
                  <span className="mt-0.5 block text-[11px] text-ink-muted">
                    Indexed {when(repo.indexed_at)}
                  </span>
                </button>
              </li>
            )
          })}
        </ul>
      </Card>

      {/* Keyed so switching application resets the selected commit rather than carrying it over. */}
      <ApplicationDetail key={active.name} repo={active} />
    </div>
  )
}
