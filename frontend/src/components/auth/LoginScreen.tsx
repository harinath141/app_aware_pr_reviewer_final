import { useState } from 'react'
import type { FormEvent } from 'react'
import { messageOf, signIn } from '../../lib/api'
import { usePending } from '../../lib/hooks'
import type { SessionUser } from '../../types'
import { Button } from '../ui/Button'
import { Card } from '../ui/Card'
import { TextInput } from '../ui/Field'
import { AlertIcon } from '../ui/icons'

/**
 * The only thing reachable before signing in.
 *
 * There is no router in this app, so this is rendered in place of the whole shell rather than at a
 * route - which also means no dashboard component is ever mounted for a signed-out browser, so
 * nothing can fetch data it has no right to.
 */
export function LoginScreen({ onSignedIn }: { onSignedIn: (user: SessionUser) => void }) {
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [pending, run] = usePending()

  const submit = async (event: FormEvent) => {
    event.preventDefault()
    setError(null)
    if (!username.trim() || !password) {
      setError('Enter your username and password.')
      return
    }
    await run(async () => {
      try {
        onSignedIn(await signIn(username.trim(), password))
      } catch (cause) {
        // The server deliberately does not distinguish "no such user" from "wrong password", so
        // this message is whatever it said - shown as-is rather than reinterpreted here.
        setError(messageOf(cause, 'Sign-in failed.'))
        setPassword('')
      }
    })
  }

  return (
    <div className="flex min-h-screen items-center justify-center bg-canvas px-4 py-10">
      <div className="w-full max-w-sm">
        <div className="mb-6 flex items-center justify-center gap-2.5">
          <span className="grid size-9 shrink-0 place-items-center rounded-xl bg-accent text-sm font-bold text-white">
            C
          </span>
          <span className="min-w-0">
            <span className="block text-sm font-semibold text-ink">ContextGuard</span>
            <span className="block text-[11px] text-ink-muted">Application-aware review</span>
          </span>
        </div>

        <Card className="p-5">
          <h1 className="text-base font-semibold text-ink">Sign in</h1>
          <p className="mt-1 text-xs leading-relaxed text-ink-muted">
            Use your directory account. Access to individual repositories is then decided by your
            GitHub permissions.
          </p>

          <form onSubmit={submit} className="mt-4 space-y-3">
            <TextInput
              label="Username"
              value={username}
              onChange={(event) => setUsername(event.target.value)}
              autoComplete="username"
              autoFocus
              spellCheck={false}
            />
            <TextInput
              label="Password"
              type="password"
              value={password}
              onChange={(event) => setPassword(event.target.value)}
              autoComplete="current-password"
            />

            {error && (
              <p role="alert" className="flex items-start gap-1.5 text-xs text-rose-700">
                <AlertIcon className="mt-px size-3.5 shrink-0" />
                {error}
              </p>
            )}

            <Button type="submit" variant="primary" busy={pending} className="w-full">
              Sign in
            </Button>
          </form>
        </Card>

        <p className="mt-4 text-center text-[11px] leading-relaxed text-ink-muted">
          Sign-in is handled by your directory. Your password is never stored by this application.
        </p>
      </div>
    </div>
  )
}
