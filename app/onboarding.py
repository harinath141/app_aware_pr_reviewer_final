"""Onboarding a repository, as a sequence of checks that can only pass for real reasons.

The design commitment is that **no step can be satisfied by looking right**. Each one performs an
actual call against GitHub and reports what came back:

* `check-repo` asks whether *our* service account can see the repository.
* `preview` downloads the archive and counts what would be indexed.
* `service-account` re-reads the permissions GitHub reports for us, after the user has granted
  access, so "did it work?" has a factual answer rather than a hopeful one.

Nothing is written until `complete`.
"""
import logging

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from app import web_auth
from app.auth import ADMIN
from app.config import settings
from app.credentials import NoCredentialError, credential_client
from app.file_policy import FilePolicy
from app.repository import safe_extract_tar_gz

logger = logging.getLogger("app-aware-reviewer")

router = APIRouter(prefix="/api/onboarding", tags=["onboarding"])

# The events the app subscribes to. Kept here rather than in prose so the guidance the wizard shows
# cannot drift from what the webhook handler actually dispatches on.
WEBHOOK_EVENTS = [
    "Push",
    "Pull request",
    "Pull request review comment",
    "Pull request review thread",
    "Issue comments",
]


def split_repo(value: str) -> tuple[str, str] | None:
    """Accept `owner/name`, a full repository URL, or one with a `.git` suffix.

    Pure, so the parsing is unit-tested rather than discovered in production.
    """
    raw = (value or "").strip().rstrip("/")
    if raw.endswith(".git"):
        raw = raw[:-4]
    if "://" in raw:
        # https://ghe.corp.example.com/owner/name -> owner/name
        remainder = raw.split("://", 1)[1]
        parts = remainder.split("/", 1)
        raw = parts[1] if len(parts) == 2 else ""
    segments = [segment for segment in raw.split("/") if segment]
    if len(segments) != 2:
        return None
    owner, name = segments
    return (owner, name) if owner and name else None


def webhook_instructions() -> dict:
    """What the user has to configure on the GitHub side, and what we already know.

    The secret itself is never returned - the wizard says which value to paste, not what it is.
    """
    base = (settings.public_base_url or "").rstrip("/")
    return {
        "payload_url": f"{base}/github/webhook" if base else "/github/webhook",
        "content_type": "application/json",
        "secret_env": "GITHUB_WEBHOOK_SECRET",
        "secret_configured": bool(settings.github_webhook_secret),
        "events": WEBHOOK_EVENTS,
        "note": ("The payload URL must be reachable from GitHub. Set PUBLIC_BASE_URL so the wizard "
                 "shows the real address rather than a relative path."
                 if not base else ""),
    }


class RepoIn(BaseModel):
    repo: str

class PreviewIn(BaseModel):
    repo: str
    ref: str = ""
    include_patterns: list[str] = []
    exclude_patterns: list[str] = []

class CompleteIn(BaseModel):
    repo: str
    description: str = ""
    ref: str = ""
    include_patterns: list[str] = []
    exclude_patterns: list[str] = []


def _require_user(request: Request) -> dict:
    """Any signed-in user may onboard; only an admin may act on repositories they cannot see."""
    return web_auth.require_session(request)


def _parse(body_repo: str, session: dict) -> tuple[str, str, str]:
    parsed = split_repo(body_repo)
    if not parsed:
        raise HTTPException(400, "Enter a repository as owner/name.")
    owner, name = parsed
    full = f"{owner}/{name}"
    # Onboarding a repository you cannot reach on GitHub would grant yourself access to it, so a
    # non-admin may only onboard something already inside their own GitHub set.
    if session.get("role") != ADMIN and full not in set(session.get("github_repos") or []):
        raise HTTPException(403, "Your GitHub account does not have access to that repository.")
    return owner, name, full


def _service_client(owner: str):
    """Our side's credential for this owner - the per-owner token, else the global one."""
    try:
        return credential_client(owner)
    except NoCredentialError as exc:
        raise HTTPException(503, str(exc)) from exc


@router.post("/check-repo")
async def check_repo(body: RepoIn, request: Request):
    """Can our service account see this repository yet?"""
    session = _require_user(request)
    owner, name, full = _parse(body.repo, session)
    gh = _service_client(owner)
    status, repository = await gh.get_repo(owner, name)

    if status == 404 or repository is None:
        return {"ok": False, "repository": full, "status": status,
                "detail": ("Our service account cannot see this repository yet. Add it as a "
                           "collaborator, then check again.")}
    if status != 200:
        return {"ok": False, "repository": full, "status": status,
                "detail": f"GitHub answered {status} for this repository."}

    return {"ok": True, "repository": full, "status": 200,
            "default_branch": repository.get("default_branch") or "",
            "language": repository.get("language") or "",
            "private": bool(repository.get("private")),
            "description": repository.get("description") or ""}


