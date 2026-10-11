import { useId, useState } from 'react'
import { cn } from '../../lib/cn'
import { humanize, when } from '../../lib/format'
import { severityTone, statusTone } from '../../lib/tones'
import type { Finding } from '../../types'
import { Badge } from '../ui/Badge'
import { ChevronDownIcon, ExternalIcon } from '../ui/icons'

function Detail({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <p className="text-[10px] font-semibold tracking-[0.08em] text-ink-muted uppercase">{label}</p>
      <p className="mt-1 text-xs leading-relaxed whitespace-pre-line text-ink-soft">{value}</p>
    </div>
  )
}

export function FindingCard({ finding }: { finding: Finding }) {
  const [expanded, setExpanded] = useState(false)
  const panelId = useId()

  const location = [finding.file || 'File not specified', finding.anchor_line ?? finding.line]
    .filter((part) => part !== undefined && part !== null && part !== '')
    .join(' · line ')

  const details = [
    { label: 'Evidence', value: finding.evidence },
    { label: 'Failure scenario', value: finding.scenario },
    { label: 'Impact', value: finding.impact },
    { label: 'Recommendation', value: finding.recommendation },
  ].filter((entry): entry is { label: string; value: string } => Boolean(entry.value))

  return (
    <article className="border-b border-line last:border-b-0">
      <button
        type="button"
        onClick={() => setExpanded((value) => !value)}
        aria-expanded={expanded}
        aria-controls={panelId}
        className="flex w-full items-start gap-2.5 px-4 py-3.5 text-left transition-colors hover:bg-canvas/60 focus-visible:outline-2 focus-visible:-outline-offset-2 focus-visible:outline-accent"
      >
        <ChevronDownIcon
          className={cn(
            'mt-1 shrink-0 text-ink-muted transition-transform',
            expanded && 'rotate-180',
          )}
        />
        <span className="min-w-0 flex-1">
          <span className="flex items-start justify-between gap-3">
            <span className="text-sm font-medium text-ink">{finding.title}</span>
            <Badge tone={statusTone(finding.status)} className="shrink-0">
              {finding.status}
            </Badge>
          </span>
          <span className="mt-1.5 flex flex-wrap items-center gap-x-2 gap-y-1 text-[11px] text-ink-muted">
            <Badge tone={severityTone(finding.severity)}>{finding.severity}</Badge>
            <span>{humanize(finding.category, 'general')}</span>
            <span aria-hidden="true">·</span>
            <span>
              {finding.repo} · PR #{finding.pr_number}
            </span>
            <span aria-hidden="true">·</span>
            <span>{when(finding.created_at)}</span>
          </span>
          <span className="mt-1.5 block truncate font-mono text-[11px] text-ink-muted" title={finding.file ?? undefined}>
            {location}
          </span>
        </span>
      </button>

      {expanded && (
        <div id={panelId} className="space-y-3.5 border-t border-line bg-canvas/50 px-4 py-4 pl-10">
          {details.length === 0 && (
            <p className="text-xs text-ink-muted">No further detail was recorded for this finding.</p>
          )}
          {details.map((entry) => (
            <Detail key={entry.label} label={entry.label} value={entry.value} />
          ))}

          <div className="flex flex-wrap items-center gap-x-4 gap-y-2 pt-0.5">
            {finding.comment_url && (
              <a
                href={finding.comment_url}
                target="_blank"
                rel="noopener noreferrer"
                className="inline-flex items-center gap-1 text-xs font-medium text-accent hover:underline"
              >
                Open comment
                <ExternalIcon />
              </a>
            )}
            {finding.status !== 'open' && finding.status_actor && (
              <span className="text-[11px] text-ink-muted">
                {humanize(finding.status)} by @{finding.status_actor}
                {finding.status_updated_at ? ` · ${when(finding.status_updated_at)}` : ''}
              </span>
            )}
          </div>
        </div>
      )}
    </article>
  )
}
