import type {
  Credential,
  CredentialsResponse,
  DashboardData,
  DashboardQuery,
  FindingFilters,
  FindingSort,
  FindingsResponse,
  OnboardingPreview,
  OnboardingResult,
  RepoCheck,
  RepositoryCommits,
  ReviewFilters,
  ReviewsResponse,
  ServiceAccountCheck,
  SessionUser,
  Verification,
  WebhookInstructions,
} from '../types'
import { errorDetail } from './format'

/** Every failure below is one of these, so callers never have to inspect a raw Response. */
export class ApiError extends Error {
  readonly status: number

  constructor(message: string, status = 0) {
    super(message)
    this.name = 'ApiError'
    this.status = status
  }
}

export function isAbort(error: unknown): boolean {
  return error instanceof DOMException && error.name === 'AbortError'
}

export function messageOf(error: unknown, fallback = 'Something went wrong.'): string {
  return error instanceof Error && error.message ? error.message : fallback
}

async function parse<T>(response: Response, fallback: string): Promise<T> {
  const body: unknown = await response.json().catch(() => null)
  if (!response.ok) {
    throw new ApiError(errorDetail(body, `${fallback} (HTTP ${response.status})`), response.status)
  }
  return body as T
}

/**
 * The credential routes are gated by an optional shared token. Empty means "not configured", in
 * which case the header is omitted entirely rather than sent blank.
 */
function adminHeader(adminToken: string): Record<string, string> {
  return adminToken ? { 'X-Admin-Token': adminToken } : {}
}

/**
 * The CSRF token, read from its cookie and echoed in a header.
 *
 * The session cookie is sent automatically, so without this a third-party page could drive the
 * mutating endpoints as the signed-in user. A cross-origin page cannot read this cookie, which is
 * what makes the comparison on the server meaningful.
 */
function csrfHeader(): Record<string, string> {
  const match = document.cookie.match(/(?:^|;\s*)cg_csrf=([^;]+)/)
  return match ? { 'X-CSRF-Token': decodeURIComponent(match[1]) } : {}
}

/** Every mutating request to this API must go through here. */
function mutationHeaders(extra: Record<string, string> = {}): Record<string, string> {
  return { ...extra, ...csrfHeader() }
}

export async function fetchDashboard(query: DashboardQuery, signal?: AbortSignal): Promise<DashboardData> {
  const url = new URL('/api/dashboard', window.location.origin)
  // The backend treats 'All' and a missing param identically, so only send real filters.
  if (query.language && query.language !== 'All') url.searchParams.set('language', query.language)
  if (query.q) url.searchParams.set('q', query.q)

  const response = await fetch(url, { signal, headers: { Accept: 'application/json' } })
  return parse<DashboardData>(response, 'Could not load dashboard data')
}

export async function fetchFindings(
  filters: FindingFilters,
  sort: FindingSort = 'severity',
  signal?: AbortSignal,
): Promise<FindingsResponse> {
  const url = new URL('/api/findings', window.location.origin)
  for (const [key, value] of Object.entries(filters)) {
    // 'all' is the UI's "no filter"; the API treats it the same, so it is not worth sending.
    if (value && value !== 'all') url.searchParams.set(key, value)
  }
  if (sort !== 'severity') url.searchParams.set('sort', sort)
  const response = await fetch(url, { signal, headers: { Accept: 'application/json' } })
  return parse<FindingsResponse>(response, 'Could not load findings')
}

export async function fetchReviews(
  filters: ReviewFilters,
  signal?: AbortSignal,
): Promise<ReviewsResponse> {
  const url = new URL('/api/reviews', window.location.origin)
  for (const [key, value] of Object.entries(filters)) {
    if (value && value !== 'all') url.searchParams.set(key, value)
  }
  const response = await fetch(url, { signal, headers: { Accept: 'application/json' } })
  return parse<ReviewsResponse>(response, 'Could not load reviews')
}

export async function fetchRepositoryCommits(
  repo: string,
  signal?: AbortSignal,
): Promise<RepositoryCommits> {
  const [owner, name] = repo.split('/')
  const response = await fetch(
    `/api/repositories/${encodeURIComponent(owner)}/${encodeURIComponent(name)}/commits`,
    { signal, headers: { Accept: 'application/json' } },
  )
  return parse<RepositoryCommits>(response, 'Could not load that repository’s commits')
}