@router.post("/service-account")
async def service_account(body: RepoIn, request: Request):
    """Re-read what we can actually do here, after the user has granted access.

    Reports the permissions GitHub itself returns for our credential, so the answer to "did that
    work?" is a fact rather than an assumption.
    """
    session = _require_user(request)
    owner, name, full = _parse(body.repo, session)
    gh = _service_client(owner)
    status, repository = await gh.get_repo(owner, name)
    if status != 200 or repository is None:
        return {"ok": False, "repository": full, "status": status,
                "detail": ("Still not visible to our service account. Add it as a collaborator "
                           "with write access, then check again.")}

    permissions = repository.get("permissions") or {}
    can_push = bool(permissions.get("push"))
    return {
        "ok": True,
        "repository": full,
        "status": 200,
        "permissions": {
            "read": bool(permissions.get("pull")) or can_push,
            # Posting review comments requires write; read alone can index but cannot review.
            "review": can_push,
            "admin": bool(permissions.get("admin")),
        },
        "detail": ("Ready. Our service account can read this repository and post review comments."
                   if can_push else
                   "We can read this repository but not write to it, so reviews could be generated "
                   "but not posted. Grant write access to enable comments."),
    }


@router.post("/preview")
async def preview(body: PreviewIn, request: Request):
    """Count what would be indexed, without writing anything.

    Downloads the archive in memory and applies the built-in filters followed by the draft
    patterns. Only counts come back: the built-in rules decide what is indexable and are never
    named here, which is why `builtin_skipped` is a number and not a list.
    """
    session = _require_user(request)
    owner, name, full = _parse(body.repo, session)
    gh = _service_client(owner)

    status, repository = await gh.get_repo(owner, name)
    if status != 200 or repository is None:
        raise HTTPException(409, "Our service account cannot see this repository yet.")

    ref = body.ref or repository.get("default_branch") or "HEAD"
    archive = await gh.get_archive(owner, name, ref, settings.max_archive_bytes)
    policy = FilePolicy.from_patterns(body.include_patterns, body.exclude_patterns)
    stats: dict = {}
    files = safe_extract_tar_gz(archive, policy, stats)

    return {
        "ok": True,
        "repository": full,
        "ref": ref,
        "counts": {
            "total_files": stats.get("total", 0),
            "to_index": stats.get("kept", 0),
            # Never broken down: naming our filters would be publishing them.
            "builtin_skipped": stats.get("builtin_skipped", 0) + stats.get("oversized", 0)
                               + stats.get("binary", 0),
            "your_patterns_skipped": stats.get("policy_skipped", 0),
        },
        "sample_paths": sorted(files)[:15],
    }


@router.get("/webhook")
def webhook(request: Request):
    _require_user(request)
    return webhook_instructions()


@router.post("/complete")
async def complete(body: CompleteIn, request: Request):
    """Persist the settings and index the repository once."""
    from app.db import connect
    from app.main import index_commit

    session = _require_user(request)
    owner, name, full = _parse(body.repo, session)
    gh = _service_client(owner)

    status, repository = await gh.get_repo(owner, name)
    if status != 200 or repository is None:
        raise HTTPException(409, "Our service account cannot see this repository.")

    ref = body.ref or repository.get("default_branch") or "HEAD"
    commit = await gh.get_json(f"/repos/{owner}/{name}/commits/{ref}")
    sha = commit.get("sha")
    if not sha:
        raise HTTPException(502, "GitHub did not return a commit for that branch.")

    policy = FilePolicy.from_patterns(body.include_patterns, body.exclude_patterns)
    with connect() as conn:
        conn.execute("""INSERT INTO repository_settings
            (repo_full_name, description, include_patterns, exclude_patterns, onboarded_by)
            VALUES (%s,%s,%s,%s,%s)
            ON CONFLICT (repo_full_name) DO UPDATE SET description=EXCLUDED.description,
              include_patterns=EXCLUDED.include_patterns, exclude_patterns=EXCLUDED.exclude_patterns
            """,
            (full, body.description, list(policy.include), list(policy.exclude),
             session["username"]))
        conn.commit()

    indexed = await index_commit(gh, owner, name, sha)
    logger.info("onboarded repo=%s by=%s sha=%s", full, session["username"], sha[:8])
    return {"ok": True, "repository": full, "commit_sha": sha, "indexing": indexed}
