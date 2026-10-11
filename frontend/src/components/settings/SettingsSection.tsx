import { useCallback, useEffect, useState } from 'react'
import { fetchCredentials, isAbort, messageOf } from '../../lib/api'
import type { CredentialsResponse } from '../../types'
import { ErrorState, Skeleton } from '../ui/States'
import { CredentialForm } from './CredentialForm'
import { CredentialTable } from './CredentialTable'
import { KeyBanner } from './KeyBanner'

function useCredentials() {
  const [data, setData] = useState<CredentialsResponse | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [attempt, setAttempt] = useState(0)

  useEffect(() => {
    const controller = new AbortController()
    let cancelled = false

    fetchCredentials(controller.signal)
      .then((next) => {
        if (cancelled) return
        setData(next)
        setError(null)
      })
      .catch((cause: unknown) => {
        if (cancelled || isAbort(cause)) return
        setError(messageOf(cause, 'Could not load credentials.'))
      })

    return () => {
      cancelled = true
      controller.abort()
    }
  }, [attempt])

  const reload = useCallback(() => setAttempt((value) => value + 1), [])

  return { data, error, reload }
}

export function SettingsSection() {
  // Held in memory only: it is a shared secret for this server, not a value worth persisting.
  const [adminToken, setAdminToken] = useState('')
  const { data, error, reload } = useCredentials()

  if (error && !data) return <ErrorState message={error} onRetry={reload} />
  if (!data) return <Skeleton className="h-72 w-full" />

  const keyUsable = data.key_status === 'ok'
  const fallback = data.global_fallback

  return (
    <div className="space-y-5">
      <KeyBanner state={data} />

      {error && (
        <p role="alert" className="text-xs text-rose-700">
          {error}
        </p>
      )}

      <CredentialForm
        adminToken={adminToken}
        adminTokenRequired={data.admin_token_required}
        keyUsable={keyUsable}
        onAdminTokenChange={setAdminToken}
        onSaved={reload}
      />

      <div>
        <div className="mb-3">
          <h3 className="text-sm font-semibold text-ink">Configured owners</h3>
          <p className="mt-0.5 text-xs text-ink-muted">
            Tokens are write-only: only a masked hint is ever shown.
          </p>
        </div>
        <CredentialTable credentials={data.credentials} adminToken={adminToken} onChanged={reload} />
      </div>

      <p className="text-[11px] leading-relaxed text-ink-muted">
        Owners without a stored credential fall back to the server default (GITHUB_TOKEN):{' '}
        {fallback.configured ? (
          <>
            configured · <span className="font-mono">{fallback.token_hint}</span>
          </>
        ) : (
          'not configured'
        )}
      </p>
    </div>
  )
}
