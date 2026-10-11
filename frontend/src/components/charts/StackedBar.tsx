import { count, share } from '../../lib/format'
import type { Datum } from './ChartCard'

/**
 * Part-to-whole in one row. Segments are laid out with `flex-grow` rather than percentage widths
 * so the 2px separators do not push the row past 100%; the outer ends take the container radius.
 *
 * Segments are separated by surface gaps, never by borders drawn around the marks.
 */
export function StackedBar({ data, total }: { data: Datum[]; total: number }) {
  const segments = data.filter((datum) => datum.value > 0)

  return (
    <div>
      <div className="flex h-3.5 w-full gap-0.5 overflow-hidden rounded-full">
        {segments.map((datum) => (
          <div
            key={datum.label}
            className="h-full basis-0"
            style={{ flexGrow: datum.value, background: datum.color }}
            title={`${datum.label}: ${count(datum.value)} (${share(datum.value, total)})`}
          />
        ))}
      </div>

      {/* Legend is always present for 2+ series, so identity is never carried by colour alone. */}
      <ul className="mt-3.5 flex flex-wrap gap-x-5 gap-y-2">
        {data.map((datum) => (
          <li key={datum.label} className="flex items-center gap-2 text-xs">
            <span
              aria-hidden="true"
              className="size-2.5 shrink-0 rounded-sm"
              style={{ background: datum.color }}
            />
            <span className="text-ink-soft">{datum.label}</span>
            <span className="font-medium tabular-nums text-ink">{count(datum.value)}</span>
            <span className="tabular-nums text-ink-muted">{share(datum.value, total)}</span>
          </li>
        ))}
      </ul>
    </div>
  )
}