/* --- session ------------------------------------------------------------------------------- */

export async function fetchMe(signal?: AbortSignal): Promise<SessionUser> {
  const response = await fetch('/api/me', { signal, headers: { Accept: 'application/json' } })
  return parse<SessionUser>(response, 'Could not read your session')
}

export async function signIn(username: string, password: string): Promise<SessionUser> {
  const response = await fetch('/auth/login', {
    method: 'POST',
    headers: mutationHeaders({ 'Content-Type': 'application/json' }),
    body: JSON.stringify({ username, password }),
  })
  return parse<SessionUser>(response, 'Sign-in failed')
}

export async function signOut(): Promise<void> {
  await fetch('/api/logout', { method: 'POST', headers: mutationHeaders() })
}

export async function disconnectGitHub(): Promise<void> {
  const response = await fetch('/api/github/disconnect', {
    method: 'POST',
    headers: mutationHeaders(),
  })
  await parse(response, 'Could not disconnect GitHub')
}

/* --- onboarding ---------------------------------------------------------------------------- */

export async function checkRepo(repo: string): Promise<RepoCheck> {
  const response = await fetch('/api/onboarding/check-repo', {
    method: 'POST',
    headers: mutationHeaders({ 'Content-Type': 'application/json' }),
    body: JSON.stringify({ repo }),
  })
  return parse<RepoCheck>(response, 'Could not check that repository')
}

export async function checkServiceAccount(repo: string): Promise<ServiceAccountCheck> {
  const response = await fetch('/api/onboarding/service-account', {
    method: 'POST',
    headers: mutationHeaders({ 'Content-Type': 'application/json' }),
    body: JSON.stringify({ repo }),
  })
  return parse<ServiceAccountCheck>(response, 'Could not check service-account access')
}

export async function previewOnboarding(input: {
  repo: string
  include_patterns: string[]
  exclude_patterns: string[]
}): Promise<OnboardingPreview> {
  const response = await fetch('/api/onboarding/preview', {
    method: 'POST',
    headers: mutationHeaders({ 'Content-Type': 'application/json' }),
    body: JSON.stringify(input),
  })
  return parse<OnboardingPreview>(response, 'Could not preview that repository')
}

export async function fetchWebhookInstructions(): Promise<WebhookInstructions> {
  const response = await fetch('/api/onboarding/webhook', {
    headers: { Accept: 'application/json' },
  })
  return parse<WebhookInstructions>(response, 'Could not read the webhook setup')
}

export async function completeOnboarding(input: {
  repo: string
  description: string
  include_patterns: string[]
  exclude_patterns: string[]
}): Promise<OnboardingResult> {
  const response = await fetch('/api/onboarding/complete', {
    method: 'POST',
    headers: mutationHeaders({ 'Content-Type': 'application/json' }),
    body: JSON.stringify(input),
  })
  return parse<OnboardingResult>(response, 'Could not complete onboarding')
}

export async function fetchCredentials(signal?: AbortSignal): Promise<CredentialsResponse> {
  const response = await fetch('/api/credentials', { signal, headers: { Accept: 'application/json' } })
  return parse<CredentialsResponse>(response, 'Could not load credentials')
}

export async function saveCredential(
  owner: string,
  token: string,
  adminToken: string,
): Promise<Credential> {
  const response = await fetch(`/api/credentials/${encodeURIComponent(owner)}`, {
    method: 'PUT',
    headers: mutationHeaders({ 'Content-Type': 'application/json', ...adminHeader(adminToken) }),
    body: JSON.stringify({ token }),
  })
  return parse<Credential>(response, 'Could not save the credential')
}

export async function verifyCredential(
  owner: string,
  adminToken: string,
): Promise<{ verification: Verification; credential: Credential }> {
  const response = await fetch(`/api/credentials/${encodeURIComponent(owner)}/verify`, {
    method: 'POST',
    headers: mutationHeaders(adminHeader(adminToken)),
  })
  return parse(response, 'Could not verify the credential')
}

export async function deleteCredential(
  owner: string,
  adminToken: string,
): Promise<{ deleted: boolean; owner: string }> {
  const response = await fetch(`/api/credentials/${encodeURIComponent(owner)}`, {
    method: 'DELETE',
    headers: mutationHeaders(adminHeader(adminToken)),
  })
  return parse(response, 'Could not delete that credential')
}
