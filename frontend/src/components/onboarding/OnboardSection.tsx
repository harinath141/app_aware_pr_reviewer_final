import { useEffect, useState } from 'react'
import { cn } from '../../lib/cn'
import {
  checkRepo,
  checkServiceAccount,
  completeOnboarding,
  fetchWebhookInstructions,
  messageOf,
  previewOnboarding,
} from '../../lib/api'
import { usePending } from '../../lib/hooks'
import type {
  OnboardingPreview,
  OnboardingResult,
  RepoCheck,
  ServiceAccountCheck,
  WebhookInstructions,
} from '../../types'
import { Badge } from '../ui/Badge'
import { Button } from '../ui/Button'
import { Card, CardHeader } from '../ui/Card'
import { TextInput, Textarea } from '../ui/Field'
import { useToast } from '../ui/Toast'
import { AlertIcon, CheckIcon } from '../ui/icons'

const STEPS = ['Repository', 'Profile', 'Access', 'Webhooks', 'Confirm'] as const

/** One pattern per line, or comma-separated - whichever the user reaches for. */
export function toPatterns(text: string): string[] {
  return text
    .split(/[\n,]/)
    .map((value) => value.trim())
    .filter(Boolean)
}

function StepChip({ index, label, done, active }: {
  index: number
  label: string
  done: boolean
  active: boolean
}) {
  return (
    <li className="flex items-center gap-2">
      <span
        className={cn(
          'grid size-6 shrink-0 place-items-center rounded-full text-[11px] font-semibold',
          done ? 'bg-emerald-100 text-emerald-700'
            : active ? 'bg-accent text-white'
              : 'bg-canvas text-ink-muted ring-1 ring-inset ring-line',
        )}
      >
        {done ? <CheckIcon className="size-3" /> : index + 1}
      </span>
      <span
        className={cn(
          'text-xs',
          active ? 'font-medium text-ink' : done ? 'text-ink-soft' : 'text-ink-muted',
        )}
      >
        {label}
      </span>
    </li>
  )
}

function Verdict({ ok, children }: { ok: boolean; children: React.ReactNode }) {
  return (
    <p
      role="status"
      className={cn(
        'mt-3 flex items-start gap-1.5 rounded-lg px-3 py-2 text-xs leading-relaxed',
        ok ? 'bg-emerald-50 text-emerald-800' : 'bg-amber-50 text-amber-900',
      )}
    >
      {ok ? (
        <CheckIcon className="mt-px size-3.5 shrink-0" />
      ) : (
        <AlertIcon className="mt-px size-3.5 shrink-0" />
      )}
      <span>{children}</span>
    </p>
  )
}

/**
 * The onboarding wizard.
 *
 * Every step is gated on a real call to GitHub, so a step cannot be completed by looking plausible:
 * the repository check asks whether our service account can actually see it, the preview downloads
 * the archive and counts what would be indexed, and the access check re-reads the permissions
 * GitHub reports *after* the user has granted them.
 */
