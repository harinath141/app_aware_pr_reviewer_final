import { formatDatum } from './ChartCard'
import type { Datum } from './ChartCard'

const PLOT_HEIGHT = 132
const LABEL_BAND = 20
/** Past this many columns, label every nth column - overlapping axis text is worse than omission. */
const MAX_X_LABELS = 7
/** Past this many columns, labelling every bar becomes noise; only the extreme is called out. */
const MAX_VALUE_LABELS = 8

/**
 * Vertical columns, used where the categories have a left-to-right order (severity levels) or run
 * along time. Bars sit on a hairline baseline and are direct-labelled, so the axis carries only the
 * category names.
 */
export function ColumnChart({ data, scaleMax }: { data: Datum[]; scaleMax?: number }) {
  const dataMax = Math.max(...data.map((datum) => datum.value), 1)
  const max = scaleMax ?? dataMax
  const labelStep = Math.ceil(data.length / MAX_X_LABELS)
  const labelEveryValue = data.length <= MAX_VALUE_LABELS

  return (
    <div>
      <div className="flex items-end gap-2" style={{ height: PLOT_HEIGHT }}>
        {data.map((datum) => {
          const barHeight = Math.max(2, Math.round((datum.value / max) * (PLOT_HEIGHT - LABEL_BAND)))
          return (
            <div
              key={datum.label}
              className="group flex h-full min-w-0 flex-1 flex-col items-center justify-end gap-1.5"
              title={`${datum.label}: ${formatDatum(datum)}${datum.hint ? ` — ${datum.hint}` : ''}`}
            >
              <span className="text-[11px] font-medium tabular-nums text-ink">
                {labelEveryValue || datum.value === dataMax ? formatDatum(datum) : ''}
              </span>
              <div
                className="w-full max-w-[44px] rounded-t-[4px] transition-opacity group-hover:opacity-80"
                style={{
                  height: barHeight,
                  background: datum.value > 0 ? datum.color : 'var(--color-line)',
                }}
              />
            </div>
          )
        })}
      </div>

      {/* Hairline baseline: one shade off the surface, solid, never dashed. */}
      <div className="flex gap-2 border-t border-line pt-2">
        {data.map((datum, index) => (
          <span
            key={datum.label}
            className="min-w-0 flex-1 truncate text-center text-[10px] text-ink-muted"
            title={datum.hint ?? datum.label}
          >
            {index % labelStep === 0 ? datum.label : ''}
          </span>
        ))}
      </div>
    </div>
  )
}
