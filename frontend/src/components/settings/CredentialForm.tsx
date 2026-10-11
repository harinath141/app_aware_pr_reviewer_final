import { useState } from 'react'
import type { FormEvent } from 'react'
import { messageOf, saveCredential } from '../../lib/api'
import { usePending } from '../../lib/hooks'
import { Button } from '../ui/Button'
import { Card, CardHeader } from '../ui/Card'
import { TextInput } from '../ui/Field'
import { useToast } from '../ui/Toast'
import { AlertIcon } from '../ui/icons'

interface CredentialFormProps {
  adminToken: string
  adminTokenRequired: boolean
  keyUsable: boolean
  onSaved: () => void
  onAdminTokenChange: (value: string) => void
}

export function CredentialForm({
  adminToken,
  adminTokenRequired,
  keyUsable,
  onSaved,
  onAdminTokenChange,
}: CredentialFormProps) {
  const [owner, setOwner] = useState('')
  const [token, setToken] = useState('')
  const [localError, setLocalError] = useState<string | null>(null)
  const [pending, run] = usePending()
  const toast = useToast()

  const submit = async (event: FormEvent) => {
    event.preventDefault()
    const cleanOwner = owner.trim()
    const cleanToken = token.trim()
    setLocalError(null)

    if (!cleanOwner || !cleanToken) {
      setLocalError('Enter both an owner and a token.')
      return
    }

    await run(async () => {
      try {
        const saved = await saveCredential(cleanOwner, cleanToken, adminToken)
        setToken('')
        // The backend explains partial success here ("Saved, but this token can see 0
        // repositories…"), so surface it as-is rather than a bare confirmation.
        const caveat = saved.last_verification_detail
        toast.show(caveat || `Credential saved for ${saved.owner_login || cleanOwner}.`, caveat ? 'info' : 'success')
        onSaved()
      } catch (cause) {
        const message = messageOf(cause, 'Could not save the credential.')
        setLocalError(message)
        toast.show(message, 'error')
      }
    })
  }

  return (
    <Card>
      <CardHeader
        title="Add or replace a credential"
        meta="Encrypted at rest — never displayed again after saving"
      />
      <form onSubmit={submit} className="space-y-3 p-4">
        <div className="grid gap-3 sm:grid-cols-2">
          <TextInput
            label="Owner or organisation"
            placeholder="owner or organisation, e.g. acme"
            autoComplete="off"
            spellCheck={false}
            value={owner}
            onChange={(event) => setOwner(event.target.value)}
            disabled={!keyUsable}
          />
          <TextInput
            label="GitHub personal access token"
            type="password"
            placeholder="GitHub personal access token"
            autoComplete="off"
            spellCheck={false}
            value={token}
            onChange={(event) => setToken(event.target.value)}
            disabled={!keyUsable}
          />
        </div>

        {adminTokenRequired && (
          <div className="rounded-lg border border-line bg-canvas p-3">
            <TextInput
              label="Admin token"
              type="password"
              placeholder="X-Admin-Token"
              autoComplete="off"
              spellCheck={false}
              value={adminToken}
              onChange={(event) => onAdminTokenChange(event.target.value)}
            />
            <p className="mt-2 text-[11px] leading-relaxed text-ink-muted">
              Required by this server. Held in memory for this tab only — never stored and never
              sent anywhere except this API.
            </p>
          </div>
        )}

        {localError && (
          <p role="alert" className="flex items-start gap-1.5 text-xs text-rose-700">
            <AlertIcon className="mt-px size-3.5 shrink-0" />
            {localError}
          </p>
        )}

        <div className="flex flex-wrap items-center gap-3">
          <Button type="submit" variant="primary" busy={pending} disabled={!keyUsable}>
            Save credential
          </Button>
          {!keyUsable && (
            <span className="text-[11px] text-ink-muted">
              Unavailable until GITHUB_CREDENTIAL_KEY is set.
            </span>
          )}
        </div>
      </form>
    </Card>
  )
}
