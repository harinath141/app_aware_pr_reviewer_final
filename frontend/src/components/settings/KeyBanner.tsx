import type { CredentialsResponse } from '../../types'
import { AlertIcon } from '../ui/icons'

/**
 * Two different warnings, ported verbatim in meaning from the original dashboard:
 * a healthy key still means the page is unauthenticated, and a missing/invalid key means tokens
 * cannot be stored at all.
 */
export function KeyBanner({ state }: { state: CredentialsResponse }) {
  const keyBroken = state.key_status !== 'ok'

  const frame = keyBroken ? 'border-rose-200 bg-rose-50' : 'border-amber-200 bg-amber-50'
  const icon = keyBroken ? 'text-rose-600' : 'text-amber-600'
  const text = keyBroken ? 'text-rose-800' : 'text-amber-900'

  return (
    <div role="alert" className={`flex items-start gap-2.5 rounded-xl border px-4 py-3 ${frame}`}>
      <AlertIcon className={`mt-0.5 size-4 shrink-0 ${icon}`} />
      <div className={`text-xs leading-relaxed ${text}`}>
        {keyBroken ? (
          <p>
            <strong className="font-semibold">
              GITHUB_CREDENTIAL_KEY is {state.key_status === 'missing' ? 'not set' : 'invalid'}
            </strong>
            , so tokens cannot be stored or read. Generate one and set it in <code>.env</code>.
          </p>
        ) : (
          <p>
            <strong className="font-semibold">This page has no authentication.</strong> Anyone who
            can reach this URL can add, replace or delete credentials.
          </p>
        )}
        <p className="mt-1 opacity-80">
          {state.admin_token_required
            ? 'Writes require the admin token below.'
            : 'GITHUB_SETTINGS_ADMIN_TOKEN is unset, so writes are ungated.'}
        </p>
      </div>
    </div>
  )
}
