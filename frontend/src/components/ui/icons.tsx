import type { ReactNode } from 'react'
import { cn } from '../../lib/cn'

/* Single-stroke icon set on a shared 24px grid, so weight and alignment stay consistent. */
function Glyph({ className, children }: { className?: string; children: ReactNode }) {
  return (
    <svg
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.7"
      strokeLinecap="round"
      strokeLinejoin="round"
      className={cn('size-4 shrink-0', className)}
      aria-hidden="true"
    >
      {children}
    </svg>
  )
}

type IconProps = { className?: string }

export const OverviewIcon = ({ className }: IconProps) => (
  <Glyph className={className}>
    <rect x="3" y="3" width="18" height="18" rx="2.5" />
    <path d="M3 9h18M9 21V9" />
  </Glyph>
)

export const PlusIcon = ({ className }: IconProps) => (
  <Glyph className={className}>
    <path d="M12 5v14M5 12h14" />
  </Glyph>
)

export const AppsIcon = ({ className }: IconProps) => (
  <Glyph className={className}>
    <path d="M12 3 20 7.5v9L12 21 4 16.5v-9z" />
    <path d="M4 7.5 12 12l8-4.5M12 12v9" />
  </Glyph>
)

export const PullRequestIcon = ({ className }: IconProps) => (
  <Glyph className={className}>
    <circle cx="6" cy="6" r="2.6" />
    <circle cx="6" cy="18" r="2.6" />
    <path d="M6 8.6v6.8" />
    <circle cx="18" cy="18" r="2.6" />
    <path d="M18 15.4V9a3 3 0 0 0-3-3h-2.6" />
    <path d="M14.4 3.6 12 6l2.4 2.4" />
  </Glyph>
)

export const ShieldIcon = ({ className }: IconProps) => (
  <Glyph className={className}>
    <path d="M12 3 5 6v6c0 4.2 2.9 7.7 7 9 4.1-1.3 7-4.8 7-9V6z" />
    <path d="M12 9v3.5M12 16h.01" />
  </Glyph>
)

export const SettingsIcon = ({ className }: IconProps) => (
  <Glyph className={className}>
    <circle cx="12" cy="12" r="3" />
    <path d="M19.4 15a1.7 1.7 0 0 0 .3 1.9l.1.1a2 2 0 1 1-2.8 2.8l-.1-.1a1.7 1.7 0 0 0-2.9 1.2v.2a2 2 0 1 1-4 0v-.1a1.7 1.7 0 0 0-1.1-1.6 1.7 1.7 0 0 0-1.9.4l-.1.1a2 2 0 1 1-2.8-2.8l.1-.1a1.7 1.7 0 0 0-1.2-2.9H3a2 2 0 1 1 0-4h.2A1.7 1.7 0 0 0 4.7 7a1.7 1.7 0 0 0-.4-1.9l-.1-.1a2 2 0 1 1 2.8-2.8l.1.1a1.7 1.7 0 0 0 1.9.3H9a1.7 1.7 0 0 0 1-1.5V1a2 2 0 1 1 4 0v.2a1.7 1.7 0 0 0 2.9 1.2l.1-.1a2 2 0 1 1 2.8 2.8l-.1.1a1.7 1.7 0 0 0-.3 1.9V9a1.7 1.7 0 0 0 1.5 1H23a2 2 0 1 1 0 4h-.2a1.7 1.7 0 0 0-1.4 1z" />
  </Glyph>
)

export const PipelineIcon = ({ className }: IconProps) => (
  <Glyph className={className}>
    <circle cx="6" cy="6" r="2.6" />
    <circle cx="6" cy="18" r="2.6" />
    <circle cx="18" cy="12" r="2.6" />
    <path d="M8.6 6h3.4a3 3 0 0 1 3 3v.4M8.6 18h3.4a3 3 0 0 0 3-3v-.4" />
  </Glyph>
)

export const RefreshIcon = ({ className }: IconProps) => (
  <Glyph className={className}>
    <path d="M20.5 12a8.5 8.5 0 1 1-2.5-6" />
    <path d="M20.5 4.5V10h-5.5" />
  </Glyph>
)

export const MenuIcon = ({ className }: IconProps) => (
  <Glyph className={className}>
    <path d="M4 7h16M4 12h16M4 17h16" />
  </Glyph>
)

export const CloseIcon = ({ className }: IconProps) => (
  <Glyph className={className}>
    <path d="m6 6 12 12M18 6 6 18" />
  </Glyph>
)

export const ExternalIcon = ({ className }: IconProps) => (
  <Glyph className={cn('size-3', className)}>
    <path d="M14 4h6v6M20 4l-8.5 8.5" />
    <path d="M18 14.5V19a1.5 1.5 0 0 1-1.5 1.5h-11A1.5 1.5 0 0 1 4 19V8a1.5 1.5 0 0 1 1.5-1.5H10" />
  </Glyph>
)

export const ChevronDownIcon = ({ className }: IconProps) => (
  <Glyph className={cn('size-3.5', className)}>
    <path d="m6 9.5 6 6 6-6" />
  </Glyph>
)

export const CheckIcon = ({ className }: IconProps) => (
  <Glyph className={className}>
    <path d="M20 6.5 9.5 17 4 11.5" />
  </Glyph>
)

export const AlertIcon = ({ className }: IconProps) => (
  <Glyph className={className}>
    <circle cx="12" cy="12" r="9" />
    <path d="M12 7.5V13M12 16.5h.01" />
  </Glyph>
)

export const InfoIcon = ({ className }: IconProps) => (
  <Glyph className={className}>
    <circle cx="12" cy="12" r="9" />
    <path d="M12 16.5V11M12 7.5h.01" />
  </Glyph>
)

export const BugIcon = ({ className }: IconProps) => (
  <Glyph className={className}>
    <path d="m8 2.5 1.9 1.9M14.1 4.4 16 2.5" />
    <path d="M9 7.1v-1a3 3 0 1 1 6 0v1" />
    <path d="M12 20.5c-3.3 0-6-2.7-6-6v-3a4 4 0 0 1 4-4h4a4 4 0 0 1 4 4v3c0 3.3-2.7 6-6 6" />
    <path d="M12 20.5v-9M6.5 9.2C4.6 9 3 7.3 3 5.2M6 13H2M3.2 20.8c0-2.1 1.7-3.9 3.8-4M17.5 9.2c1.9-.2 3.5-1.9 3.5-4M18 13h4M20.8 20.8c0-2.1-1.7-3.9-3.8-4" />
  </Glyph>
)

export const FlameIcon = ({ className }: IconProps) => (
  <Glyph className={className}>
    <path d="M12 2.5c.6 2.5 2.4 3.6 3.8 5.2A6.6 6.6 0 0 1 17.5 12a5.5 5.5 0 1 1-11 0c0-1.1.3-2 1-2.9.3 1 1 1.7 2 1.9-.6-2.6.3-5.3 2.5-8.5z" />
  </Glyph>
)
