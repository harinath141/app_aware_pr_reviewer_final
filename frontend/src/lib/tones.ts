/**
 * Maps backend enum values onto visual tones.
 *
 * The thresholds here are the same ones the original dashboard used, so a risk or severity reads
 * the same way it always did. They are kept in one file because they encode a backend contract -
 * if a new severity is ever added to the reviewer, this is the only place that needs to know.
 */

export type Tone = 'neutral' | 'accent' | 'success' | 'warning' | 'danger' | 'info'

export function riskTone(risk?: string | null): Tone {
  switch ((risk ?? '').toLowerCase()) {
    case 'critical':
    case 'high':
      return 'danger'
    case 'medium':
      return 'warning'
    case 'low':
      return 'success'
    default:
      return 'neutral'
  }
}

export function statusTone(status?: string | null): Tone {
  switch ((status ?? '').toLowerCase()) {
    case 'resolved':
      return 'success'
    case 'invalid':
      return 'danger'
    case 'open':
      return 'accent'
    default:
      return 'neutral'
  }
}

export function severityTone(severity?: string | null): Tone {
  switch ((severity ?? '').toLowerCase()) {
    case 'critical':
    case 'high':
      return 'danger'
    case 'medium':
      return 'warning'
    case 'low':
    case 'info':
      return 'info'
    default:
      return 'neutral'
  }
}

/**
 * Credential verification outcome. `ok` is the only clean result; `bad_credentials` and `error`
 * are refusals, and the remainder mean "stored, but with a caveat" - the backend detail for those
 * literally begins "Saved, but…", so they read as warnings rather than as plain successes.
 */
export function credentialTone(status?: string | null): Tone {
  switch ((status ?? '').toLowerCase()) {
    case 'ok':
      return 'success'
    case 'bad_credentials':
    case 'error':
      return 'danger'
    case 'no_repo_access':
    case 'owner_invisible':
    case 'insufficient_scope':
    case 'rate_limited':
      return 'warning'
    default:
      return 'neutral'
  }
}
