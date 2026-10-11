import { useEffect, useState } from 'react'
import type { ReactNode } from 'react'
import type { TabId } from '../../lib/nav'
import { CloseIcon, MenuIcon } from '../ui/icons'
import { Brand, Sidebar } from './Sidebar'

interface AppShellProps {
  active: TabId
  onSelect: (id: TabId) => void
  isAdmin: boolean
  /** Rendered above the standing note - the signed-in account and sign-out live here. */
  footer?: ReactNode
  children: ReactNode
}

export function AppShell({ active, onSelect, isAdmin, footer, children }: AppShellProps) {
  const [drawerOpen, setDrawerOpen] = useState(false)

  const select = (id: TabId) => {
    onSelect(id)
    setDrawerOpen(false)
  }

  useEffect(() => {
    if (!drawerOpen) return
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') setDrawerOpen(false)
    }
    const previousOverflow = document.body.style.overflow
    document.addEventListener('keydown', onKeyDown)
    document.body.style.overflow = 'hidden'
    return () => {
      document.removeEventListener('keydown', onKeyDown)
      document.body.style.overflow = previousOverflow
    }
  }, [drawerOpen])

  return (
    <div className="min-h-screen">
      <aside className="fixed inset-y-0 left-0 hidden w-[248px] flex-col gap-7 overflow-y-auto border-r border-line bg-surface px-4 py-6 lg:flex">
        <Sidebar active={active} onSelect={select} isAdmin={isAdmin} footer={footer} />
      </aside>

      <header className="sticky top-0 z-30 flex items-center gap-3 border-b border-line bg-surface/85 px-4 py-2.5 backdrop-blur lg:hidden">
        <button
          type="button"
          onClick={() => setDrawerOpen(true)}
          aria-label="Open navigation"
          aria-expanded={drawerOpen}
          className="rounded-lg p-2 text-ink-soft transition-colors hover:bg-canvas hover:text-ink focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent"
        >
          <MenuIcon className="size-5" />
        </button>
        <Brand />
      </header>

      {drawerOpen && (
        <div className="fixed inset-0 z-50 lg:hidden">
          <div
            className="absolute inset-0 bg-slate-900/30"
            onClick={() => setDrawerOpen(false)}
            aria-hidden="true"
          />
          <div
            role="dialog"
            aria-modal="true"
            aria-label="Navigation"
            className="absolute inset-y-0 left-0 flex w-72 max-w-[85vw] flex-col gap-7 overflow-y-auto border-r border-line bg-surface px-4 py-6 shadow-xl"
          >
            <div className="flex items-start justify-between gap-2">
              <Brand />
              <button
                type="button"
                onClick={() => setDrawerOpen(false)}
                aria-label="Close navigation"
                className="-mr-1 rounded-lg p-1.5 text-ink-muted transition-colors hover:bg-canvas hover:text-ink focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent"
              >
                <CloseIcon className="size-4" />
              </button>
            </div>
            <Sidebar active={active} onSelect={select} isAdmin={isAdmin} footer={footer} />
          </div>
        </div>
      )}

      <main className="lg:pl-[248px]">
        <div className="mx-auto w-full max-w-[1400px] px-4 py-6 sm:px-6 lg:px-10 lg:py-9">
          {children}
        </div>
      </main>
    </div>
  )
}
