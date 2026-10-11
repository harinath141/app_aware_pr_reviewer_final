import type { ReactNode } from 'react'

interface SectionProps {
  id: string
  title: string
  description?: ReactNode
  /** Filter controls or buttons, right-aligned against the heading on wide screens. */
  actions?: ReactNode
  children: ReactNode
}

export function Section({ id, title, description, actions, children }: SectionProps) {
  return (
    <section id={id} className="pt-9 first:pt-0">
      <div className="mb-3 flex flex-wrap items-end justify-between gap-x-4 gap-y-3">
        <div>
          <h2 className="text-base font-semibold tracking-tight text-ink">{title}</h2>
          {description && (
            <p className="mt-0.5 max-w-2xl text-xs leading-relaxed text-ink-muted">{description}</p>
          )}
        </div>
        {actions && <div className="flex flex-wrap items-center gap-2">{actions}</div>}
      </div>
      {children}
    </section>
  )
}
