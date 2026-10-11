from app.commands import parse_command
from app.main import is_our_comment, thread_status_transition, thread_state_for_status

def test_plain_commands():
    assert parse_command("/resolved") == ("resolved", None)
    assert parse_command("/invalid") == ("invalid", None)

def test_command_with_finding_id():
    assert parse_command("/resolved 42") == ("resolved", 42)
    assert parse_command("/invalid 7") == ("invalid", 7)

def test_leading_whitespace_and_blank_lines():
    assert parse_command("\n\n   /resolved   ") == ("resolved", None)

def test_case_insensitive():
    assert parse_command("/Resolved") == ("resolved", None)

def test_quoted_command_is_ignored():
    # GitHub quote-replies prefix every quoted line with "> ". Quoting an earlier command must
    # not re-trigger it.
    assert parse_command("> /resolved 42\n\nLooks good to me") is None

def test_no_command():
    assert parse_command("please fix this") is None
    assert parse_command("") is None
    assert parse_command(None) is None

def test_unknown_commands_are_not_matched():
    assert parse_command("/not-sure") is None     # the 3-state model has no not-sure
    assert parse_command("/approved 1") is None

def test_first_command_wins():
    assert parse_command("/resolved 3\n/invalid 4") == ("resolved", 3)

def test_thread_event_can_resolve_and_reopen():
    assert thread_status_transition("open", "resolved") == "resolved"
    assert thread_status_transition("resolved", "unresolved") == "open"

def test_thread_event_never_overrides_an_explicit_invalid():
    # Replying auto-resolves the thread, so this event follows every reply. It must not turn
    # the reviewer's /invalid into a resolved.
    assert thread_status_transition("invalid", "resolved") is None
    assert thread_status_transition("invalid", "unresolved") is None

def test_thread_event_ignores_redundant_transitions():
    assert thread_status_transition("resolved", "resolved") is None
    assert thread_status_transition("open", "unresolved") is None
    assert thread_status_transition("open", "edited") is None

def test_settled_findings_resolve_their_thread():
    # Otherwise an unresolved conversation blocks merging on a protected branch.
    assert thread_state_for_status("resolved") is True
    assert thread_state_for_status("invalid") is True

def test_reopening_a_finding_reopens_the_thread():
    assert thread_state_for_status("open") is False

def test_our_own_comments_are_recognised():
    # These carry the markers we embed; the app must never act on its own comments.
    assert is_our_comment("## [HIGH] x\n<!-- finding-id:12 -->\n/reply instructions")
    assert is_our_comment("_App-Aware PR Reviewer — Context-First MVP_")
    assert not is_our_comment("/resolved 42")
    assert not is_our_comment(None)
