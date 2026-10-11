import { useState } from 'react'
import { deleteCredential, messageOf, verifyCredential } from '../../lib/api'
import { count, humanize, when } from '../../lib/format'
import { credentialTone } from '../../lib/tones'
import type { Credential } from '../../types'
import { Badge } from '../ui/Badge'
import { Button } from '../ui/Button'
import { Card } from '../ui/Card'
import { useToast } from '../ui/Toast'

const HEAD = 'px-4 py-2.5 text-[10px] font-semibold tracking-[0.08em] text-ink-muted uppercase'
const CELL = 'px-4 py-3 align-middle text-xs text-ink-soft'

interface CredentialTableProps {
  credentials: Credential[]
  adminToken: string
  onChanged: () => void
}

export function CredentialTable({ credentials, adminToken, onChanged }: CredentialTableProps) {
  const [busyOwner, setBusyOwner] = useState<string | null>(null)
  const toast = useToast()

  const reverify = async (owner: string) => {
    setBusyOwner(owner)
    try {
      const { verification } = await verifyCredential(owner, adminToken)
      toast.show(
        verification.detail || `Re-verified: ${humanize(verification.status, 'unknown')}`,
        verification.status === 'ok' ? 'success' : 'info',
      )
      onChanged()
    } catch (cause) {
      toast.show(messageOf(cause, 'Could not verify the credential.'), 'error')
    } finally {
      setBusyOwner(null)
    }
  }

  const remove = async (owner: string) => {
    // Destructive and not undoable from here; the token would have to be re-entered.
    if (!window.confirm(`Delete the credential for ${owner}?\n\nThat owner will fall back to the default token.`)) {
      return
    }
    setBusyOwner(owner)
    try {
      await deleteCredential(owner, adminToken)
      toast.show('Credential deleted.', 'success')
      onChanged()
    } catch (cause) {
      toast.show(messageOf(cause, 'Could not delete that credential.'), 'error')
    } finally {
      setBusyOwner(null)
    }
  }

  return (
    <Card>
      <div className="overflow-x-auto">
        <table className="w-full min-w-[860px] border-collapse text-left">
          <caption className="sr-only">Per-owner GitHub credentials</caption>
          <thead>
            <tr className="border-b border-line bg-canvas/60">
              <th scope="col" className={HEAD}>
                Owner
              </th>
              <th scope="col" className={HEAD}>
                Token
              </th>
              <th scope="col" className={HEAD}>
                Verified as
              </th>
              <th scope="col" className={HEAD}>
                Repos
              </th>
              <th scope="col" className={HEAD}>
                Last check
              </th>
              <th scope="col" className={HEAD}>
                Checked
              </th>
              <th scope="col" className={HEAD}>
                <span className="sr-only">Actions</span>
              </th>
            </tr>
          </thead>
          <tbody>
            {credentials.length === 0 ? (
              <tr>
                <td colSpan={7} className="px-4 py-10 text-center text-xs text-ink-muted">
                  No per-owner credentials yet — every owner uses the default token.
                </td>
              </tr>
            ) : (
              credentials.map((credential) => (
                <tr
                  key={credential.owner}
                  className="border-b border-line last:border-b-0 hover:bg-canvas/50"
                >
                  <td className={`${CELL} font-medium text-ink`}>
                    {credential.owner_login || credential.owner}
                  </td>
                  <td className={`${CELL} font-mono`}>{credential.token_hint}</td>
                  <td className={CELL}>{credential.verified_login || '—'}</td>
                  <td className={`${CELL} tabular-nums`}>
                    {credential.repo_access_count == null ? '—' : count(credential.repo_access_count)}
                  </td>
                  <td className={CELL}>
                    <Badge tone={credentialTone(credential.last_verification_status)}>
                      {humanize(credential.last_verification_status, 'unknown')}
                    </Badge>
                  </td>
                  <td className={`${CELL} whitespace-nowrap`}>{when(credential.last_verified_at)}</td>
                  <td className={CELL}>
                    <div className="flex items-center gap-2">
                      <Button
                        size="sm"
                        busy={busyOwner === credential.owner}
                        onClick={() => reverify(credential.owner)}
                      >
                        Re-verify
                      </Button>
                      <Button
                        size="sm"
                        variant="danger"
                        disabled={busyOwner !== null}
                        onClick={() => remove(credential.owner)}
                      >
                        Delete
                      </Button>
                    </div>
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>
    </Card>
  )
}
