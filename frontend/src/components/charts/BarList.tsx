import { share } from '../../lib/format'
import { formatDatum } from './ChartCard'
import type { Datum } from './ChartCard'

/**
 * Horizontal bars for nominal categories with long names. One series, so every bar takes the same
 * hue - colouring each bar by its own value would spend the identity channel re-encoding what bar
 * length already shows. Values are direct-labelled, so nothing is hover-gated.
 *
 * Bars are scaled against the largest value, not the total: the question is "which is biggest",
 * and the share column already carries the part-to-whole reading.
 */
export function BarList({
  data,
  total,
  showShare = true,
  scaleMax,
}: {
  data: Datum[]
  total: number
  showShare?: boolean
  /** Pass 100 for percentage values, so a near-zero bar reads as near-zero. */
  scaleMax?: number
}) {
  const max = scaleMax ?? Math.max(...data.map((datum) => datum.value), 1)

  return (
    <ul className="space-y-3">
      {data.map((datum) => (
        <li key={datum.label}>
          <div className="flex items-baseline justify-between gap-3 text-xs">
            <span className="min-w-0 truncate text-ink-soft" title={datum.hint ?? datum.label}>
              {datum.label}
            </span>
            <span className="shrink-0 tabular-nums">
              <span className="font-medium text-ink">{formatDatum(datum)}</span>
              {showShare && (
                <span className="ml-1.5 text-ink-muted">{share(datum.value, total)}</span>
              )}
            </span>
          </div>
          {/* 8px track: thin enough to stay recessive against the labels. */}
          <div className="mt-1.5 h-2 w-full rounded-full bg-canvas">
            <div
              className="h-full rounded-full"
              style={{
                width: `${(datum.value / max) * 100}%`,
                background: datum.color,
                // Keep a visible stub for a non-zero value, so "1" never renders as nothing.
                minWidth: datum.value > 0 ? 6 : 0,
              }}
            />
          </div>
        </li>
      ))}
    </ul>
  )
}
