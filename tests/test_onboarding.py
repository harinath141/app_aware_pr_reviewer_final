from app.config import settings
from app.onboarding import WEBHOOK_EVENTS, split_repo, webhook_instructions

# --- repository parsing ------------------------------------------------------------------------

def test_plain_owner_slash_name():
    assert split_repo("acme/payments") == ("acme", "payments")

def test_surrounding_whitespace_and_slashes_are_tolerated():
    assert split_repo("  acme/payments/  ") == ("acme", "payments")

def test_a_git_suffix_is_stripped():
    assert split_repo("acme/payments.git") == ("acme", "payments")

def test_a_full_url_is_accepted():
    # What someone actually pastes from the browser.
    assert split_repo("https://git.corp.example.com/acme/payments") == ("acme", "payments")
    assert split_repo("http://git.corp.example.com/acme/payments.git") == ("acme", "payments")

def test_nested_groups_are_rejected_rather_than_guessed_at():
    # GitHub Enterprise allows group/subgroup/repo; taking the first two would silently point at
    # the wrong repository, so this is refused instead.
    assert split_repo("group/subgroup/repo") is None

def test_incomplete_input_is_rejected():
    for value in ["", "   ", "acme", "acme/", "/payments", "https://git.corp.example.com/",
                  "https://git.corp.example.com/acme"]:
        assert split_repo(value) is None, value

# --- webhook guidance ---------------------------------------------------------------------------

def test_webhook_instructions_name_the_events_the_handler_dispatches_on():
    # These must match the event branches in the webhook handler; the wizard and the code cannot
    # be allowed to drift apart.
    assert "Push" in WEBHOOK_EVENTS
    assert "Pull request" in WEBHOOK_EVENTS
    assert "Pull request review comment" in WEBHOOK_EVENTS
    assert "Pull request review thread" in WEBHOOK_EVENTS
    assert "Issue comments" in WEBHOOK_EVENTS

def test_webhook_instructions_never_return_the_secret_itself():
    previous, settings.public_base_url = settings.public_base_url, "https://cg.example.com"
    try:
        info = webhook_instructions()
        assert info["payload_url"] == "https://cg.example.com/github/webhook"
        assert info["content_type"] == "application/json"
        # The wizard says which variable holds the secret, never its value.
        assert info["secret_env"] == "GITHUB_WEBHOOK_SECRET"
        assert settings.github_webhook_secret not in str(info.values())
    finally:
        settings.public_base_url = previous

def test_a_missing_public_base_url_is_flagged_rather_than_shown_as_a_relative_path():
    previous, settings.public_base_url = settings.public_base_url, ""
    try:
        info = webhook_instructions()
        assert info["payload_url"] == "/github/webhook"
        assert info["note"], "the user must be told the URL is not the real address"
    finally:
        settings.public_base_url = previous
