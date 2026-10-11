import type { ComponentType } from 'react'
import { AppsIcon, OverviewIcon, PlusIcon, SettingsIcon, ShieldIcon } from '../components/ui/icons'

export type TabId = 'overview' | 'projects' | 'onboard' | 'findings' | 'settings'

export interface NavItem {
  id: TabId
  label: string
  Icon: ComponentType<{ className?: string }>
  /** Not rendered for a non-admin; the server refuses the underlying routes regardless. */
  adminOnly?: boolean
}

/**
 * The dashboard is tabbed rather than one long scroll: only the selected tab is mounted, so the
 * findings table, the application detail and the credentials form are never all in the DOM at once.
 *
 * The ids double as URL hashes, so /#projects is deep-linkable and matches the anchors this
 * dashboard used before it was tabbed.
 *
 * There is no separate reviews tab: a review run belongs to a commit, so reviews are shown inside
 * the application detail against the commit they ran on, next to that commit's findings.
 */
export const NAV_ITEMS: NavItem[] = [
  { id: 'overview', label: 'Overview', Icon: OverviewIcon },
  { id: 'projects', label: 'Applications', Icon: AppsIcon },
  { id: 'onboard', label: 'Onboard', Icon: PlusIcon },
  { id: 'findings', label: 'Security & issues', Icon: ShieldIcon },
  { id: 'settings', label: 'Settings', Icon: SettingsIcon, adminOnly: true },
]

export function visibleNavItems(isAdmin: boolean): NavItem[] {
  return NAV_ITEMS.filter((item) => !item.adminOnly || isAdmin)
}

export function isTabId(value: string): value is TabId {
  return NAV_ITEMS.some((item) => item.id === value)
}
