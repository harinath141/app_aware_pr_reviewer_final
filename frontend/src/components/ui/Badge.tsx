import type { ReactNode } from 'react'
import { cn } from '../../lib/cn'
import type { Tone } from '../../lib/tones'

const TONE: Record<Tone, string> = {
  neutral: 'bg-slate-100 text-slate-600 ring-slate-200',
  accent: 'bg-accent-soft text-accent-strong ring-accent-line',
  success: 'bg-emerald-50 text-emerald-700 ring-emerald-200',
  warning: 'bg-amber-50 text-amber-700 ring-amber-200',
  danger: 'bg-rose-50 text-rose-700 ring-rose-200',
  info: 'bg-sky-50 text-sky-700 ring-sky-200',
}

interface BadgeProps {
  tone?: Tone
  /** Uppercase micro-label (statuses, severities). Off for prose-length content. */
  caps?: boolean
  className?: string
  children: ReactNode
}

export function Badge({ tone = 'neutral', caps = true, className, children }: BadgeProps) {
  return (
    <span
      className={cn(
        'inline-flex items-center rounded-md px-1.5 py-0.5 text-[11px] font-medium ring-1 ring-inset',
        caps && 'tracking-wide uppercase',
        TONE[tone],
        className,
      )}
    >
      {children}
    </span>
  )
}
