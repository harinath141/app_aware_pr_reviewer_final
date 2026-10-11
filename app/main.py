import hashlib
import hmac
import json
import logging
import secrets
import time
from datetime import datetime, timezone
from urllib.parse import urlencode
import httpx
from fastapi import FastAPI, Header, HTTPException, Request, Response
from fastapi.responses import JSONResponse, FileResponse, RedirectResponse
from pydantic import BaseModel
from fastapi.staticfiles import StaticFiles
from pathlib import Path
from openai import AsyncOpenAI
from app import auth, onboarding, visibility, web_auth
from app.config import settings
from app.crypto import CryptoKeyMissing
from app.db import init_db, connect
from app.github_client import GitHubClient
from app.indexer import Indexer
from app.context import retrieve_context
from app.reviewer import Reviewer, coerce_line
from app.formatting import (render_comment, render_finding_comment, finding_marker,
                            annotate_status, has_status)
from app.diff_anchor import build_patch_index, resolve_anchor
from app.commands import parse_command
from app.crypto import mask_token
from app.credentials import (REJECTED, NoCredentialError, audit, credential_client,
                             delete_credential, get_credential, key_status, list_credentials,
                             normalize_owner, record_verification, save_credential, stored_token,
                             verify_owner_token)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("app-aware-reviewer")
app = FastAPI(title="App-Aware PR Reviewer", version="1.2.0")
STATIC_DIR = Path(__file__).parent / "static"
ASSETS_DIR = STATIC_DIR / "assets"
# The React dashboard is built into STATIC_DIR by Vite, which emits hashed bundles under assets/.
# Mount only when a build is present: StaticFiles raises at import time when the directory is
# missing, and check_dir=False merely defers that failure to the first request, so a checkout that
# has not run `npm run build` yet would fail to start rather than serve a 404.
if ASSETS_DIR.is_dir():
    app.mount("/assets", StaticFiles(directory=ASSETS_DIR), name="assets")
# Each finding is posted as its own comment, so a huge review would mean hundreds of API calls
# and a good chance of hitting secondary rate limits mid-loop. The rest still reach the dashboard.
MAX_INDIVIDUAL_COMMENTS = 20

# Installed before any route is declared, so nothing can be reached without passing it. Router
# routes are covered by it too, which is why /api/onboarding needs no guard of its own.
web_auth.install(app)
app.include_router(onboarding.router)

@app.on_event("startup")
def startup():
    # Configuration first: if sign-in is required but unconfigured, fail before touching the
    # database rather than coming up in a state nobody can log into.
    web_auth.check_configuration()
    init_db()
    removed = auth.purge_expired_sessions()
    if removed:
        logger.info("purged %s expired session(s)", removed)

def verify_signature(secret: str, body: bytes, signature: str | None) -> bool:
    if not signature or not signature.startswith("sha256="):
        return False
    expected = "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature)

def snapshot_exists(repo: str, sha: str) -> bool:
    with connect() as conn:
        return conn.execute("SELECT 1 FROM repository_snapshots WHERE repo_full_name=%s AND commit_sha=%s",
                            (repo, sha)).fetchone() is not None

async def index_commit(gh, owner, repo_name, sha):
    repo = f"{owner}/{repo_name}"
    if snapshot_exists(repo, sha):
        return {"already_indexed": True, "commit_sha": sha}
    archive = await gh.get_archive(owner, repo_name, sha, settings.max_archive_bytes)
    return await Indexer().index_archive(repo, sha, archive)

async def query_embedding(query: str) -> list[float]:
    client = AsyncOpenAI(api_key=settings.llm_api_key,
        base_url=settings.embedding_base_url or settings.llm_base_url)
    r = await client.embeddings.create(model=settings.embedding_model, input=query[:12000])
    v = r.data[0].embedding
    if len(v) != settings.embedding_dimensions:
        raise ValueError("Query embedding dimension mismatch")
    return v

def is_our_comment(body: str | None) -> bool:
    """True for comments this app posted.

    Do NOT test against the token's own login: the token belongs to the repo owner, so that
    would silently discard the owner's genuine triage replies. Every comment we post carries
    either a finding marker or the report footer, which is what we match on instead.
    """
    text = body or ""
    return "<!-- finding-id:" in text or "App-Aware PR Reviewer" in text

def thread_status_transition(current: str, action: str) -> str | None:
    """Status a review-thread event should apply, or None to leave the finding alone.

    GitHub fires `pull_request_review_thread` resolved/unresolved not only for the Resolve
    button but also as a side effect of replying to a thread — roughly two seconds after every
    reply. Applying it unconditionally would silently overwrite the reviewer's explicit
    `/invalid`, so the thread event may only move a finding between open and resolved.
    """
    if action == "resolved":
        return "resolved" if current == "open" else None
    if action == "unresolved":
        return "open" if current == "resolved" else None
    return None

def thread_state_for_status(status: str) -> bool | None:
    """Whether the review thread should be resolved for a finding status (None = leave alone).

    A settled finding (fixed, or dismissed as a false positive) should leave its conversation
    resolved, or GitHub's "Require conversation resolution before merging" branch protection
    will block the merge. Re-opening a finding puts the conversation back in the reviewer's way.
    """
    if status in ("resolved", "invalid"):
        return True
    if status == "open":
        return False
    return None

def finding_row(row):
    return None if not row else {"id": row[0], "repo": row[1], "pr": row[2], "status": row[3],
                                 "comment_kind": row[4], "comment_id": row[5]}

FINDING_COLS = "id, repo_full_name, pr_number, status, comment_kind, comment_id"

async def thread_root_id(gh, owner, repo_name, comment: dict) -> int | None:
    """Find the finding comment a reply belongs to.

    in_reply_to_id may point at a human's reply rather than the thread root, so walk up the
    chain until we hit a comment id we recognise (or run out of hops).
    """
    parent = comment.get("in_reply_to_id")
    seen = set()
    for _ in range(6):
        if not parent or parent in seen:
            return None
        seen.add(parent)
        with connect() as conn:
            if conn.execute("SELECT 1 FROM review_findings WHERE comment_kind='review_comment'"
                            " AND comment_id=%s", (parent,)).fetchone():
                return parent
        try:
            parent = (await gh.get_review_comment(owner, repo_name, parent)).get("in_reply_to_id")
        except Exception:
            logger.exception("Could not walk reply chain from comment %s", parent)
            return None
    return None

