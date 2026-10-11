import re

def clip(v, limit=1500):
    s = str(v or "")
    return s if len(s) <= limit else s[:limit] + "…"

STATUS_LABEL = {"resolved": "✅ Resolved", "invalid": "🚫 Invalid", "open": "Open"}
# The banner we prepend when a reviewer sets a status. Matching the whole two-line block lets
# strip_status_banner remove exactly our own banner and leave human edits untouched.
STATUS_BLOCK_RE = re.compile(
    r"^> \*\*(?:✅ Resolved|🚫 Invalid)\*\*.*\n<!-- status:(?:open|resolved|invalid) -->\n?",
    re.MULTILINE)

def finding_marker(finding_id: int) -> str:
    """Hidden tag tying a posted comment back to its review_findings row."""
    return f"<!-- finding-id:{finding_id} -->"

def has_status(body: str, status: str) -> bool:
    return f"<!-- status:{status} -->" in (body or "")

def render_status_banner(status: str, actor: str | None, via: str | None, ts) -> str:
    """via is display-ready, e.g. "`/resolved`" or "the Resolve conversation button"."""
    who = f" by @{actor}" if actor else ""
    how = f" via {via}" if via else ""
    stamp = f" on {ts}" if ts else ""
    return (f"> **{STATUS_LABEL.get(status, status)}** — set{who}{how}{stamp}\n"
            f"<!-- status:{status} -->")

def annotate_status(body: str, status: str, actor: str | None, via: str | None, ts) -> str:
    """Prepend a status banner, replacing any previous one.

    Only our own banner is stripped, so anything a human edited into the comment survives.
    """
    base = STATUS_BLOCK_RE.sub("", body or "").lstrip("\n")
    return render_status_banner(status, actor, via, ts) + "\n\n" + base

def render_finding_comment(f: dict, finding_id: int, line: int | None, inline: bool) -> str:
    """One finding as its own PR comment, with instructions matching how it was posted."""
    where = clip(f.get("file") or "(file not specified)", 300)
    if line:
        where = f"{where}:{line}"
    lines = [f"## [{str(f.get('severity') or 'medium').upper()}] {clip(f.get('title') or 'Untitled finding', 300)}",
        "", finding_marker(finding_id), "",
        f"- **Confidence/category:** `{f.get('confidence', 'unknown')}` / `{f.get('category', 'unknown')}`",
        f"- **File:** `{where}`",
        f"- **Evidence:** {clip(f.get('evidence'))}",
        f"- **Failure scenario:** {clip(f.get('failure_scenario'))}",
        f"- **Impact:** {clip(f.get('impact'))}",
        f"- **Recommendation:** {clip(f.get('recommendation'))}",
        "", "---", "**Triage this finding**"]
    if inline:
        lines += ["Reply to *this* comment with exactly one command:",
            "- `/resolved` · fixed, or not a real problem",
            "- `/invalid` · false positive",
            "", "_Your reply sets the status in the reviewer dashboard and annotates this comment._"]
    else:
        # A timeline comment cannot be threaded, so the id has to travel in the command.
        lines += ["This finding could not be anchored to a diff line, so post a **new top-level",
            f"comment** (not a reply) beginning with the finding id:",
            f"- `/resolved {finding_id}` · fixed, or not a real problem",
            f"- `/invalid {finding_id}` · false positive",
            "", f"_Finding `#{finding_id}` — your command sets its status in the reviewer dashboard._"]
    return "\n".join(lines)

def render_comment(review: dict, context_count: int) -> str:
    lines = ["## App-Aware AI PR Review", "",
        f"**Risk:** `{review.get('risk', 'unknown')}`  ",
        f"**Recommendation:** `{review.get('merge_recommendation', 'review_required')}`  ",
        f"**Application context records retrieved:** `{context_count}`", "",
        "## Summary of changes", "",
        clip(review.get("summary", "No summary.")), "",
        "> AI-generated. Findings need human verification.",
        "", "### Findings"]
    findings = review.get("findings") or []
    if not findings:
        lines.append("No actionable findings returned; this is not proof the PR is defect-free.")
    for i, f in enumerate(findings[:20], 1):
        lines += ["", f"#### {i}. [{str(f.get('severity','medium')).upper()}] {clip(f.get('title'),300)}",
            f"- **Confidence/category:** `{f.get('confidence','unknown')}` / `{f.get('category','unknown')}`",
            f"- **File:** `{clip(f.get('file'),300)}`", f"- **Evidence:** {clip(f.get('evidence'))}",
            f"- **Failure scenario:** {clip(f.get('failure_scenario'))}", f"- **Impact:** {clip(f.get('impact'))}",
            f"- **Recommendation:** {clip(f.get('recommendation'))}"]
    lines += ["", "### Breaking scenarios to validate"]
    scenarios = review.get("breaking_scenarios") or []
    lines += [f"- **{clip(s.get('scenario'),400)}** — Preconditions: {clip(s.get('preconditions'),400)}; "
              f"Expected: {clip(s.get('expected_result'),400)}; Test: {clip(s.get('test_idea'),600)}"
              for s in scenarios[:12]] or ["- None returned."]
    lines += ["", "### Test gaps"]
    lines += [f"- {clip(x,500)}" for x in (review.get("test_gaps") or [])[:15]] or ["- None identified."]
    lines += ["", "---",
        "_Each finding is also posted as its own comment. Triage them there with `/resolved` or "
        "`/invalid`; the reviewer dashboard reflects whatever you decide._"]
    return "\n".join(lines + ["", "_App-Aware PR Reviewer — Context-First MVP_"])
