import type { ComponentType } from 'react'
import { cn } from '../../lib/cn'
import { count } from '../../lib/format'
import type { DashboardStats } from '../../types'
import { Skeleton } from '../ui/States'
import {
  AppsIcon,
  BugIcon,
  CheckIcon,
  CloseIcon,
  FlameIcon,
  PullRequestIcon,
  ShieldIcon,
} from '../ui/icons'

interface Tile {
  key: keyof DashboardStats
  label: string
  hint: string
  Icon: ComponentType<{ className?: string }>
  /** Icon chip classes. Tones mirror the original dashboard's per-tile accents. */
  tone: string
}

const TILES: Tile[] = [
  {
    key: 'projects',
    label: 'Projects onboarded',
    hint: 'Repositories with indexed knowledge',
    Icon: AppsIcon,
    tone: 'bg-accent-soft text-accent',
  },
  {
    key: 'reviews',
    label: 'PR reviews done',
    hint: 'Recorded review runs',
    Icon: PullRequestIcon,
    tone: 'bg-sky-50 text-sky-600',
  },
  {
    key: 'issues_found',
    label: 'Issues found',
    hint: 'All review findings',
    Icon: BugIcon,
    tone: 'bg-amber-50 text-amber-600',
  },
  {
    key: 'security_issues',
    label: 'Security issues',
    hint: 'Tagged security / vulnerability',
    Icon: ShieldIcon,
    tone: 'bg-violet-50 text-violet-600',
  },
  {
    key: 'issues_fixed',
    label: 'Issues fixed',
    hint: 'Resolved by a /resolved reply',
    Icon: CheckIcon,
    tone: 'bg-emerald-50 text-emerald-600',
  },
  {
    key: 'issues_invalid',
    label: 'Invalid findings',
    hint: 'Marked a false positive via /invalid',
    Icon: CloseIcon,
    tone: 'bg-slate-100 text-slate-500',
  },
  {
    key: 'high_risk_open',
    label: 'Open high / critical',
    hint: 'Prioritize these first',
    Icon: FlameIcon,
    tone: 'bg-rose-50 text-rose-600',
  },
]

export function StatsSection({ stats }: { stats: DashboardStats | null }) {
  return (
    <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 xl:grid-cols-4">
      {TILES.map(({ key, label, hint, Icon, tone }) => (
        <div key={key} className="rounded-xl border border-line bg-surface p-4">
          <div className="flex items-start justify-between gap-2">
            <p className="text-xs font-medium text-ink-muted">{label}</p>
            <span className={cn('grid size-7 shrink-0 place-items-center rounded-lg', tone)}>
              <Icon className="size-3.5" />
            </span>
          </div>
          {/* Proportional figures on the value: tabular-nums is for columns that must align
              vertically, and makes a large standalone number look loose. */}
          {stats ? (
            <p className="mt-2.5 text-2xl font-semibold tracking-tight text-ink">
              {count(stats[key])}
            </p>
          ) : (
            <Skeleton className="mt-3 h-7 w-16" />
          )}
          <p className="mt-0.5 text-[11px] leading-relaxed text-ink-muted">{hint}</p>
        </div>
      ))}
    </div>
  )
}
