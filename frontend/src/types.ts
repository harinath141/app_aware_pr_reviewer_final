/**
 * Shapes returned by the FastAPI backend. These mirror the serialisers in app/main.py and
 * app/credentials.py exactly - check those before changing a field name here.
 *
 * The knowledge-graph types are deliberately absent: the graph has no UI, only API endpoints.
 * If a view is ever added, its shapes belong here.
 */

export interface DashboardStats {
  projects: number
  reviews: number
  issues_found: number
  security_issues: number
  issues_fixed: number
  issues_open: number
  snapshots: number
  high_risk_open: number
  issues_invalid: number
}

export interface Repository {
  name: string
  language: string | null
  description: string | null
  latest_sha: string | null
  indexed_at: string | null
  files: number
  chunks: number
  symbols: number
  edges: number
}

export interface Review {
  id: number
  repo: string
  pr_number: number
  title: string | null
  url: string | null
  risk: string | null
  recommendation: string | null
  findings: number
  reviewed_at: string | null
  /** Only populated by /api/reviews, which joins these in. */
  commit_sha?: string | null
  language?: string | null
}

/** Every value defaults to 'all', which the API treats as "no filter". */
export interface ReviewFilters {
  repo: string
  language: string
  commit: string
  risk: string
}

export interface ReviewsResponse {
  reviews: Review[]
  total: number
  returned: number
  options: {
    projects: string[]
    languages: string[]
    commits: FindingCommitOption[]
    risks: string[]
  }
}

/** Ordering for the findings list; the API whitelists exactly these. */
export type FindingSort = 'severity' | 'recent' | 'oldest' | 'file' | 'category' | 'project'

export interface RepositoryCommit {
  sha: string
  /** Set when a pull-request review ran against this commit. */
  reviewed_at: string | null
  /** Set when a push caused this commit to be indexed. */
  indexed_at: string | null
  reviews: number
  findings: number
  files: number | null
  chunks: number | null
}

export interface RepositoryCommits {
  repository: string
  commits: RepositoryCommit[]
}

export interface Finding {
  id: number
  repo: string
  pr_number: number
  title: string
  severity: string
  category: string
  file: string | null
  evidence: string | null
  scenario: string | null
  impact: string | null
  recommendation: string | null
  /** 'open' by default; only GitHub triage moves it on. */
  status: string
  created_at: string | null
  anchor_line: number | null
  line: number | null
  comment_url: string | null
  status_actor: string | null
  status_updated_at: string | null
  /** Only populated by /api/findings, which joins these in. */
  language?: string | null
  commit_sha?: string | null
}

export interface LanguageCount {
  name: string
  count: number
}

export interface DashboardData {
  stats: DashboardStats
  languages: LanguageCount[]
  repositories: Repository[]
  reviews: Review[]
  findings: Finding[]
}

/* --- filterable findings ------------------------------------------------------------------ */

/** Every value defaults to 'all', which the API treats as "no filter". */
export interface FindingFilters {
  repo: string
  language: string
  commit: string
  status: string
  severity: string
}

export interface FindingCommitOption {
  sha: string
  repo: string
  reviewed_at: string | null
}

export interface FindingsOptions {
  projects: string[]
  languages: string[]
  commits: FindingCommitOption[]
  statuses: string[]
  severities: string[]
}

export interface FindingsResponse {
  findings: Finding[]
  /** Matches before the row cap; `returned` is how many came back. */
  total: number
  returned: number
  options: FindingsOptions
}

/* --- credentials -------------------------------------------------------------------------- */

/** 'missing' and 'invalid' both block storing tokens; only 'ok' allows writes. */
export type KeyStatus = 'ok' | 'missing' | 'invalid'

export interface Credential {
  owner: string
  owner_login: string | null
  /** Masked, e.g. `ghp_…4f2a`. The token itself is never returned by any endpoint. */
  token_hint: string
  verified_login: string | null
  scopes: string | null
  repo_access_count: number | null
  owner_is_org: boolean | null
  last_verified_at: string | null
  last_verification_status: string | null
  last_verification_detail: string | null
  created_at: string | null
  updated_at: string | null
}

export interface CredentialsResponse {
  key_status: KeyStatus
  credentials: Credential[]
  global_fallback: { configured: boolean; token_hint: string | null }
  admin_token_required: boolean
}

export interface Verification {
  status: string
  detail?: string | null
  http_status?: number
  verified_login?: string | null
}

export interface DashboardQuery {
  language: string
  q: string
}

/* --- session ------------------------------------------------------------------------------- */

export interface SessionUser {
  username: string
  display_name: string
  /** From LDAP group membership: CONTEXTGUARD-ADMIN or CONTEXTGUARD-USER. */
  role: 'admin' | 'user'
  github_login: string | null
  github_connected: boolean
  /** False means this deployment runs with sign-in switched off. */
  auth_required: boolean
  oauth_available?: boolean
}

/* --- onboarding ----------------------------------------------------------------------------- */

export interface RepoCheck {
  ok: boolean
  repository: string
  status: number
  detail?: string
  default_branch?: string
  language?: string
  private?: boolean
  description?: string
}

export interface ServiceAccountCheck {
  ok: boolean
  repository: string
  status: number
  detail: string
  permissions?: { read: boolean; review: boolean; admin: boolean }
}

export interface OnboardingPreview {
  ok: boolean
  repository: string
  ref: string
  counts: {
    total_files: number
    to_index: number
    /** A count only - the built-in filter rules are never named. */
    builtin_skipped: number
    your_patterns_skipped: number
  }
  sample_paths: string[]
}

export interface WebhookInstructions {
  payload_url: string
  content_type: string
  secret_env: string
  secret_configured: boolean
  events: string[]
  note: string
}

export interface OnboardingResult {
  ok: boolean
  repository: string
  commit_sha: string
  indexing: Record<string, unknown>
}
