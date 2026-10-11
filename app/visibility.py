"""Which repositories a signed-in user may see.

One rule, in one place, used by every read route - so tightening or loosening it later is a single
edit rather than a hunt through handlers.

LDAP deliberately plays no part here. It answered "who are you" and "are you an admin"; which
repositories you can reach is a GitHub question, answered by a user token obtained through OAuth
rather than by our service account's much wider view.
"""
from app.auth import ADMIN


def owned_repos(username: str) -> set[str]:
    """Repositories this user onboarded. One query, so callers can filter a whole list cheaply."""
    if not username:
        return set()
    from app.db import connect
    try:
        with connect() as conn:
            rows = conn.execute(
                "SELECT repo_full_name FROM repository_settings WHERE onboarded_by=%s",
                (username,)).fetchall()
    except Exception:
        # A missing settings table (an older database) means nobody has onboarded anything yet.
        # Admins still see everything, and everyone still sees their GitHub set.
        return set()
    return {row[0] for row in rows}


def visible_repos(session: dict, onboarded: list[str],
                  owned: set[str] | None = None) -> list[str]:
    """The subset of `onboarded` this session may read.

    Admins see everything. Everyone else sees a repository when either:

    * it is in the repository set GitHub reported for *their* token, or
    * they onboarded it - so somebody who set a repository up keeps sight of it if their GitHub
      access is later reduced, and a user who has not connected GitHub yet still sees the
      repositories they themselves added rather than an empty dashboard.
    """
    if session.get("role") == ADMIN:
        return list(onboarded)
    allowed = set(session.get("github_repos") or [])
    # `owned` is injectable so the rule can be tested without a database; production callers leave
    # it out and it is read from repository_settings.
    owner_set = owned_repos(session.get("username") or "") if owned is None else owned
    return [repo for repo in onboarded if repo in allowed or repo in owner_set]


def may_view(session: dict, repo: str, owned: set[str] | None = None) -> bool:
    """Whether this session may read one repository."""
    if session.get("role") == ADMIN:
        return True
    if repo in set(session.get("github_repos") or []):
        return True
    owner_set = owned_repos(session.get("username") or "") if owned is None else owned
    return repo in owner_set


def onboarded_repos() -> list[str]:
    """Every catalogued repository, regardless of who may see it."""
    from app.db import connect
    with connect() as conn:
        rows = conn.execute("SELECT repo_full_name FROM repository_catalog"
                            " ORDER BY repo_full_name").fetchall()
    return [row[0] for row in rows]
