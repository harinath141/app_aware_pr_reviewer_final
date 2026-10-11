import json

from app.credentials import (BAD_CREDENTIALS, ERROR, INSUFFICIENT_SCOPE, NO_REPO_ACCESS, OK,
                             OWNER_INVISIBLE, RATE_LIMITED, REJECTED, choose_token,
                             classify_verification, normalize_owner, serialize_credential)

def test_normalize_owner_is_case_insensitive():
    # GitHub logins are case-insensitive but case-preserving, so the key is lowercased.
    assert normalize_owner("Acme") == "acme"
    assert normalize_owner("  ACME  ") == "acme"
    assert normalize_owner(None) == ""

def test_choose_token_prefers_the_stored_credential():
    assert choose_token("owner-tok", "global-tok") == ("owner-tok", "owner")
    assert choose_token(None, "global-tok") == ("global-tok", "global")
    assert choose_token("", "global-tok") == ("global-tok", "global")
    assert choose_token(None, None) == (None, "none")

def test_only_hard_failures_are_rejected():
    assert REJECTED == {BAD_CREDENTIALS, ERROR}

def test_classify_verification_truth_table():
    # Live token, visible org, repos present.
    assert classify_verification(org_status=200, user_status=None, repo_status=200,
                                 repo_count=5, is_org=True) == OK
    # A visible org with zero repos is legitimate, not a rejection: a fine-grained PAT can be
    # scoped to repos that are added later.
    assert classify_verification(org_status=200, user_status=None, repo_status=200,
                                 repo_count=0, is_org=True) == NO_REPO_ACCESS
    # GitHub answers 404 (not 403) for things a token cannot see, so a bare 404 is only
    # meaningful once the user lookup also comes back empty.
    assert classify_verification(org_status=404, user_status=404, repo_status=None,
                                 repo_count=None, is_org=False) == OWNER_INVISIBLE
    assert classify_verification(org_status=403, user_status=None, repo_status=None,
                                 repo_count=None, is_org=False) == INSUFFICIENT_SCOPE
    # A 403 with the rate-limit budget exhausted is a different problem from a scope problem.
    assert classify_verification(org_status=403, user_status=None, repo_status=None,
                                 repo_count=None, is_org=False,
                                 rate_limited=True) == RATE_LIMITED
    assert classify_verification(org_status=404, user_status=200, repo_status=403,
                                 repo_count=None, is_org=False) == INSUFFICIENT_SCOPE

def test_serialize_credential_never_carries_token_material():
    # Column order must match credentials.CRED_COLS, which deliberately omits token_ciphertext.
    secret = "github_pat_SUPERSECRETVALUE123456"
    ciphertext = "gAAAAABm-not-a-real-ciphertext"
    row = ("acme", "Acme", "github_pat_…3456", "ci-bot", "repo", 5, True,
           None, OK, None, None, None)
    # ensure_ascii=False so the masked hint's ellipsis is not escaped as ….
    payload = json.dumps(serialize_credential(row), ensure_ascii=False)
    assert secret not in payload
    assert ciphertext not in payload
    assert "…3456" in payload          # the masked hint is the only token-ish value
    assert serialize_credential(row)["owner"] == "acme"
