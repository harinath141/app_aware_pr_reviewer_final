from app.formatting import (finding_marker, has_status, annotate_status, render_finding_comment)

FINDING = {"title": "Unvalidated input", "severity": "high", "category": "security",
           "confidence": "high", "file": "app/x.py", "evidence": "e", "failure_scenario": "s",
           "impact": "i", "recommendation": "r"}

CMD = "`/resolved`"

def test_finding_marker_is_stable():
    assert finding_marker(12) == "<!-- finding-id:12 -->"

def test_annotate_prepends_the_banner_and_keeps_the_body():
    out = annotate_status("original body\n\nmore", "resolved", "alice", CMD, "2026-01-01 00:00 UTC")
    assert out.startswith("> **✅ Resolved** — set by @alice via `/resolved`")
    assert "<!-- status:resolved -->" in out
    assert out.endswith("original body\n\nmore")

def test_banner_accepts_any_via_text():
    # The resolve button is a different source of truth than a typed command.
    out = annotate_status("body", "resolved", "alice", "the Resolve conversation button", "t")
    assert "via the Resolve conversation button" in out

def test_reannotating_the_same_status_is_idempotent():
    once = annotate_status("body", "resolved", "alice", CMD, "t")
    twice = annotate_status(once, "resolved", "alice", CMD, "t")
    assert twice.count("<!-- status:resolved -->") == 1
    assert twice.count("> **") == 1

def test_changing_status_replaces_the_previous_banner():
    resolved = annotate_status("body", "resolved", "alice", CMD, "t")
    invalid = annotate_status(resolved, "invalid", "bob", "`/invalid`", "t2")
    assert "<!-- status:invalid -->" in invalid
    assert "<!-- status:resolved -->" not in invalid
    assert invalid.endswith("body")

def test_human_edits_survive_a_status_change():
    edited = annotate_status("body", "resolved", "alice", CMD, "t") + "\n\nnote from bob"
    out = annotate_status(edited, "invalid", "bob", "`/invalid`", "t2")
    assert "note from bob" in out
    assert out.endswith("body\n\nnote from bob")

def test_unresolving_clears_the_banner():
    resolved = annotate_status("body", "resolved", "alice", CMD, "t")
    reopened = annotate_status(resolved, "open", "alice", "un-resolving the conversation", "t2")
    assert "<!-- status:open -->" in reopened
    assert "<!-- status:resolved -->" not in reopened
    assert reopened.endswith("body")

def test_has_status():
    body = annotate_status("body", "resolved", "a", CMD, "t")
    assert has_status(body, "resolved")
    assert not has_status(body, "invalid")

def test_inline_comment_asks_for_a_reply():
    out = render_finding_comment(FINDING, 5, 12, inline=True)
    assert finding_marker(5) in out
    assert "app/x.py:12" in out
    assert "`/resolved`" in out
    assert "`/resolved 5`" not in out

def test_standalone_comment_requires_the_finding_id():
    # A timeline comment cannot be threaded, so the command has to carry the id.
    out = render_finding_comment(FINDING, 5, None, inline=False)
    assert "`/resolved 5`" in out
    assert "`/invalid 5`" in out

def test_line_is_omitted_when_unknown():
    out = render_finding_comment(FINDING, 5, None, inline=True)
    assert "app/x.py`" in out
