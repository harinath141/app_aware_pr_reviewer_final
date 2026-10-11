import { useCallback, useEffect, useState } from 'react'
import {
  ApiError,
  fetchDashboard,
  fetchFindings,
  fetchMe,
  fetchRepositoryCommits,
  fetchReviews,
  isAbort,
  messageOf,
} from './api'
import type {
  DashboardData,
  DashboardQuery,
  FindingFilters,
  FindingSort,
  FindingsResponse,
  RepositoryCommits,
  ReviewFilters,
  ReviewsResponse,
  SessionUser,
} from '../types'

/** Trailing-edge debounce, used so typing in the search box does not fire a request per keystroke. */
export function useDebounced<T>(value: T, delay = 300): T {
  const [debounced, setDebounced] = useState(value)

  useEffect(() => {
    const timer = setTimeout(() => setDebounced(value), delay)
    return () => clearTimeout(timer)
  }, [value, delay])

  return debounced
}

interface DashboardState {
  data: DashboardData | null
  loading: boolean
  error: string | null
  reload: () => void
}

/**
 * Loads the dashboard for the given filter. Filtering happens server-side (the API accepts
 * `language` and `q`), matching the original contract - stats, languages, reviews and findings
 * always come back global.
 */
export function useDashboard(query: DashboardQuery): DashboardState {
  const [data, setData] = useState<DashboardData | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [attempt, setAttempt] = useState(0)
  const { language, q } = query

  useEffect(() => {
    const controller = new AbortController()
    let cancelled = false

    setLoading(true)
    fetchDashboard({ language, q }, controller.signal)
      .then((next) => {
        if (cancelled) return
        setData(next)
        setError(null)
      })
      .catch((cause: unknown) => {
        // An aborted request is superseded by a newer one, not a failure worth showing.
        if (cancelled || isAbort(cause)) return
        setError(messageOf(cause, 'Could not load dashboard data.'))
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })

    return () => {
      cancelled = true
      controller.abort()
    }
  }, [language, q, attempt])

  const reload = useCallback(() => setAttempt((value) => value + 1), [])

  return { data, loading, error, reload }
}

/**
 * Findings for the current filter set, fetched from the server.
 *
 * Filtering happens there rather than over an already-fetched array: the dashboard payload caps
 * findings at the 20 most severe, and two of these filters - language and commit - are not in that
 * payload at all.
 */
export function useFindings(
  filters: FindingFilters,
  sort: FindingSort = 'severity',
  enabled = true,
): {
  data: FindingsResponse | null
  loading: boolean
  error: string | null
  reload: () => void
} {
  const [data, setData] = useState<FindingsResponse | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [attempt, setAttempt] = useState(0)
  const { repo, language, commit, status, severity } = filters

  useEffect(() => {
    // Callers can hold the request until a selection exists, so an empty filter set never fires.
    if (!enabled) {
      setLoading(false)
      return undefined
    }
    const controller = new AbortController()
    let cancelled = false

    setLoading(true)
    fetchFindings({ repo, language, commit, status, severity }, sort, controller.signal)
      .then((next) => {
        if (cancelled) return
        setData(next)
        setError(null)
      })
      .catch((cause: unknown) => {
        if (cancelled || isAbort(cause)) return
        setError(messageOf(cause, 'Could not load findings.'))
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })

    return () => {
      cancelled = true
      controller.abort()
    }
  }, [repo, language, commit, status, severity, sort, attempt, enabled])

  const reload = useCallback(() => setAttempt((value) => value + 1), [])

  return { data, loading, error, reload }
}

/** Review runs for the current filter set. Same reasoning as useFindings. */
export function useReviews(filters: ReviewFilters): {
  data: ReviewsResponse | null
  loading: boolean
  error: string | null
  reload: () => void
} {
  const [data, setData] = useState<ReviewsResponse | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [attempt, setAttempt] = useState(0)
  const { repo, language, commit, risk } = filters

  useEffect(() => {
    const controller = new AbortController()
    let cancelled = false

    setLoading(true)
    fetchReviews({ repo, language, commit, risk }, controller.signal)
      .then((next) => {
        if (cancelled) return
        setData(next)
        setError(null)
      })
      .catch((cause: unknown) => {
        if (cancelled || isAbort(cause)) return
        setError(messageOf(cause, 'Could not load reviews.'))
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })

    return () => {
      cancelled = true
      controller.abort()
    }
  }, [repo, language, commit, risk, attempt])

  const reload = useCallback(() => setAttempt((value) => value + 1), [])

  return { data, loading, error, reload }
}

/** Every commit known for one repository, newest first. Null repo means nothing is selected. */
export function useRepositoryCommits(repo: string | null): {
  data: RepositoryCommits | null
  loading: boolean
  error: string | null
} {
  const [data, setData] = useState<RepositoryCommits | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (!repo) {
      setData(null)
      return undefined
    }
    const controller = new AbortController()
    let cancelled = false

    setLoading(true)
    setError(null)
    fetchRepositoryCommits(repo, controller.signal)
      .then((next) => {
        if (!cancelled) setData(next)
      })
      .catch((cause: unknown) => {
        if (cancelled || isAbort(cause)) return
        setData(null)
        setError(messageOf(cause, 'Could not load that repository’s commits.'))
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })

    return () => {
      cancelled = true
      controller.abort()
    }
  }, [repo])

  return { data, loading, error }
}

/**
 * Who the browser is signed in as.
 *
 * A 401 is the ordinary signed-out state rather than a failure, so it sets `user` to null and
 * leaves `error` alone - the login screen is the correct response, not an error message.
 */
export function useSession(): {
  user: SessionUser | null
  loading: boolean
  error: string | null
  refresh: () => void
  setUser: (user: SessionUser | null) => void
} {
  const [user, setUser] = useState<SessionUser | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [attempt, setAttempt] = useState(0)

  useEffect(() => {
    const controller = new AbortController()
    let cancelled = false

    setLoading(true)
    fetchMe(controller.signal)
      .then((next) => {
        if (cancelled) return
        setUser(next)
        setError(null)
      })
      .catch((cause: unknown) => {
        if (cancelled || isAbort(cause)) return
        if (cause instanceof ApiError && cause.status === 401) {
          setUser(null)
          setError(null)
        } else {
          setError(messageOf(cause, 'Could not read your session.'))
        }
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })

    return () => {
      cancelled = true
      controller.abort()
    }
  }, [attempt])

  const refresh = useCallback(() => setAttempt((value) => value + 1), [])
  return { user, loading, error, refresh, setUser }
}

/** Runs an async action once, exposing a busy flag so buttons can disable themselves. */
export function usePending(): [boolean, <T>(action: () => Promise<T>) => Promise<T | undefined>] {
  const [pending, setPending] = useState(false)

  const run = useCallback(async <T,>(action: () => Promise<T>): Promise<T | undefined> => {
    setPending(true)
    try {
      return await action()
    } finally {
      setPending(false)
    }
  }, [])

  return [pending, run]
}
