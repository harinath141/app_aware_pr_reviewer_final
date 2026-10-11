import { useEffect, useMemo, useState } from 'react'
import { ApplicationsSection } from './components/applications/ApplicationsSection'
import { AccountPanel } from './components/auth/AccountPanel'
import { LoginScreen } from './components/auth/LoginScreen'
import { InsightsSection } from './components/charts/InsightsSection'
import { StatsSection } from './components/dashboard/StatsSection'
import { WorkflowSection } from './components/dashboard/WorkflowSection'
import { FindingsSection } from './components/findings/FindingsSection'
import { AppShell } from './components/layout/AppShell'
import { Section } from './components/layout/Section'
import { OnboardSection } from './components/onboarding/OnboardSection'
import { SettingsSection } from './components/settings/SettingsSection'
import { Button } from './components/ui/Button'
import { Select, TextInput } from './components/ui/Field'
import { ErrorState } from './components/ui/States'
import { RefreshIcon } from './components/ui/icons'
import { useDashboard, useDebounced, useSession } from './lib/hooks'
import { count } from './lib/format'
import { NAV_ITEMS, isTabId } from './lib/nav'
import type { TabId } from './lib/nav'
import type { SessionUser } from './types'

/** The tab ids double as URL hashes, so /#projects opens the applications tab directly. */
function tabFromHash(): TabId {
  const id = window.location.hash.replace(/^#/, '')
  return isTabId(id) ? id : 'overview'
}

function ConnectionPill({ state }: { state: 'connected' | 'connecting' | 'error' }) {
  const styles = {
    connected: 'border-emerald-200 bg-emerald-50 text-emerald-700',
    connecting: 'border-line bg-canvas text-ink-muted',
    error: 'border-rose-200 bg-rose-50 text-rose-700',
  }[state]
  const dot = {
    connected: 'bg-emerald-500',
    connecting: 'bg-slate-400',
    error: 'bg-rose-500',
  }[state]
  const label = {
    connected: 'Dashboard connected',
    connecting: 'Connecting…',
    error: 'Connection problem',
  }[state]

  return (
    <span
      className={`hidden items-center gap-1.5 rounded-full border px-2.5 py-1 text-[11px] font-medium sm:inline-flex ${styles}`}
    >
      <span className={`size-1.5 rounded-full ${dot}`} />
      {label}
    </span>
  )
}

function BootScreen() {
  return (
    <div className="flex min-h-screen items-center justify-center bg-canvas">
      <p className="text-sm text-ink-muted">Loading…</p>
    </div>
  )
}

/**
 * Everything behind the sign-in gate.
 *
 * Split from App so that no dashboard component - and therefore no data request - is ever mounted
 * for a signed-out browser. The server would refuse those requests anyway; not making them at all
 * is better.
 */
function Dashboard({ user, onSessionChange }: { user: SessionUser; onSessionChange: () => void }) {
  const [tab, setTab] = useState<TabId>(tabFromHash)
  const [search, setSearch] = useState('')
  const [language, setLanguage] = useState('All')

  useEffect(() => {
    const onHashChange = () => setTab(tabFromHash())
    window.addEventListener('hashchange', onHashChange)
    return () => window.removeEventListener('hashchange', onHashChange)
  }, [])

  const selectTab = (id: TabId) => {
    if (window.location.hash !== `#${id}`) window.location.hash = id
    setTab(id)
  }

  const debouncedSearch = useDebounced(search, 300)
  const query = useMemo(
    () => ({ language, q: debouncedSearch.trim() }),
    [language, debouncedSearch],
  )
  const { data, loading, error, reload } = useDashboard(query)

  const isAdmin = user.role === 'admin'
  const languages = data?.languages ?? []
  const repositories = data?.repositories ?? null
  const applicationCount = repositories?.length ?? 0
  const activeLabel = NAV_ITEMS.find((item) => item.id === tab)?.label ?? 'Overview'

  const fatal = Boolean(error) && !data
  // Connecting GitHub is what decides which repositories are visible, so an unconnected session
  // is worth saying out loud rather than leaving as a thin sidebar button.
  const needsGitHub = user.auth_required && !user.github_connected && user.oauth_available

  return (
    <AppShell
      active={tab}
      onSelect={selectTab}
      isAdmin={isAdmin}
      footer={<AccountPanel user={user} onChange={onSessionChange} />}
    >
      <header className="flex flex-wrap items-end justify-between gap-x-6 gap-y-4">
        <div>
          <p className="text-[11px] font-semibold tracking-[0.14em] text-accent uppercase">
            {activeLabel}
          </p>
          <h1 className="mt-1.5 text-2xl font-semibold tracking-tight text-ink">
            Application review dashboard
          </h1>
          <p className="mt-1 text-sm text-ink-soft">
            Your codebase knowledge, PR quality and security posture in one place.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <ConnectionPill state={fatal ? 'error' : data ? 'connected' : 'connecting'} />
          <Button onClick={reload} busy={loading && Boolean(data)}>
            <RefreshIcon />
            Refresh data
          </Button>
        </div>
      </header>

      {needsGitHub && (
        <div className="mt-6 flex flex-wrap items-center justify-between gap-3 rounded-xl border border-accent-line bg-accent-soft px-4 py-3">
          <p className="text-xs leading-relaxed text-accent-strong">
            Connect your GitHub account to see the repositories you have access to. Until then you
            will only see applications you onboard yourself.
          </p>
          <Button
            size="sm"
            variant="primary"
            onClick={() => {
              window.location.href = '/oauth/github/start'
            }}
          >
            Connect GitHub
          </Button>
        </div>
      )}

      {fatal ? (
        <div className="mt-6">
          <ErrorState message={error ?? 'Could not load dashboard data.'} onRetry={reload} />
        </div>
      ) : (
        <div className="mt-6">
          {tab === 'overview' && (
            <>
              <StatsSection stats={data?.stats ?? null} />
              <Section
                id="insights"
                title="Insights"
                description="How the findings break down by status, language and review activity. Every chart has a table view."
              >
                <InsightsSection data={data} />
              </Section>
              <Section
                id="workflow"
                title="How ContextGuard works"
                description="Every push updates application knowledge; each pull request is reviewed against that knowledge."
              >
                <WorkflowSection />
              </Section>
            </>
          )}

          {tab === 'projects' && (
            <Section
              id="projects"
              title="Applications"
              description={
                repositories
                  ? `${count(applicationCount)} application${applicationCount === 1 ? '' : 's'} match your filters. Pick one to see its commits, and a commit to see the reviews and findings it produced.`
                  : 'Applications discovered from indexed repository snapshots.'
              }
              actions={
                <>
                  <div className="w-full sm:w-60">
                    <TextInput
                      label="Search applications"
                      placeholder="Search apps or descriptions…"
                      value={search}
                      onChange={(event) => setSearch(event.target.value)}
                    />
                  </div>
                  <Select
                    label="Language"
                    value={language}
                    onChange={(event) => setLanguage(event.target.value)}
                  >
                    <option value="All">All languages</option>
                    {languages.map((entry) => (
                      <option key={entry.name} value={entry.name}>
                        {entry.name} ({entry.count})
                      </option>
                    ))}
                  </Select>
                </>
              }
            >
              <ApplicationsSection repositories={repositories} />
            </Section>
          )}

          {tab === 'onboard' && (
            <Section
              id="onboard"
              title="Onboard a repository"
              description="Each step is verified against GitHub before you can move on, so a step cannot be completed by looking right."
            >
              <OnboardSection />
            </Section>
          )}

          {tab === 'findings' && (
            <Section
              id="findings"
              title="Security & quality findings"
              description={
                <>
                  Status is set by replying{' '}
                  <code className="rounded bg-canvas px-1 py-0.5">/resolved</code> or{' '}
                  <code className="rounded bg-canvas px-1 py-0.5">/invalid</code> on the
                  finding&apos;s own PR comment. Findings stay open until a human does.
                </>
              }
            >
              <FindingsSection />
              <p className="mt-5 text-[11px] leading-relaxed text-ink-muted">
                Findings cover reviews recorded since this dashboard version was deployed;
                historical reviews are not backfilled. &ldquo;Resolved&rdquo; means a reviewer
                replied <code className="rounded bg-canvas px-1 py-0.5">/resolved</code> on the
                finding&apos;s PR comment — it is not automatically verified by a test run.
              </p>
            </Section>
          )}

          {tab === 'settings' && isAdmin && (
            <Section
              id="settings"
              title="GitHub credentials"
              description="One token per owner or organisation, applied to every repository under it. Owners without a stored credential fall back to the server's default token."
            >
              <SettingsSection />
            </Section>
          )}
        </div>
      )}
    </AppShell>
  )
}

export default function App() {
  const { user, loading, error, refresh, setUser } = useSession()

  if (loading) return <BootScreen />

  if (!user) {
    return (
      <>
        <LoginScreen
          onSignedIn={(signedIn) => {
            setUser(signedIn)
            refresh()
          }}
        />
        {error && (
          <p role="alert" className="pb-6 text-center text-xs text-rose-700">
            {error}
          </p>
        )}
      </>
    )
  }

  return <Dashboard user={user} onSessionChange={refresh} />
}
