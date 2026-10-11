import type { ReactNode } from 'react'
import { cn } from '../../lib/cn'
import { Button } from './Button'

export function Skeleton({ className }: { className?: string }) {
  return <div className={cn('animate-pulse rounded-md bg-slate-200/70', className)} aria-hidden="true" />
}

/** Placeholder rows sized like the real content, so the layout does not jump when data lands. */
export function SkeletonRows({ rows = 3, className }: { rows?: number; className?: string }) {
  return (
    <div className={cn('space-y-2', className)}>
      {Array.from({ length: rows }, (_, index) => (
        <Skeleton key={index} className="h-16 w-full" />
      ))}
    </div>
  )
}

export function EmptyState({
  title,
  hint,
  action,
  className,
}: {
  title: string
  hint?: string
  action?: ReactNode
  className?: string
}) {
  return (
    <div
      className={cn(
        'rounded-xl border border-dashed border-line-strong bg-surface px-6 py-10 text-center',
        className,
      )}
    >
      <p className="text-sm font-medium text-ink-soft">{title}</p>
      {hint && <p className="mx-auto mt-1.5 max-w-md text-xs leading-relaxed text-ink-muted">{hint}</p>}
      {action && <div className="mt-4 flex justify-center">{action}</div>}
    </div>
  )
}

export function ErrorState({ message, onRetry }: { message: string; onRetry?: () => void }) {
  return (
    <div
      role="alert"
      className="rounded-xl border border-rose-200 bg-rose-50/60 px-6 py-8 text-center"
    >
      <p className="text-sm font-medium text-rose-800">{message}</p>
      <p className="mx-auto mt-1.5 max-w-md text-xs leading-relaxed text-rose-700/80">
        Check that the API and database are running, then try again.
      </p>
      {onRetry && (
        <div className="mt-4 flex justify-center">
          <Button onClick={onRetry}>Try again</Button>
        </div>
      )}
    </div>
  )
}
