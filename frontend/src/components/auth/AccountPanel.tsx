import { disconnectGitHub, messageOf, signOut } from '../../lib/api'
import { usePending } from '../../lib/hooks'
import type { SessionUser } from '../../types'
import { Button } from '../ui/Button'
import { useToast } from '../ui/Toast'

/**
 * Who you are, what you are, and the way out.
 *
 * Connecting GitHub is what determines which repositories you can see, so when it has not happened
 * the button is the primary action rather than a footnote.
 */
export function AccountPanel({ user, onChange }: { user: SessionUser; onChange: () => void }) {
  const [pending, run] = usePending()
  const toast = useToast()

  const connect = () => {
    // A full navigation, not a fetch: this is a redirect into GitHub's consent screen.
    window.location.href = '/oauth/github/start'
  }

  const disconnect = () =>
    run(async () => {
      try {
        await disconnectGitHub()
        toast.show('GitHub disconnected.', 'success')
        onChange()
      } catch (cause) {
        toast.show(messageOf(cause, 'Could not disconnect GitHub.'), 'error')
      }
    })

  const leave = () =>
    run(async () => {
      await signOut()
      // Reload rather than resetting state, so no cached data survives the sign-out.
      window.location.href = '/'
    })

  return (
    <div className="rounded-xl border border-line bg-surface p-3">
      <p className="truncate text-xs font-semibold text-ink" title={user.username}>
        {user.display_name}
      </p>
      <p className="mt-0.5 truncate text-[11px] text-ink-muted">
        {user.role === 'admin' ? 'Administrator' : 'User'}
        {user.github_connected ? ` · GitHub: ${user.github_login}` : ' · GitHub not connected'}
      </p>

      <div className="mt-2.5 flex flex-col gap-1.5">
        {user.github_connected ? (
          <Button size="sm" onClick={disconnect} busy={pending} className="w-full">
            Disconnect GitHub
          </Button>
        ) : user.oauth_available ? (
          <Button size="sm" variant="primary" onClick={connect} className="w-full">
            Connect GitHub
          </Button>
        ) : (
          <p className="text-[11px] leading-relaxed text-ink-muted">
            GitHub sign-in is not configured on this server, so you will see only repositories you
            onboard yourself.
          </p>
        )}
        <Button size="sm" variant="ghost" onClick={leave} busy={pending} className="w-full">
          Sign out
        </Button>
      </div>
    </div>
  )
}
