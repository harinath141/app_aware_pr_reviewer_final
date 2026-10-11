const STEPS = [
  {
    step: '01 / INGEST',
    title: 'Connect repositories',
    body: 'GitHub push events identify a commit snapshot to index.',
  },
  {
    step: '02 / UNDERSTAND',
    title: 'Build app knowledge',
    body: 'Store code chunks and embeddings, extract symbols and candidate relationships, inspect docs and manifests.',
  },
  {
    step: '03 / REVIEW',
    title: 'Trace change impact',
    body: 'Retrieve related application context and ask the reviewer to assess failure scenarios, regressions and security.',
  },
  {
    step: '04 / IMPROVE',
    title: 'Track and resolve',
    body: 'Review history and findings are recorded. Mark a finding resolved after verifying the fix.',
  },
]

export function WorkflowSection() {
  return (
    <ol className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
      {STEPS.map(({ step, title, body }, index) => (
        <li key={step} className="relative rounded-xl border border-line bg-surface p-4">
          <p className="text-[10px] font-semibold tracking-[0.12em] text-accent">{step}</p>
          <h3 className="mt-1.5 text-sm font-semibold text-ink">{title}</h3>
          <p className="mt-1 text-xs leading-relaxed text-ink-muted">{body}</p>
          {index < STEPS.length - 1 && (
            <span
              aria-hidden="true"
              className="absolute top-1/2 -right-2.5 hidden text-ink-muted xl:block"
            >
              →
            </span>
          )}
        </li>
      ))}
    </ol>
  )
}