async def apply_status(gh, owner, repo_name, finding: dict, status: str, actor: str, via: str):
    """Set a finding's status and annotate its posted comment. Safe to call repeatedly.

    `via` is the display-ready source of the change, e.g. "`/resolved`" for a reply command or
    "the Resolve conversation button" for GitHub's native thread resolution.
    """
    kind, comment_id = finding.get("comment_kind"), finding.get("comment_id")
    if kind and comment_id:
        read = gh.get_review_comment if kind == "review_comment" else gh.get_issue_comment
        try:
            current = (await read(owner, repo_name, comment_id)).get("body") or ""
        except Exception:
            logger.exception("Could not read comment %s for finding %s", comment_id, finding["id"])
            current = None
        if current is not None:
            if finding_marker(finding["id"]) not in current:
                # Someone replaced the comment; never edit a stranger's text.
                logger.warning("Comment %s no longer carries finding %s; not editing",
                               comment_id, finding["id"])
            elif has_status(current, status):
                logger.info("Finding %s already %s; skipping edit", finding["id"], status)
            else:
                # Rebase on the freshly fetched body so human edits survive.
                body = annotate_status(current, status, actor, via,
                                       datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"))
                edit = gh.edit_review_comment if kind == "review_comment" else gh.edit_issue_comment
                await edit(owner, repo_name, comment_id, body)
                with connect() as conn:
                    conn.execute("UPDATE review_findings SET comment_body=%s WHERE id=%s",
                                 (body, finding["id"]))
    with connect() as conn:
        conn.execute("""UPDATE review_findings SET status=%s, status_actor=%s,
            status_updated_at=now(), resolved_at=CASE WHEN %s='resolved' THEN now() ELSE NULL END
            WHERE id=%s""", (status, actor or None, status, finding["id"]))

    # Keep GitHub's own thread state in step with the status. Without this a dismissed finding
    # leaves an open conversation behind, which blocks merging on protected branches.
    want = thread_state_for_status(status)
    if want is not None and kind == "review_comment" and comment_id:
        try:
            thread_id = await gh.find_review_thread(owner, repo_name, finding["pr"], comment_id)
            if thread_id:
                await gh.set_review_thread_resolved(thread_id, want)
                logger.info("finding %s thread -> %s", finding["id"],
                            "resolved" if want else "unresolved")
        except Exception:
            # Best effort: the status is already recorded and a leftover unresolved thread can be
            # cleared by hand, so this must not fail the whole webhook.
            logger.exception("Could not sync thread state for finding %s", finding["id"])

async def handle_review_comment_command(gh, owner, repo_name, payload: dict):
    comment = payload.get("comment") or {}
    actor = (comment.get("user") or {}).get("login") or ""
    if is_our_comment(comment.get("body")):
        return {"status": "ignored", "reason": "our own comment"}
    parsed = parse_command(comment.get("body") or "")
    if not parsed:
        return {"status": "ignored", "reason": "no command"}
    status, explicit_id = parsed
    root = await thread_root_id(gh, owner, repo_name, comment)
    if root is None:
        return {"status": "ignored", "reason": "not a reply to a finding comment"}
    with connect() as conn:
        finding = finding_row(conn.execute(
            f"SELECT {FINDING_COLS} FROM review_findings"
            " WHERE comment_kind='review_comment' AND comment_id=%s", (root,)).fetchone())
    if not finding:
        return {"status": "ignored", "reason": "no finding for this thread"}
    if explicit_id is not None and explicit_id != finding["id"]:
        return {"status": "ignored", "reason": "finding id does not match this thread"}
    await apply_status(gh, owner, repo_name, finding, status, actor, f"`/{status}`")
    logger.info("finding %s -> %s by %s", finding["id"], status, actor)
    return {"status": "finding_updated", "finding": finding["id"], "state": status}

async def handle_issue_comment_command(gh, owner, repo_name, payload: dict):
    comment = payload.get("comment") or {}
    actor = (comment.get("user") or {}).get("login") or ""
    if is_our_comment(comment.get("body")):
        # Our own summary and standalone finding comments land here; reacting to them would loop.
        return {"status": "ignored", "reason": "our own comment"}
    parsed = parse_command(comment.get("body") or "")
    if not parsed:
        return {"status": "ignored", "reason": "no command"}
    status, finding_id = parsed
    if finding_id is None:
        # A timeline comment cannot be threaded, so the id has to travel in the command.
        return {"status": "ignored", "reason": "timeline commands must include the finding id"}
    number = (payload.get("issue") or {}).get("number")
    with connect() as conn:
        finding = finding_row(conn.execute(
            f"SELECT {FINDING_COLS} FROM review_findings"
            " WHERE id=%s AND repo_full_name=%s AND pr_number=%s",
            (finding_id, f"{owner}/{repo_name}", number)).fetchone())
    if not finding:
        return {"status": "ignored", "reason": "no such finding on this pull request"}
    await apply_status(gh, owner, repo_name, finding, status, actor, f"`/{status}`")
    logger.info("finding %s -> %s by %s", finding["id"], status, actor)
    return {"status": "finding_updated", "finding": finding["id"], "state": status}

async def handle_review_thread(gh, owner, repo_name, payload: dict):
    """GitHub's native "Resolve conversation" / "Unresolve conversation" button.

    Complement to the reply commands: reviewers reach for the button by default. The thread
    payload carries its comments, so any of them identifies which finding it belongs to.
    """
    action = payload.get("action")
    if action not in {"resolved", "unresolved"}:
        return {"status": "ignored", "reason": "action not reviewed"}
    actor = (payload.get("sender") or {}).get("login") or ""
    comments = ((payload.get("thread") or {}).get("comments") or [])
    finding = None
    with connect() as conn:
        for c in comments:
            cid = c.get("id")
            if cid is None:
                continue
            finding = finding_row(conn.execute(
                f"SELECT {FINDING_COLS} FROM review_findings"
                " WHERE comment_kind='review_comment' AND comment_id=%s", (cid,)).fetchone())
            if finding:
                break
    if not finding:
        return {"status": "ignored", "reason": "no finding for this thread"}
    status = thread_status_transition(finding["status"], action)
    if status is None:
        return {"status": "ignored",
                "reason": f"thread '{action}' must not override explicit '{finding['status']}'"}
    await apply_status(gh, owner, repo_name, finding, status, actor,
                       "the Resolve conversation button" if status == "resolved"
                       else "un-resolving the conversation")
    logger.info("finding %s -> %s by %s (thread)", finding["id"], status, actor)
    return {"status": "finding_updated", "finding": finding["id"], "state": status}

# --- authentication ---------------------------------------------------------------------------

class LoginIn(BaseModel):
    username: str
    password: str

@app.post("/auth/login")
def login(body: LoginIn, request: Request):
    """Sign in against the directory.

    Public by necessity - there is no session yet - which is why the CSRF token is still required:
    without it a third-party page could sign a victim into an account of the attacker's choosing.
    """
    if settings.auth_required and not web_auth.csrf_ok(request):
        raise HTTPException(403, "Missing or invalid CSRF token.")

    user, reason = auth.authenticate(body.username, body.password)
    if user is None:
        logger.warning("login failed user=%s reason=%s", body.username, reason)
        return JSONResponse({"detail": reason}, status_code=401)

    session_id = auth.create_session(user)
    logger.info("login ok user=%s role=%s dn=%s", user.username, user.role, user.dn)
    response = JSONResponse({"username": user.username, "role": user.role,
                             "display_name": user.display_name, "github_login": None,
                             "github_connected": False, "auth_required": True})
    web_auth.set_session_cookie(response, session_id)
    return web_auth.ensure_csrf_cookie(request, response)

@app.post("/api/logout")
def logout(request: Request):
    """Server-side revocation: the row is deleted, so the cookie is worthless afterwards."""
    session = web_auth.session_from(request)
    if session:
        logger.info("logout user=%s", session["username"])
        auth.delete_session(session["id"])
    response = JSONResponse({"signed_out": True})
    web_auth.clear_session_cookie(response)
    return response

@app.get("/api/me")
def me(request: Request):
    """Who the browser is signed in as, and whether GitHub is connected."""
    session = web_auth.session_from(request)
    if not session:
        if not settings.auth_required:
            # Sign-in is switched off for this deployment; the UI still needs an identity to render.
            return {"username": "anonymous", "display_name": "Sign-in disabled", "role": auth.ADMIN,
                    "github_login": None, "github_connected": False, "auth_required": False}
        raise HTTPException(401, "Sign in to continue.")
    return {
        "username": session["username"],
        "display_name": session["display_name"] or session["username"],
        "role": session["role"],
        "github_login": session["github_login"],
        "github_connected": bool(session["github_login"]),
        "auth_required": settings.auth_required,
        "oauth_available": settings.oauth_configured,
    }

# --- GitHub OAuth (per-user repository visibility) ---------------------------------------------
# The user authorises against their own GitHub, and we read their token's repository list. Our
# service account cannot answer "what can this person reach" - that requires acting as them, which
# is the entire reason this flow exists.

OAUTH_STATE_COOKIE = "cg_oauth_state"

def _callback_url(request: Request) -> str:
    """Must be byte-identical between the authorize redirect and the token exchange."""
    if settings.oauth_callback_url:
        return settings.oauth_callback_url
    return str(request.base_url).rstrip("/") + "/oauth/github/callback"

@app.get("/oauth/github/start")
def oauth_start(request: Request):
    """Redirect to GitHub's consent screen. Needs a session: the result is stored on it."""
    web_auth.require_session(request)
    if not settings.oauth_configured:
        raise HTTPException(503, "GitHub sign-in is not configured on this server.")

    authorize_url, _ = settings.oauth_endpoints
    state = secrets.token_urlsafe(24)
    query = urlencode({
        "client_id": settings.oauth_client_id,
        "redirect_uri": _callback_url(request),
        # `repo` is what makes private repositories visible; `read:org` lets org membership count.
        "scope": "repo read:org",
        "state": state,
    })
    response = RedirectResponse(f"{authorize_url}?{query}")
    # HttpOnly so no script can read it, and short-lived: it only needs to survive the round trip.
    response.set_cookie(OAUTH_STATE_COOKIE, state, httponly=True, samesite="lax",
                        secure=settings.session_cookie_secure, max_age=600, path="/")
    return response

async def _exchange_code(code: str, redirect_uri: str) -> str | None:
    _, token_url = settings.oauth_endpoints
    async with httpx.AsyncClient(timeout=30) as client:
        response = await client.post(
            token_url,
            headers={"Accept": "application/json"},
            data={"client_id": settings.oauth_client_id,
                  "client_secret": settings.oauth_client_secret,
                  "code": code, "redirect_uri": redirect_uri},
        )
        response.raise_for_status()
        return (response.json() or {}).get("access_token")

@app.get("/oauth/github/callback")
async def oauth_callback(request: Request, code: str = "", state: str = ""):
    session = web_auth.session_from(request)
    if not session:
        return RedirectResponse("/login")

    # The state is compared against an HttpOnly cookie set when the flow began. Without this a
    # third party could hand the browser a callback URL carrying *their* code, silently attaching
    # their GitHub identity - and their repository access - to this session.
    expected = request.cookies.get(OAUTH_STATE_COOKIE) or ""
    if not code or not expected or not hmac.compare_digest(expected, state):
        logger.warning("OAuth callback rejected: bad or missing state for user=%s", session["username"])
        return RedirectResponse("/?github=state_error")

    try:
        token = await _exchange_code(code, _callback_url(request))
    except Exception:
        logger.exception("OAuth token exchange failed for user=%s", session["username"])
        return RedirectResponse("/?github=token_error")
    if not token:
        return RedirectResponse("/?github=token_error")

    client = GitHubClient(token)
    try:
        account = await client.get_json("/user")
        repos = await client.list_user_repos(token)
    except Exception:
        logger.exception("OAuth: could not read repositories for user=%s", session["username"])
        return RedirectResponse("/?github=api_error")

    names = sorted({r.get("full_name") for r in repos if r.get("full_name")})
    login = (account or {}).get("login") or ""
    try:
        auth.store_github_identity(session["id"], login, names, token)
    except CryptoKeyMissing:
        # Refuse rather than fall back to storing a user's token in the clear.
        logger.error("GITHUB_CREDENTIAL_KEY is unset; refusing to store an OAuth token")
        return RedirectResponse("/?github=no_key")

    logger.info("github connected user=%s login=%s repos=%s", session["username"], login, len(names))
    response = RedirectResponse("/?github=connected")
    response.delete_cookie(OAUTH_STATE_COOKIE, path="/")
    return response

@app.post("/api/github/disconnect")
def github_disconnect(request: Request):
    session = web_auth.require_session(request)
    auth.forget_github_identity(session["id"])
    return {"connected": False}

def visibility_scope(request: Request) -> list[str] | None:
    """Repositories this request may read, or None meaning "no restriction".

    None only when sign-in is switched off for the whole deployment, which is the local-trial
    escape hatch. Otherwise it is an explicit list - and an empty list is a real answer meaning
    "show nothing", not "show everything".
    """
    if not settings.auth_required:
        return None
    session = web_auth.require_session(request)
    return visibility.visible_repos(session, visibility.onboarded_repos())

def require_repo_access(request: Request, owner: str, repo: str) -> None:
    """403 unless this session may read the repository."""
    if not settings.auth_required:
        return
    session = web_auth.require_session(request)
    if not visibility.may_view(session, f"{owner}/{repo}"):
        raise HTTPException(403, "You do not have access to that repository.")

@app.get("/", include_in_schema=False)
def dashboard():
    # FileResponse raises RuntimeError (a 500) when the file is absent, so an unbuilt checkout
    # would surface as a stack trace instead of an explanation.
    index = STATIC_DIR / "index.html"
    if not index.is_file():
        raise HTTPException(503, "Dashboard not built. Run `npm run build` in frontend/.")
    return FileResponse(index)

@app.get("/api/dashboard")
def dashboard_data(request: Request, language: str | None = None, q: str | None = None):
    # Applied in SQL rather than after the fact, so a repository the caller may not see is never
    # loaded. An empty scope means "show nothing", which `= ANY('{}')` does correctly.
    allowed = visibility_scope(request)
    with connect() as conn:
        where, params = [], []
        if allowed is not None:
            where.append("repo_full_name = ANY(%s)"); params.append(allowed)
        if language and language.lower() != "all":
            where.append("primary_language=%s"); params.append(language)
        if q:
            where.append("(repo_full_name ILIKE %s OR description ILIKE %s)")
            params.extend([f"%{q}%", f"%{q}%"])
        clause = (" WHERE " + " AND ".join(where)) if where else ""
        repos = conn.execute("SELECT repo_full_name,primary_language,description,latest_sha,indexed_at,file_count,chunk_count,symbol_count,edge_count FROM repository_catalog" + clause + " ORDER BY indexed_at DESC", params).fetchall()
        totals = conn.execute("""SELECT
            (SELECT count(*) FROM repository_catalog),
            (SELECT count(*) FROM review_runs),
            (SELECT count(*) FROM review_findings),
            (SELECT count(*) FROM review_findings WHERE category ILIKE '%security%' OR category ILIKE '%vuln%'),
            (SELECT count(*) FROM review_findings WHERE status='resolved'),
            (SELECT count(*) FROM review_findings WHERE status='open'),
            (SELECT count(*) FROM repository_snapshots),
            (SELECT count(*) FROM review_findings WHERE status='open' AND severity IN ('critical','high')),
            (SELECT count(*) FROM review_findings WHERE status='invalid')""").fetchone()
        languages = conn.execute("SELECT primary_language,count(*) FROM repository_catalog GROUP BY primary_language ORDER BY count(*) DESC,primary_language").fetchall()
        reviews = conn.execute("SELECT id,repo_full_name,pr_number,pr_title,pr_url,risk,recommendation,finding_count,reviewed_at FROM review_runs ORDER BY reviewed_at DESC LIMIT 12").fetchall()
        findings = conn.execute("SELECT id,repo_full_name,pr_number,title,severity,category,file_path,evidence,failure_scenario,impact,recommendation,status,created_at,anchor_line,line_no,comment_url,status_actor,status_updated_at FROM review_findings ORDER BY CASE severity WHEN 'critical' THEN 0 WHEN 'high' THEN 1 WHEN 'medium' THEN 2 WHEN 'low' THEN 3 ELSE 4 END,created_at DESC LIMIT 20").fetchall()
    def iso(v): return v.isoformat() if v else None
    return {
        "stats": {"projects": totals[0], "reviews": totals[1], "issues_found": totals[2], "security_issues": totals[3], "issues_fixed": totals[4], "issues_open": totals[5], "snapshots": totals[6], "high_risk_open": totals[7], "issues_invalid": totals[8]},
        "languages": [{"name": r[0], "count": r[1]} for r in languages],
        "repositories": [{"name": r[0], "language": r[1], "description": r[2], "latest_sha": r[3], "indexed_at": iso(r[4]), "files": r[5], "chunks": r[6], "symbols": r[7], "edges": r[8]} for r in repos],
        "reviews": [{"id": r[0], "repo": r[1], "pr_number": r[2], "title": r[3], "url": r[4], "risk": r[5], "recommendation": r[6], "findings": r[7], "reviewed_at": iso(r[8])} for r in reviews],
        "findings": [{"id": r[0], "repo": r[1], "pr_number": r[2], "title": r[3], "severity": r[4], "category": r[5], "file": r[6], "evidence": r[7], "scenario": r[8], "impact": r[9], "recommendation": r[10], "status": r[11], "created_at": iso(r[12]), "anchor_line": r[13], "line": r[14], "comment_url": r[15], "status_actor": r[16], "status_updated_at": iso(r[17])} for r in findings]
    }

@app.get("/api/repositories/{owner}/{repo}")
def repository_detail(owner: str, repo: str, request: Request):
    require_repo_access(request, owner, repo)
    with connect() as conn:
        r = conn.execute("SELECT repo_full_name,primary_language,description,latest_sha,indexed_at,file_count,chunk_count,symbol_count,edge_count FROM repository_catalog WHERE repo_full_name=%s", (f"{owner}/{repo}",)).fetchone()
        if not r: raise HTTPException(404, "Repository not indexed yet")
        snaps = conn.execute("SELECT commit_sha,indexed_at,file_count,chunk_count FROM repository_snapshots WHERE repo_full_name=%s ORDER BY indexed_at DESC LIMIT 10", (f"{owner}/{repo}",)).fetchall()
        recent = conn.execute("SELECT id,pr_number,pr_title,risk,finding_count,reviewed_at FROM review_runs WHERE repo_full_name=%s ORDER BY reviewed_at DESC LIMIT 10", (f"{owner}/{repo}",)).fetchall()
    return {"name":r[0],"language":r[1],"description":r[2],"latest_sha":r[3],"indexed_at":r[4].isoformat(),"files":r[5],"chunks":r[6],"symbols":r[7],"edges":r[8],"snapshots":[{"sha":x[0],"indexed_at":x[1].isoformat(),"files":x[2],"chunks":x[3]} for x in snaps],"reviews":[{"id":x[0],"pr_number":x[1],"title":x[2],"risk":x[3],"findings":x[4],"reviewed_at":x[5].isoformat()} for x in recent]}

# --- knowledge graph -------------------------------------------------------------------------
# Read-only views over code_symbols (nodes) and code_edges. These describe what the reviewer
# already uses as `symbol_graph` context; nothing here mutates anything.

# Total degree per symbol (in + out), deduplicated so a mutual edge is not counted twice.
_GRAPH_DEGREE_CTE = """
WITH deg AS (
    SELECT repo_full_name, commit_sha, symbol_id, count(*) AS degree FROM (
        SELECT repo_full_name, commit_sha, source_id AS symbol_id FROM code_edges
        UNION ALL
        SELECT repo_full_name, commit_sha, target_id FROM code_edges
    ) endpoints GROUP BY repo_full_name, commit_sha, symbol_id
)
"""

@app.get("/api/graph")
def graph_overview():
    with connect() as conn:
        coverage = conn.execute("""
            WITH endpoints AS (
                SELECT repo_full_name, commit_sha, source_id AS symbol_id FROM code_edges
                UNION
                SELECT repo_full_name, commit_sha, target_id FROM code_edges
            ), snap AS (
                SELECT repo_full_name, latest_sha FROM repository_catalog WHERE latest_sha IS NOT NULL
            )
            SELECT snap.repo_full_name, count(s.symbol_id), count(endpoints.symbol_id),
                   (SELECT count(*) FROM code_edges e
                     WHERE e.repo_full_name = snap.repo_full_name AND e.commit_sha = snap.latest_sha)
            FROM snap
            LEFT JOIN code_symbols s
              ON s.repo_full_name = snap.repo_full_name AND s.commit_sha = snap.latest_sha
            LEFT JOIN endpoints
              ON endpoints.repo_full_name = s.repo_full_name
             AND endpoints.commit_sha = s.commit_sha AND endpoints.symbol_id = s.symbol_id
            GROUP BY snap.repo_full_name, snap.latest_sha
            ORDER BY count(s.symbol_id) DESC, snap.repo_full_name""").fetchall()
        hubs = conn.execute(_GRAPH_DEGREE_CTE + """
            SELECT s.name, s.kind, s.file_path, s.repo_full_name, d.degree
            FROM deg d
            JOIN code_symbols s ON s.repo_full_name = d.repo_full_name
             AND s.commit_sha = d.commit_sha AND s.symbol_id = d.symbol_id
            JOIN repository_catalog c ON c.repo_full_name = s.repo_full_name
             AND c.latest_sha = s.commit_sha
            ORDER BY d.degree DESC, s.name LIMIT 12""").fetchall()
        edge_types = conn.execute(
            "SELECT edge_type, count(*) FROM code_edges GROUP BY edge_type ORDER BY count(*) DESC").fetchall()

    rows = [{"repo": r[0], "symbols": r[1], "connected": r[2], "isolated": r[1] - r[2], "edges": r[3]}
            for r in coverage]
    return {
        "coverage": rows,
        "totals": {
            "symbols": sum(r["symbols"] for r in rows),
            "connected": sum(r["connected"] for r in rows),
            "edges": sum(r["edges"] for r in rows),
        },
        "hubs": [{"name": h[0], "kind": h[1], "file": h[2], "repo": h[3], "degree": h[4]} for h in hubs],
        "edge_types": [{"type": t[0], "count": t[1]} for t in edge_types],
    }

@app.get("/api/repositories/{owner}/{repo}/graph")
def repository_graph(owner: str, repo: str, request: Request, limit: int = 150):
    """The connected core of one repository's graph.

    Only symbols that participate in at least one edge are returned, ranked by degree. A repo can
    hold hundreds of symbols that resolve to no relationship at all, and drawing those would bury
    the part of the graph that carries signal.
    """
    require_repo_access(request, owner, repo)
    full = f"{owner}/{repo}"
    limit = max(1, min(limit, 400))
    with connect() as conn:
        catalog = conn.execute("SELECT latest_sha FROM repository_catalog WHERE repo_full_name=%s",
                               (full,)).fetchone()
        if not catalog or not catalog[0]:
            raise HTTPException(404, "Repository not indexed yet")
        sha = catalog[0]
        total_symbols = conn.execute(
            "SELECT count(*) FROM code_symbols WHERE repo_full_name=%s AND commit_sha=%s",
            (full, sha)).fetchone()[0]
        total_edges = conn.execute(
            "SELECT count(*) FROM code_edges WHERE repo_full_name=%s AND commit_sha=%s",
            (full, sha)).fetchone()[0]
        connected = conn.execute(_GRAPH_DEGREE_CTE +
            "SELECT count(*) FROM deg WHERE repo_full_name=%s AND commit_sha=%s",
            (full, sha)).fetchone()[0]
        nodes = conn.execute(_GRAPH_DEGREE_CTE + """
            SELECT s.symbol_id, s.name, s.kind, s.file_path, d.degree
            FROM deg d
            JOIN code_symbols s ON s.repo_full_name = d.repo_full_name
             AND s.commit_sha = d.commit_sha AND s.symbol_id = d.symbol_id
            WHERE d.repo_full_name = %s AND d.commit_sha = %s
            ORDER BY d.degree DESC, s.name LIMIT %s""", (full, sha, limit)).fetchall()
        ids = [n[0] for n in nodes]
        links = conn.execute("""
            SELECT source_id, target_id FROM code_edges
            WHERE repo_full_name = %s AND commit_sha = %s
              AND source_id = ANY(%s) AND target_id = ANY(%s)""",
            (full, sha, ids, ids)).fetchall() if ids else []

    return {
        "repository": full,
        "commit_sha": sha,
        "nodes": [{"id": n[0], "name": n[1], "kind": n[2], "file": n[3], "degree": n[4]} for n in nodes],
        "links": [{"source": l[0], "target": l[1]} for l in links],
        "stats": {"total_symbols": total_symbols, "total_edges": total_edges,
                  "connected_symbols": connected, "shown_nodes": len(nodes), "shown_edges": len(links)},
        "truncated": connected > len(nodes) or total_edges > len(links),
    }

# Sort keys are a whitelist, never interpolated from the request: the value lands in an ORDER BY,
# which cannot be parameterised.
FINDING_SORTS = {
    "severity": ("CASE f.severity WHEN 'critical' THEN 0 WHEN 'high' THEN 1"
                 " WHEN 'medium' THEN 2 WHEN 'low' THEN 3 ELSE 4 END, f.created_at DESC"),
    "recent": "f.created_at DESC",
    "oldest": "f.created_at ASC",
    "file": "f.file_path ASC, f.created_at DESC",
    "category": "f.category ASC, f.created_at DESC",
    "project": "f.repo_full_name ASC, f.created_at DESC",
}

@app.get("/api/findings")
def findings_filtered(request: Request, repo: str | None = None, language: str | None = None,
                      status: str | None = None, severity: str | None = None,
                      commit: str | None = None, sort: str = "severity", limit: int = 100):
    """Filterable findings, queried from the whole table.

    `/api/dashboard` caps findings at the 20 most severe rows so its payload stays small, which
    makes it useless as a source for filtering - most matches would never be in the slice. This
    reads the table directly, and joins the two fields the dashboard payload does not carry:
    the repository's primary language, and the commit the review ran against.

    `language` and `commit` are derived through those joins, so a finding whose repository is not
    catalogued, or whose review row is missing, simply has NULL there and matches no filter for it.
    """
    limit = max(1, min(limit, 500))
    where, params = [], []
    allowed = visibility_scope(request)
    if allowed is not None:
        where.append("f.repo_full_name = ANY(%s)"); params.append(allowed)
    # "all" is what the dashboard's selects use for "no filter", so treat it as absent.
    if repo and repo != "all":
        where.append("f.repo_full_name = %s"); params.append(repo)
    if language and language != "all":
        where.append("c.primary_language = %s"); params.append(language)
    if status and status != "all":
        where.append("f.status = %s"); params.append(status)
    if severity and severity != "all":
        where.append("f.severity = %s"); params.append(severity)
    if commit and commit != "all":
        where.append("r.commit_sha = %s"); params.append(commit)
    clause = (" WHERE " + " AND ".join(where)) if where else ""

    joined = """ FROM review_findings f
        LEFT JOIN repository_catalog c ON c.repo_full_name = f.repo_full_name
        LEFT JOIN review_runs r ON r.id = f.review_id """

    with connect() as conn:
        total = conn.execute("SELECT count(*) " + joined + clause, params).fetchone()[0]
        rows = conn.execute("""SELECT f.id, f.repo_full_name, f.pr_number, f.title, f.severity,
                f.category, f.file_path, f.evidence, f.failure_scenario, f.impact, f.recommendation,
                f.status, f.created_at, f.anchor_line, f.line_no, f.comment_url, f.status_actor,
                f.status_updated_at, c.primary_language, r.commit_sha """ + joined + clause +
            " ORDER BY " + FINDING_SORTS.get(sort, FINDING_SORTS["severity"]) + " LIMIT %s",
            params + [limit]).fetchall()
        # Filter options are drawn from all findings, not just the current result, so choosing one
        # filter never removes the choices for the others.
        projects = conn.execute(
            "SELECT DISTINCT repo_full_name FROM review_findings ORDER BY 1").fetchall()
        languages = conn.execute("""SELECT DISTINCT c.primary_language FROM repository_catalog c
            JOIN review_findings f ON f.repo_full_name = c.repo_full_name
            WHERE c.primary_language IS NOT NULL ORDER BY 1""").fetchall()
        commits = conn.execute("""SELECT r.commit_sha, r.repo_full_name, max(r.reviewed_at)
            FROM review_runs r JOIN review_findings f ON f.review_id = r.id
            WHERE r.commit_sha <> '' GROUP BY r.commit_sha, r.repo_full_name
            ORDER BY max(r.reviewed_at) DESC LIMIT 50""").fetchall()
        statuses = conn.execute(
            "SELECT DISTINCT status FROM review_findings ORDER BY 1").fetchall()
        severities = conn.execute(
            "SELECT DISTINCT severity FROM review_findings ORDER BY 1").fetchall()

    def iso(v):
        return v.isoformat() if v else None

    def finding(r):
        return {"id": r[0], "repo": r[1], "pr_number": r[2], "title": r[3], "severity": r[4],
                "category": r[5], "file": r[6], "evidence": r[7], "scenario": r[8], "impact": r[9],
                "recommendation": r[10], "status": r[11], "created_at": iso(r[12]),
                "anchor_line": r[13], "line": r[14], "comment_url": r[15], "status_actor": r[16],
                "status_updated_at": iso(r[17]), "language": r[18], "commit_sha": r[19]}

    return {
        "findings": [finding(r) for r in rows],
        "total": total,
        "returned": len(rows),
        "sort": sort if sort in FINDING_SORTS else "severity",
        "options": {
            "projects": [r[0] for r in projects],
            "languages": [r[0] for r in languages],
            "commits": [{"sha": r[0], "repo": r[1], "reviewed_at": iso(r[2])} for r in commits],
            "statuses": [r[0] for r in statuses],
            "severities": [r[0] for r in severities],
        },
    }

@app.get("/api/reviews")
def reviews_filtered(request: Request, repo: str | None = None, language: str | None = None,
                     commit: str | None = None, risk: str | None = None, limit: int = 200):
    """Filterable review runs. Same shape and same reasoning as /api/findings: review_runs carries
    the commit directly, and the language comes from the catalog join."""
    limit = max(1, min(limit, 500))
    where, params = [], []
    allowed = visibility_scope(request)
    if allowed is not None:
        where.append("r.repo_full_name = ANY(%s)"); params.append(allowed)
    if repo and repo != "all":
        where.append("r.repo_full_name = %s"); params.append(repo)
    if language and language != "all":
        where.append("c.primary_language = %s"); params.append(language)
    if commit and commit != "all":
        where.append("r.commit_sha = %s"); params.append(commit)
    if risk and risk != "all":
        where.append("r.risk = %s"); params.append(risk)
    clause = (" WHERE " + " AND ".join(where)) if where else ""

    joined = """ FROM review_runs r
        LEFT JOIN repository_catalog c ON c.repo_full_name = r.repo_full_name """

    with connect() as conn:
        total = conn.execute("SELECT count(*) " + joined + clause, params).fetchone()[0]
        rows = conn.execute("""SELECT r.id, r.repo_full_name, r.pr_number, r.pr_title, r.pr_url,
                r.risk, r.recommendation, r.finding_count, r.reviewed_at, r.commit_sha,
                c.primary_language """ + joined + clause + """
            ORDER BY r.reviewed_at DESC LIMIT %s""", params + [limit]).fetchall()
        projects = conn.execute(
            "SELECT DISTINCT repo_full_name FROM review_runs ORDER BY 1").fetchall()
        languages = conn.execute("""SELECT DISTINCT c.primary_language FROM repository_catalog c
            JOIN review_runs r ON r.repo_full_name = c.repo_full_name
            WHERE c.primary_language IS NOT NULL ORDER BY 1""").fetchall()
        commits = conn.execute("""SELECT commit_sha, repo_full_name, max(reviewed_at)
            FROM review_runs WHERE commit_sha <> ''
            GROUP BY commit_sha, repo_full_name ORDER BY max(reviewed_at) DESC LIMIT 50""").fetchall()
        risks = conn.execute("SELECT DISTINCT risk FROM review_runs ORDER BY 1").fetchall()

    def iso(v):
        return v.isoformat() if v else None

    return {
        "reviews": [{"id": r[0], "repo": r[1], "pr_number": r[2], "title": r[3], "url": r[4],
                     "risk": r[5], "recommendation": r[6], "findings": r[7],
                     "reviewed_at": iso(r[8]), "commit_sha": r[9], "language": r[10]}
                    for r in rows],
        "total": total,
        "returned": len(rows),
        "options": {
            "projects": [r[0] for r in projects],
            "languages": [r[0] for r in languages],
            "commits": [{"sha": r[0], "repo": r[1], "reviewed_at": iso(r[2])} for r in commits],
            "risks": [r[0] for r in risks],
        },
    }

@app.get("/api/repositories/{owner}/{repo}/commits")
def repository_commits(owner: str, repo: str, request: Request):
    require_repo_access(request, owner, repo)
    """Every commit known for a repository, newest first.

    A commit can arrive two ways - a push that got indexed, and a pull-request review that ran
    against it - so the two sets are unioned. Commits carrying findings are what a reader drills
    into, which is why the finding count is on every row.
    """
    full = f"{owner}/{repo}"
    with connect() as conn:
        rows = conn.execute("""
            WITH reviewed AS (
                SELECT commit_sha, max(reviewed_at) AS reviewed_at, count(*) AS reviews,
                       sum(finding_count) AS findings
                FROM review_runs WHERE repo_full_name = %s AND commit_sha <> ''
                GROUP BY commit_sha
            ), indexed AS (
                SELECT commit_sha, max(indexed_at) AS indexed_at,
                       max(file_count) AS files, max(chunk_count) AS chunks
                FROM repository_snapshots WHERE repo_full_name = %s
                GROUP BY commit_sha
            )
            SELECT COALESCE(rv.commit_sha, ix.commit_sha) AS sha,
                   rv.reviewed_at, ix.indexed_at, COALESCE(rv.reviews, 0),
                   COALESCE(rv.findings, 0), ix.files, ix.chunks
            FROM reviewed rv FULL OUTER JOIN indexed ix ON ix.commit_sha = rv.commit_sha
            ORDER BY GREATEST(COALESCE(rv.reviewed_at, TIMESTAMPTZ 'epoch'),
                              COALESCE(ix.indexed_at, TIMESTAMPTZ 'epoch')) DESC
            LIMIT 100""", (full, full)).fetchall()

    def iso(v):
        return v.isoformat() if v else None

    return {"repository": full, "commits": [
        {"sha": r[0], "reviewed_at": iso(r[1]), "indexed_at": iso(r[2]),
         "reviews": r[3], "findings": r[4], "files": r[5], "chunks": r[6]} for r in rows]}

# Finding status is set only from GitHub: a reviewer replies /resolved or /invalid on the
# finding's own PR comment and the webhook handler applies it. There is deliberately no
# dashboard endpoint that mutates status.

# --- per-owner credential settings --------------------------------------------------------
# The app has no authentication. These routes are gated only by an OPTIONAL shared token and a
# crude write rate limit, so every mutation is audited and no response ever carries a token.

class CredentialIn(BaseModel):
    token: str

_write_log: dict[str, list[float]] = {}
WRITE_LIMIT_PER_MIN = 10

def _client_addr(request: Request) -> tuple[str, str]:
    """(real client, full chain). Behind a tunnel the socket peer is just the tunnel, so the
    leftmost X-Forwarded-For entry is the meaningful one. Addresses are advisory, never access
    control - X-Forwarded-For is spoofable if the app is ever reachable without a proxy."""
    chain = request.headers.get("x-forwarded-for", "")
    if chain:
        return chain.split(",")[0].strip(), chain
    return (request.client.host if request.client else ""), ""

def _settings_guard(request: Request) -> tuple[str, str]:
    expected = settings.github_settings_admin_token
    if expected and request.headers.get("x-admin-token") != expected:
        raise HTTPException(403, "X-Admin-Token required")
    addr, chain = _client_addr(request)
    now = time.monotonic()
    hits = [t for t in _write_log.get(addr, []) if now - t < 60]
    if len(hits) >= WRITE_LIMIT_PER_MIN:
        raise HTTPException(429, "Too many credential changes; try again in a minute.")
    hits.append(now)
    _write_log[addr] = hits
    return addr, chain

@app.get("/api/credentials")
def credentials_list(request: Request, response: Response):
    # Credentials are owner-wide, so even listing them is an administrator action.
    web_auth.require_admin(request)
    response.headers["Cache-Control"] = "no-store"
    return {"key_status": key_status(), "credentials": list_credentials(),
            "global_fallback": {"configured": bool(settings.github_token),
                                "token_hint": mask_token(settings.github_token)},
            "admin_token_required": bool(settings.github_settings_admin_token)}

@app.put("/api/credentials/{owner}")
async def credentials_put(owner: str, body: CredentialIn, request: Request, response: Response):
    session = web_auth.require_admin(request)
    response.headers["Cache-Control"] = "no-store"
    addr, chain = _settings_guard(request)
    ua = request.headers.get("user-agent", "")
    owner = normalize_owner(owner)
    token = (body.token or "").strip()
    if not owner or not token:
        raise HTTPException(400, {"error": "invalid_input",
                                  "detail": "Both an owner and a token are required."})
    if key_status() != "ok":
        raise HTTPException(400, {"error": "key_missing", "detail":
            "GITHUB_CREDENTIAL_KEY is not configured, so tokens cannot be stored."})

    verdict = await verify_owner_token(owner, token)
    if verdict["status"] in REJECTED:
        # Nothing is written when GitHub rejects the token outright.
        audit(owner, "verify_failed", addr=addr, chain=chain, ua=ua,
              detail=f"{verdict['status']}: {verdict.get('detail')}")
        raise HTTPException(int(verdict.get("http_status") or 400),
                            {"error": verdict["status"], "detail": verdict.get("detail")})

    existed = get_credential(owner) is not None
    saved = save_credential(owner, verdict.get("verified_login") or owner, token, verdict)
    audit(owner, "updated" if existed else "created", addr=addr, chain=chain, ua=ua,
          detail=f"{verdict['status']} hint={saved['token_hint']}")
    logger.warning("credential %s for owner=%s by %s (status=%s)",
                   "updated" if existed else "created", owner, addr or "unknown", verdict["status"])
    return saved

@app.post("/api/credentials/{owner}/verify")
async def credentials_verify(owner: str, request: Request, response: Response):
    web_auth.require_admin(request)
    response.headers["Cache-Control"] = "no-store"
    addr, chain = _settings_guard(request)
    owner = normalize_owner(owner)
    if get_credential(owner) is None:
        raise HTTPException(404, "No credential stored for that owner")
    token = stored_token(owner)
    if token is None:
        raise HTTPException(409, {"error": "key_missing",
                                  "detail": "The stored token cannot be decrypted with the "
                                            "current GITHUB_CREDENTIAL_KEY."})
    verdict = await verify_owner_token(owner, token)
    record_verification(owner, verdict)
    audit(owner, "verified" if verdict["status"] not in REJECTED else "verify_failed",
          addr=addr, chain=chain, ua=request.headers.get("user-agent", ""),
          detail=f"{verdict['status']}: {verdict.get('detail')}")
    return {"verification": verdict, "credential": get_credential(owner)}

@app.delete("/api/credentials/{owner}")
def credentials_delete(owner: str, request: Request, response: Response):
    web_auth.require_admin(request)
    response.headers["Cache-Control"] = "no-store"
    addr, chain = _settings_guard(request)
    owner = normalize_owner(owner)
    if not delete_credential(owner):
        raise HTTPException(404, "No credential stored for that owner")
    audit(owner, "deleted", addr=addr, chain=chain,
          ua=request.headers.get("user-agent", ""))
    logger.warning("credential deleted for owner=%s by %s", owner, addr or "unknown")
    return {"deleted": True, "owner": owner}

@app.get("/health")
def health():
    return {"status": "ok"}

@app.get("/repositories/{owner}/{repo}/snapshots")
def snapshots(owner: str, repo: str, request: Request):
    require_repo_access(request, owner, repo)
    with connect() as conn:
        rows = conn.execute("SELECT commit_sha,indexed_at,file_count,chunk_count FROM repository_snapshots "
            "WHERE repo_full_name=%s ORDER BY indexed_at DESC LIMIT 50", (f"{owner}/{repo}",)).fetchall()
    return {"repository": f"{owner}/{repo}", "snapshots": [
        {"commit_sha": r[0], "indexed_at": r[1].isoformat(), "files": r[2], "chunks": r[3]} for r in rows]}

@app.post("/github/webhook")
async def webhook(request: Request, x_hub_signature_256: str | None = Header(default=None),
                  x_github_event: str | None = Header(default=None),
                  x_github_delivery: str | None = Header(default=None)):
    raw = await request.body()
    if not verify_signature(settings.github_webhook_secret, raw, x_hub_signature_256):
        raise HTTPException(401, "Invalid webhook signature")
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        raise HTTPException(400, "Invalid JSON")
    repo_obj = payload.get("repository") or {}
    owner = (repo_obj.get("owner") or {}).get("login")
    repo_name = repo_obj.get("name")
    if not owner or not repo_name:
        raise HTTPException(400, "Missing repository metadata")
    try:
        # A stored per-owner token, else the global one. Built inside the try so a database problem
        # here returns the same 502 as any other processing failure rather than an uncaught 500.
        try:
            gh = credential_client(owner)
        except NoCredentialError as exc:
            raise HTTPException(503, str(exc)) from exc
        logger.info("webhook delivery=%s event=%s owner=%s credential=%s",
                    x_github_delivery, x_github_event, owner, gh.source)
        if x_github_event == "push":
            sha = payload.get("after")
            if not sha or set(sha) == {"0"}:
                return {"status": "ignored", "reason": "branch deleted or missing SHA"}
            return {"status": "indexed", **(await index_commit(gh, owner, repo_name, sha))}
        if x_github_event == "pull_request_review_comment":
            if payload.get("action") != "created":
                return {"status": "ignored", "reason": "action not reviewed"}
            return await handle_review_comment_command(gh, owner, repo_name, payload)
        if x_github_event == "pull_request_review_thread":
            return await handle_review_thread(gh, owner, repo_name, payload)
        if x_github_event == "issue_comment":
            if payload.get("action") != "created":
                return {"status": "ignored", "reason": "action not reviewed"}
            if not (payload.get("issue") or {}).get("pull_request"):
                return {"status": "ignored", "reason": "not a pull request comment"}
            return await handle_issue_comment_command(gh, owner, repo_name, payload)
        if x_github_event != "pull_request":
            return JSONResponse({"status": "ignored", "reason": "unsupported event"})
        if payload.get("action") not in {"opened", "synchronize", "reopened", "ready_for_review"}:
            return {"status": "ignored", "reason": "action not reviewed"}
        pr = payload.get("pull_request") or {}
        if pr.get("draft"):
            return {"status": "ignored", "reason": "draft PR"}
        number = int(payload.get("number") or 0)
        head, base = pr.get("head") or {}, pr.get("base") or {}
        head_sha, base_sha = head.get("sha"), base.get("sha")
        if not number or not head_sha:
            raise HTTPException(400, "Missing PR number or head SHA")
        indexed = await index_commit(gh, owner, repo_name, head_sha)
        files = await gh.get_pr_files(owner, repo_name, number)
        changed = [f.get("filename", "") for f in files if f.get("filename")]
        diff = "\n\n".join(f"### {f.get('filename')} ({f.get('status')})\n{f.get('patch') or '[No text patch]'}"
                             for f in files)[:settings.max_diff_chars]
        query = f"Repository {owner}/{repo_name}. PR {pr.get('title','')}. {pr.get('body') or ''}. Changed: {', '.join(changed)}. Analyze downstream impact, contracts, failure modes, security and tests."
        qvec = await query_embedding(query)
        context = retrieve_context(f"{owner}/{repo_name}", head_sha, qvec, changed)
        review = await Reviewer().review({"repository": f"{owner}/{repo_name}", "commit_sha": head_sha,
            "base_commit_sha": base_sha, "pull_request": {"number": number, "title": pr.get("title",""),
            "description": pr.get("body") or "", "base_branch": base.get("ref"), "head_branch": head.get("ref")},
            "changed_files": changed, "diff": diff, "application_context": context, "indexing_summary": indexed})
        findings = review.get("findings") or []
        repo_full = f"{owner}/{repo_name}"

        # Insert and commit before any network I/O: never hold a DB transaction open across HTTP.
        with connect() as conn:
            run_id = conn.execute("""INSERT INTO review_runs(repo_full_name,pr_number,pr_title,pr_url,commit_sha,risk,recommendation,finding_count)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id""",
                (repo_full, number, pr.get("title") or "", pr.get("html_url") or "",
                 head_sha, review.get("risk", "unknown"), review.get("merge_recommendation", "review_required"), len(findings))).fetchone()[0]
            stored = []
            for f in findings:
                fid = conn.execute("""INSERT INTO review_findings(review_id,repo_full_name,pr_number,title,severity,category,file_path,evidence,failure_scenario,impact,recommendation)
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id""",
                    (run_id, repo_full, number, str(f.get("title") or "Untitled finding")[:500],
                     str(f.get("severity") or "medium").lower(), str(f.get("category") or "general")[:120],
                     str(f.get("file") or "")[:500], str(f.get("evidence") or "")[:5000],
                     str(f.get("failure_scenario") or "")[:3000], str(f.get("impact") or "")[:3000],
                     str(f.get("recommendation") or "")[:3000])).fetchone()[0]
                stored.append((fid, f))

        # Anchor against the raw per-file patches, not the truncated `diff` string above.
        patch_index = build_patch_index(files)
        posted = {"inline": 0, "standalone": 0, "failed": 0}
        for fid, f in stored[:MAX_INDIVIDUAL_COMMENTS]:
            try:
                line_no = coerce_line(f.get("line"))
                anchor = resolve_anchor(patch_index.get(f.get("file") or ""), line_no)
                res, body, kind = None, None, None
                if anchor is not None:
                    body = render_finding_comment(f, fid, anchor, inline=True)
                    res = await gh.create_review_comment(owner, repo_name, number, body,
                                                         head_sha, f.get("file"), anchor)
                    if res is not None:
                        kind = "review_comment"
                if res is None:
                    # Either it could not be anchored, or GitHub rejected the line as not in the
                    # diff. A standalone comment always works.
                    body = render_finding_comment(f, fid, None, inline=False)
                    res = await gh.post_pr_comment(owner, repo_name, number, body)
                    kind = "issue_comment"
                with connect() as conn:
                    conn.execute("""UPDATE review_findings SET line_no=%s, anchor_line=%s,
                        comment_kind=%s, comment_id=%s, comment_url=%s, comment_body=%s WHERE id=%s""",
                        (line_no, anchor, kind, res.get("id"), res.get("html_url"), body, fid))
                posted["inline" if kind == "review_comment" else "standalone"] += 1
            except Exception:
                # One bad finding must not cost us the whole review.
                logger.exception("Could not post comment for finding id=%s", fid)
                posted["failed"] += 1

        await gh.post_pr_comment(owner, repo_name, number, render_comment(review, len(context)))
        logger.info("review posted delivery=%s repo=%s pr=%s sha=%s findings=%s",
                    x_github_delivery, owner, number, head_sha, posted)
        return {"status": "review_posted", "repository": repo_full, "pull_request": number,
                "commit_sha": head_sha, "context_records": len(context),
                "risk": review.get("risk"), "comments": posted}
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Webhook processing failed delivery=%s", x_github_delivery)
        raise HTTPException(502, "Processing failed; inspect service logs") from exc
