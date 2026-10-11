import type { ReactNode } from 'react'
import { cn } from '../../lib/cn'
import { visibleNavItems } from '../../lib/nav'
import type { TabId } from '../../lib/nav'

export function Brand() {
  return (
    <div className="flex items-center gap-2.5 px-2">
      <span className="grid size-9 shrink-0 place-items-center rounded-xl bg-accent text-sm font-bold text-white">
        C
      </span>
      <span className="min-w-0">
        <span className="block truncate text-sm font-semibold text-ink">ContextGuard</span>
        <span className="block truncate text-[11px] text-ink-muted">Application-aware review</span>
      </span>
    </div>
  )
}

interface SidebarProps {
  active: TabId
  onSelect: (id: TabId) => void
  isAdmin: boolean
  footer?: ReactNode
}

export function Sidebar({ active, onSelect, isAdmin, footer }: SidebarProps) {
  return (
    <>
      <Brand />

      {/* Buttons, not anchors: these switch a tab rather than scroll to a section. */}
      <nav aria-label="Sections">
        <p className="px-2.5 pb-1.5 text-[10px] font-semibold tracking-[0.14em] text-ink-muted uppercase">
          Workspace
        </p>
        <ul className="space-y-0.5">
          {visibleNavItems(isAdmin).map(({ id, label, Icon }) => {
            const isActive = active === id
            return (
              <li key={id}>
                <button
                  type="button"
                  onClick={() => onSelect(id)}
                  aria-current={isActive ? 'page' : undefined}
                  className={cn(
                    'flex w-full items-center gap-2.5 rounded-lg px-2.5 py-2 text-left text-sm transition-colors',
                    'focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent',
                    isActive
                      ? 'bg-accent-soft font-medium text-accent-strong'
                      : 'text-ink-soft hover:bg-canvas hover:text-ink',
                  )}
                >
                  <Icon className={cn('size-4', isActive ? 'text-accent' : 'text-ink-muted')} />
                  {label}
                </button>
              </li>
            )
          })}
        </ul>
      </nav>

      <div className="mt-auto space-y-3">
        {footer}
        <div className="rounded-xl border border-line bg-canvas p-3">
          <p className="text-xs font-semibold text-ink">Context-first review</p>
          <p className="mt-1 text-[11px] leading-relaxed text-ink-muted">
            Reviews are grounded in versioned repository knowledge, code symbols and dependency
            candidates — not just the changed diff.
          </p>
        </div>
      </div>
    </>
  )
}
