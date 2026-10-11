from app.visibility import may_view, visible_repos

ADMIN = {"username": "root", "role": "admin", "github_repos": []}
# A normal user who connected GitHub and can reach two of the three onboarded repositories.
USER = {"username": "dana", "role": "user",
        "github_repos": ["acme/payments", "acme/console"]}
ONBOARDED = ["acme/payments", "acme/console", "acme/secret"]

def test_an_admin_sees_every_onboarded_repository():
    assert visible_repos(ADMIN, ONBOARDED) == ONBOARDED

def test_a_user_sees_what_their_github_token_can_reach():
    assert visible_repos(USER, ONBOARDED, owned=set()) == ["acme/payments", "acme/console"]

def test_a_repository_outside_their_github_set_is_hidden():
    assert "acme/secret" not in visible_repos(USER, ONBOARDED, owned=set())

def test_a_user_still_sees_what_they_onboarded():
    # Not in their GitHub set, but they added it - losing sight of it would be worse than the
    # permission being slightly generous.
    assert visible_repos(USER, ONBOARDED, owned={"acme/secret"}) == ONBOARDED

def test_a_user_who_has_not_connected_github_sees_only_their_own():
    # github_repos is empty until OAuth completes; the dashboard must not simply be blank.
    unconnected = {"username": "sam", "role": "user", "github_repos": []}
    assert visible_repos(unconnected, ONBOARDED, owned={"acme/console"}) == ["acme/console"]

def test_a_user_with_nothing_connected_and_nothing_owned_sees_nothing():
    stranger = {"username": "eve", "role": "user", "github_repos": []}
    assert visible_repos(stranger, ONBOARDED, owned=set()) == []

def test_visibility_preserves_the_order_of_the_catalogue():
    assert visible_repos(USER, ONBOARDED, owned=set()) == ["acme/payments", "acme/console"]

def test_may_view_allows_admins_and_their_github_set():
    assert may_view(ADMIN, "anything/at/all") is True
    assert may_view(USER, "acme/payments", owned=set()) is True

def test_may_view_refuses_what_is_out_of_reach():
    assert may_view(USER, "acme/secret", owned=set()) is False

def test_may_view_allows_what_they_onboarded():
    assert may_view(USER, "acme/secret", owned={"acme/secret"}) is True
