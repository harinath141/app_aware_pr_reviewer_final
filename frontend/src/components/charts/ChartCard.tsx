import { useState } from 'react'
import type { ReactNode } from 'react'
import { cn } from '../../lib/cn'
import { count, share } from '../../lib/format'
import { Card, CardHeader } from '../ui/Card'
import { BarList } from './BarList'
import { ColumnChart } from './ColumnChart'
import { StackedBar } from './StackedBar'

export interface Datum {
  label: string
  value: number
  /** A validated palette value. Always a CSS var reference, never a raw hex. */
  color: string
  /** Extra context for the tooltip and table (repo, PR, date…). */
  hint?: string
  /** Replaces the formatted value, e.g. "66%" where the value is a rate rather than a count. */
  display?: string
}

type Variant = 'columns' | 'bars' | 'stack'

interface ChartCardProps {
  title: string
  meta?: string
  data: Datum[]
  variant: Variant
  /** Shown instead of the chart when every value is zero. */
  emptyText?: string
  note?: ReactNode
  className?: string
  /** Set false when values are already rates, where a share-of-total column means nothing. */
  showShare?: boolean
  /** Scale bars against this instead of the largest value — pass 100 for percentages. */
  scaleMax?: number
}

/** Values are counts unless a datum supplies its own formatting. */
export function formatDatum(datum: Datum): string {
  return datum.display ?? count(datum.value)
}

function DatumTable({
  data,
  total,
  showShare,
}: {
  data: Datum[]
  total: number
  showShare: boolean
}) {
  const head = 'py-2 text-[10px] font-semibold tracking-[0.08em] text-ink-muted uppercase'
  const usesRates = data.some((datum) => datum.display !== undefined)
  return (
    <table className="w-full border-collapse">
      <caption className="sr-only">Chart values as a table</caption>
      <thead>
        <tr className="border-b border-line">
          <th scope="col" className={cn(head, 'text-left')}>
            Category
          </th>
          <th scope="col" className={cn(head, 'text-right')}>
            {usesRates ? 'Value' : 'Count'}
          </th>
          {showShare && (
            <th scope="col" className={cn(head, 'pl-3 text-right')}>
              Share
            </th>
          )}
        </tr>
      </thead>
      <tbody>
        {data.map((datum) => (
          <tr key={datum.label} className="border-b border-line last:border-b-0">
            <th scope="row" className="py-2 pr-3 text-left text-xs font-normal text-ink-soft">
              <span className="flex items-center gap-2">
                <span
                  aria-hidden="true"
                  className="size-2.5 shrink-0 rounded-sm"
                  style={{ background: datum.color }}
                />
                <span className="min-w-0">
                  {datum.label}
                  {datum.hint && (
                    <span className="block truncate text-[10px] text-ink-muted">{datum.hint}</span>
                  )}
                </span>
              </span>
            </th>
            <td className="py-2 text-right text-xs tabular-nums text-ink">{formatDatum(datum)}</td>
            {showShare && (
              <td className="py-2 pl-3 text-right text-xs tabular-nums text-ink-muted">
                {share(datum.value, total)}
              </td>
            )}
          </tr>
        ))}
      </tbody>
    </table>
  )
}

export function ChartCard({
  title,
  meta,
  data,
  variant,
  emptyText = 'Nothing recorded yet.',
  note,
  className,
  showShare = true,
  scaleMax,
}: ChartCardProps) {
  const [asTable, setAsTable] = useState(false)
  const total = data.reduce((sum, datum) => sum + datum.value, 0)

  return (
    <Card className={className}>
      <CardHeader
        title={title}
        meta={
          <span className="flex items-center gap-2">
            {meta && <span className="text-xs text-ink-muted">{meta}</span>}
            {total > 0 && (
              // Every chart has a table twin, so no value is reachable only by reading a shape.
              <button
                type="button"
                onClick={() => setAsTable((value) => !value)}
                aria-pressed={asTable}
                className="rounded-md border border-line px-1.5 py-0.5 text-[10px] font-medium text-ink-muted transition-colors hover:bg-canvas hover:text-ink focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent"
              >
                {asTable ? 'Chart' : 'Table'}
              </button>
            )}
          </span>
        }
      />
      <div className="p-4">
        {total === 0 ? (
          <p className="py-5 text-center text-xs text-ink-muted">{emptyText}</p>
        ) : asTable ? (
          <DatumTable data={data} total={total} showShare={showShare} />
        ) : variant === 'columns' ? (
          <ColumnChart data={data} scaleMax={scaleMax} />
        ) : variant === 'bars' ? (
          <BarList data={data} total={total} showShare={showShare} scaleMax={scaleMax} />
        ) : (
          <StackedBar data={data} total={total} />
        )}
      </div>
      {note && <p className="px-4 pb-4 text-[11px] leading-relaxed text-ink-muted">{note}</p>}
    </Card>
  )
}
