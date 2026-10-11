import type { ReactNode } from 'react'
import { cn } from '../../lib/cn'

export function Card({ className, children }: { className?: string; children: ReactNode }) {
  return (
    <div className={cn('overflow-hidden rounded-xl border border-line bg-surface', className)}>
      {children}
    </div>
  )
}

export function CardHeader({
  title,
  meta,
  className,
}: {
  title: ReactNode
  meta?: ReactNode
  className?: string
}) {
  return (
    <div
      className={cn(
        'flex flex-wrap items-center justify-between gap-x-3 gap-y-1 border-b border-line px-4 py-3',
        className,
      )}
    >
      <h3 className="text-sm font-semibold text-ink">{title}</h3>
      {meta && <span className="text-xs text-ink-muted">{meta}</span>}
    </div>
  )
}