export function OnboardSection() {
  const [step, setStep] = useState(0)
  const [repo, setRepo] = useState('')
  const [check, setCheck] = useState<RepoCheck | null>(null)
  const [description, setDescription] = useState('')
  const [includeText, setIncludeText] = useState('')
  const [excludeText, setExcludeText] = useState('')
  const [preview, setPreview] = useState<OnboardingPreview | null>(null)
  const [access, setAccess] = useState<ServiceAccountCheck | null>(null)
  const [webhook, setWebhook] = useState<WebhookInstructions | null>(null)
  const [result, setResult] = useState<OnboardingResult | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [pending, run] = usePending()
  const toast = useToast()

  useEffect(() => {
    if (step !== 3 || webhook) return
    fetchWebhookInstructions()
      .then(setWebhook)
      .catch((cause) => setError(messageOf(cause, 'Could not read the webhook setup.')))
  }, [step, webhook])

  const guard = (action: () => Promise<void>) =>
    run(async () => {
      setError(null)
      try {
        await action()
      } catch (cause) {
        setError(messageOf(cause, 'Something went wrong.'))
      }
    })

  const runCheck = () =>
    guard(async () => {
      const next = await checkRepo(repo.trim())
      setCheck(next)
      setPreview(null)
      setAccess(null)
      // Carried over so the user is not retyping what the repository already states.
      if (next.ok && next.description) setDescription(next.description)
    })

  const runPreview = () =>
    guard(async () => {
      const next = await previewOnboarding({
        repo: repo.trim(),
        include_patterns: toPatterns(includeText),
        exclude_patterns: toPatterns(excludeText),
      })
      setPreview(next)
    })

  const runAccessCheck = () =>
    guard(async () => {
      setAccess(await checkServiceAccount(repo.trim()))
    })

  const runComplete = () =>
    guard(async () => {
      const next = await completeOnboarding({
        repo: repo.trim(),
        description: description.trim(),
        include_patterns: toPatterns(includeText),
        exclude_patterns: toPatterns(excludeText),
      })
      setResult(next)
      toast.show(`${next.repository} onboarded.`, 'success')
    })

  const canAdvance = [
    Boolean(check?.ok),
    Boolean(preview?.ok),
    Boolean(access?.ok && access.permissions?.review),
    Boolean(webhook),
    true,
  ][step]

  return (
    <div className="space-y-4">
      <ol className="flex flex-wrap items-center gap-x-6 gap-y-2">
        {STEPS.map((label, index) => (
          <StepChip
            key={label}
            index={index}
            label={label}
            done={index < step || (index === 4 && Boolean(result))}
            active={index === step}
          />
        ))}
      </ol>

      {error && (
        <p role="alert" className="flex items-start gap-1.5 rounded-lg bg-rose-50 px-3 py-2 text-xs text-rose-800">
          <AlertIcon className="mt-px size-3.5 shrink-0" />
          {error}
        </p>
      )}

      {step === 0 && (
        <Card>
          <CardHeader title="Which repository?" meta="Step 1 of 5" />
          <div className="space-y-3 p-4">
            <div className="flex flex-wrap items-end gap-2">
              <div className="min-w-[16rem] flex-1">
                <TextInput
                  label="Repository"
                  placeholder="owner/name, or paste the repository URL"
                  value={repo}
                  onChange={(event) => {
                    setRepo(event.target.value)
                    setCheck(null)
                  }}
                  disabled={Boolean(check?.ok)}
                  spellCheck={false}
                />
              </div>
              <Button onClick={runCheck} busy={pending} variant="primary" disabled={!repo.trim()}>
                {check?.ok ? 'Check again' : 'Check access'}
              </Button>
              {check?.ok && (
                <Button onClick={() => { setCheck(null); setRepo('') }}>Change</Button>
              )}
            </div>
            {check && (
              <Verdict ok={check.ok}>
                {check.ok ? (
                  <>
                    Our service account can see <strong>{check.repository}</strong>
                    {check.language ? ` · ${check.language}` : ''}
                    {check.private ? ' · private' : ''}
                    {check.default_branch ? ` · default branch ${check.default_branch}` : ''}
                  </>
                ) : (
                  check.detail || 'That repository is not visible to our service account yet.'
                )}
              </Verdict>
            )}
          </div>
        </Card>
      )}

      {step === 1 && (
        <Card>
          <CardHeader title="Describe it and set exclusions" meta="Step 2 of 5" />
          <div className="space-y-4 p-4">
            <Textarea
              label="Description"
              rows={3}
              value={description}
              onChange={(event) => setDescription(event.target.value)}
              placeholder="What this application does, in a sentence or two."
            />
            <div className="grid gap-3 sm:grid-cols-2">
              <Textarea
                label="Only include these paths"
                rows={4}
                value={includeText}
                onChange={(event) => setIncludeText(event.target.value)}
                placeholder={'Leave blank to include everything.\nservices/api/*'}
                hint="One pattern per line. Blank means everything not excluded."
              />
              <Textarea
                label="Exclude these paths"
                rows={4}
                value={excludeText}
                onChange={(event) => setExcludeText(event.target.value)}
                placeholder={'*.min.js\ndocs/*\nvendor'}
                hint="Always wins over the include list."
              />
            </div>
            <div className="flex flex-wrap items-center gap-2">
              <Button onClick={runPreview} busy={pending}>
                Preview what would be indexed
              </Button>
            </div>
            {preview && (
              <div className="rounded-lg border border-line bg-canvas p-3">
                <dl className="grid grid-cols-2 gap-3 sm:grid-cols-4">
                  {[
                    { label: 'Files in archive', value: preview.counts.total_files },
                    { label: 'Would be indexed', value: preview.counts.to_index },
                    { label: 'Skipped by our filters', value: preview.counts.builtin_skipped },
                    { label: 'Skipped by your patterns', value: preview.counts.your_patterns_skipped },
                  ].map((stat) => (
                    <div key={stat.label}>
                      <dd className="text-sm font-semibold text-ink tabular-nums">
                        {stat.value.toLocaleString()}
                      </dd>
                      <dt className="mt-0.5 text-[10px] leading-tight text-ink-muted">{stat.label}</dt>
                    </div>
                  ))}
                </dl>
                <p className="mt-3 text-[11px] leading-relaxed text-ink-muted">
                  &ldquo;Skipped by our filters&rdquo; counts files this application never indexes —
                  binaries, lockfiles and dependency trees. The rules are fixed and shown only as a
                  total.
                </p>
              </div>
            )}
          </div>
        </Card>
      )}

      {step === 2 && (
        <Card>
          <CardHeader title="Grant our service account access" meta="Step 3 of 5" />
          <div className="space-y-3 p-4">
            <p className="text-xs leading-relaxed text-ink-soft">
              On GitHub, open <strong>{check?.repository || repo}</strong> → Settings →
              Collaborators, and add the ContextGuard service account with <strong>write</strong>{' '}
              access. Write access is what lets us post review comments; read alone would let us
              index the repository but not review it.
            </p>
            <Button onClick={runAccessCheck} busy={pending} variant="primary">
              I have granted access — check again
            </Button>
            {access && (
              <Verdict ok={Boolean(access.ok && access.permissions?.review)}>
                {access.detail}
                {access.permissions && (
                  <span className="mt-1.5 flex flex-wrap gap-1.5">
                    <Badge tone={access.permissions.read ? 'success' : 'danger'}>read</Badge>
                    <Badge tone={access.permissions.review ? 'success' : 'warning'}>comment</Badge>
                    <Badge tone={access.permissions.admin ? 'success' : 'neutral'}>admin</Badge>
                  </span>
                )}
              </Verdict>
            )}
          </div>
        </Card>
      )}

      {step === 3 && (
        <Card>
          <CardHeader title="Configure the webhook" meta="Step 4 of 5" />
          <div className="space-y-3 p-4 text-xs leading-relaxed text-ink-soft">
            <p>
              On <strong>{check?.repository || repo}</strong> → Settings → Webhooks → Add webhook,
              and set:
            </p>
            <dl className="space-y-2 rounded-lg border border-line bg-canvas p-3">
              {[
                { label: 'Payload URL', value: webhook?.payload_url ?? '—' },
                { label: 'Content type', value: webhook?.content_type ?? 'application/json' },
                {
                  label: 'Secret',
                  value: webhook
                    ? `the value of ${webhook.secret_env}${webhook.secret_configured ? '' : ' (not set on this server!)'}`
                    : '—',
                },
              ].map((row) => (
                <div key={row.label} className="flex flex-wrap items-baseline gap-x-2">
                  <dt className="w-28 shrink-0 text-[10px] font-semibold tracking-[0.08em] text-ink-muted uppercase">
                    {row.label}
                  </dt>
                  <dd className="font-mono text-[11px] break-all text-ink">{row.value}</dd>
                </div>
              ))}
            </dl>
            <p>Subscribe it to these events:</p>
            <ul className="flex flex-wrap gap-1.5">
              {(webhook?.events ?? []).map((event) => (
                <li key={event}>
                  <Badge tone="accent" caps={false}>{event}</Badge>
                </li>
              ))}
            </ul>
            {webhook?.note && (
              <p className="flex items-start gap-1.5 text-amber-800">
                <AlertIcon className="mt-px size-3.5 shrink-0" />
                {webhook.note}
              </p>
            )}
          </div>
        </Card>
      )}

      {step === 4 && (
        <Card>
          <CardHeader title="Confirm" meta="Step 5 of 5" />
          <div className="space-y-3 p-4">
            {result ? (
              <Verdict ok>
                <strong>{result.repository}</strong> is onboarded and indexed at{' '}
                <span className="font-mono">{result.commit_sha.slice(0, 8)}</span>. It now appears
                under Applications.
              </Verdict>
            ) : (
              <>
                <dl className="space-y-2 text-xs">
                  {[
                    { label: 'Repository', value: check?.repository ?? repo },
                    { label: 'Would index', value: `${preview?.counts.to_index ?? 0} files` },
                    { label: 'Your exclusions', value: `${toPatterns(excludeText).length}` },
                  ].map((row) => (
                    <div key={row.label} className="flex items-baseline justify-between gap-3">
                      <dt className="text-ink-muted">{row.label}</dt>
                      <dd className="font-medium text-ink">{row.value}</dd>
                    </div>
                  ))}
                </dl>
                <Button onClick={runComplete} busy={pending} variant="primary">
                  Save and index this repository
                </Button>
              </>
            )}
          </div>
        </Card>
      )}

      <div className="flex items-center justify-between gap-2">
        <Button onClick={() => setStep((value) => Math.max(0, value - 1))} disabled={step === 0}>
          Back
        </Button>
        <Button
          onClick={() => setStep((value) => Math.min(STEPS.length - 1, value + 1))}
          disabled={!canAdvance || step === STEPS.length - 1}
          variant="primary"
        >
          Next
        </Button>
      </div>
    </div>
  )
}
