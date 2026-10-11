import httpx
from urllib.parse import quote

from app.github_urls import graphql_url, rest_base

class GitHubClient:
    def __init__(self, token: str, *, api_url: str | None = None, graphql: str | None = None):
        # Resolved lazily so this module stays importable without app.config (and therefore without
        # a populated environment), which is what lets the URL helpers be unit-tested on their own.
        if api_url is None or graphql is None:
            from app.config import settings
            api_url = api_url if api_url is not None else settings.github_api_url
            graphql = graphql if graphql is not None else settings.github_graphql_url
        self.api = rest_base(api_url)
        self.graphql_api = graphql_url(api_url, graphql)
        self.token = token
        self.headers = {
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }
    # NOTE: there is deliberately no "is this comment ours?" helper based on GET /user. The token
    # belongs to the repo owner, so comparing logins would discard the owner's own triage replies.
    # main.is_our_comment matches on the markers we embed in our comments instead.

    async def get_json(self, path: str):
        async with httpx.AsyncClient(timeout=40) as client:
            r = await client.get(f"{self.api}{path}", headers=self.headers)
            r.raise_for_status()
            return r.json()

    async def probe_json(self, path: str) -> tuple[int, object, dict]:
        """GET returning (status, json|None, headers) instead of raising.

        Credential verification has to tell a 401 (dead token) from a 404 (private resource the
        token cannot see), and raise_for_status() would collapse both into one exception.
        """
        async with httpx.AsyncClient(timeout=20) as client:
            r = await client.get(f"{self.api}{path}", headers=self.headers)
            try:
                data = r.json()
            except Exception:
                data = None
            return r.status_code, data, dict(r.headers)

    async def get_bytes(self, url: str, max_bytes: int) -> bytes:
        async with httpx.AsyncClient(timeout=90, follow_redirects=True) as client:
            async with client.stream("GET", url, headers=self.headers) as r:
                r.raise_for_status()
                result, total = [], 0
                async for part in r.aiter_bytes():
                    total += len(part)
                    if total > max_bytes:
                        raise ValueError("Repository archive exceeds MAX_ARCHIVE_BYTES")
                    result.append(part)
                return b"".join(result)

    async def get_archive(self, owner: str, repo: str, ref: str, max_bytes: int) -> bytes:
        url = f"{self.api}/repos/{quote(owner)}/{quote(repo)}/tarball/{quote(ref, safe='')}"
        return await self.get_bytes(url, max_bytes)

    async def get_pr_files(self, owner: str, repo: str, number: int) -> list[dict]:
        out = []
        for page in range(1, 4):
            data = await self.get_json(
                f"/repos/{quote(owner)}/{quote(repo)}/pulls/{number}/files?per_page=100&page={page}")
            out.extend(data)
            if len(data) < 100:
                break
        return out

    async def post_pr_comment(self, owner: str, repo: str, number: int, body: str) -> dict:
        async with httpx.AsyncClient(timeout=40) as client:
            r = await client.post(f"{self.api}/repos/{quote(owner)}/{quote(repo)}/issues/{number}/comments",
                                  headers=self.headers, json={"body": body})
            r.raise_for_status()
            return r.json()

    async def create_review_comment(self, owner: str, repo: str, number: int, body: str,
                                    commit_id: str, path: str, line: int,
                                    side: str = "RIGHT") -> dict | None:
        """Post a single inline comment on a diff line. Returns None on 422 (not an error).

        GitHub answers 422 when the line is not part of the PR diff, which means this finding
        cannot be anchored inline and the caller should fall back to a standalone comment.
        Every other failure is re-raised so token/permission problems stay visible rather than
        silently degrading every finding.
        """
        async with httpx.AsyncClient(timeout=40) as client:
            r = await client.post(
                f"{self.api}/repos/{quote(owner)}/{quote(repo)}/pulls/{number}/comments",
                headers=self.headers,
                json={"body": body, "commit_id": commit_id, "path": path,
                      "line": line, "side": side})
            if r.status_code == 422:
                return None
            r.raise_for_status()
            return r.json()

    async def get_review_comment(self, owner: str, repo: str, comment_id: int) -> dict:
        return await self.get_json(f"/repos/{quote(owner)}/{quote(repo)}/pulls/comments/{comment_id}")

    async def get_issue_comment(self, owner: str, repo: str, comment_id: int) -> dict:
        return await self.get_json(f"/repos/{quote(owner)}/{quote(repo)}/issues/comments/{comment_id}")

    async def edit_review_comment(self, owner: str, repo: str, comment_id: int, body: str) -> dict:
        return await self._patch_comment(f"/repos/{quote(owner)}/{quote(repo)}/pulls/comments/{comment_id}", body)

    async def edit_issue_comment(self, owner: str, repo: str, comment_id: int, body: str) -> dict:
        return await self._patch_comment(f"/repos/{quote(owner)}/{quote(repo)}/issues/comments/{comment_id}", body)

    async def _patch_comment(self, path: str, body: str) -> dict:
        async with httpx.AsyncClient(timeout=40) as client:
            r = await client.patch(f"{self.api}{path}", headers=self.headers, json={"body": body})
            r.raise_for_status()
            return r.json()

    # --- Onboarding and per-user visibility ---------------------------------------------------

    async def get_repo(self, owner: str, repo: str) -> tuple[int, dict | None]:
        """(status, repo) without raising, so onboarding can say *why* a repository is unreachable.

        A 404 here means the credential cannot see the repo, which during onboarding is the normal
        "they have not granted access yet" state rather than an error.
        """
        status, data, _ = await self.probe_json(f"/repos/{quote(owner)}/{quote(repo)}")
        return status, data if isinstance(data, dict) else None

    async def list_user_repos(self, token: str, max_pages: int = 10) -> list[dict]:
        """Every repository a *user* token can see, private ones included.

        Uses the supplied token rather than this client's own: answering "what can this person
        reach" requires acting as them, which is the whole reason users sign in through OAuth.
        """
        headers = {**self.headers, "Authorization": f"Bearer {token}"}
        out: list[dict] = []
        async with httpx.AsyncClient(timeout=40) as client:
            for page in range(1, max_pages + 1):
                r = await client.get(
                    f"{self.api}/user/repos?per_page=100&page={page}&affiliation=owner,collaborator,organization_member",
                    headers=headers)
                r.raise_for_status()
                batch = r.json()
                out.extend(batch)
                if len(batch) < 100:
                    break
        return out

    async def get_collaborator_permission(self, owner: str, repo: str, login: str) -> str | None:
        """A user's effective permission on a repository: admin | write | read | none.

        GitHub resolves this through direct collaboration *and* org/team grants, so it answers
        the real question without us reimplementing team inheritance. Returns None when the
        answer cannot be read at all.
        """
        status, data, _ = await self.probe_json(
            f"/repos/{quote(owner)}/{quote(repo)}/collaborators/{quote(login)}/permission")
        if status != 200 or not isinstance(data, dict):
            return None
        return data.get("permission")

    # --- Review thread resolution (GraphQL only; the REST API cannot resolve a thread) ---

    async def graphql(self, query: str, variables: dict | None = None) -> dict:
        async with httpx.AsyncClient(timeout=40) as client:
            r = await client.post(self.graphql_api, headers=self.headers,
                                  json={"query": query, "variables": variables or {}})
            r.raise_for_status()
            payload = r.json()
            if payload.get("errors"):
                raise RuntimeError(f"GraphQL error: {str(payload['errors'])[:300]}")
            return payload.get("data") or {}

    async def find_review_thread(self, owner: str, repo: str, number: int,
                                 comment_id: int) -> str | None:
        """Node id of the review thread containing this comment, or None.

        Threads are only reachable through GraphQL, and the thread a comment belongs to is not
        returned when the comment is created, so it has to be looked up by walking the PR's
        threads for the one holding our comment id.
        """
        query = """query($owner:String!,$name:String!,$number:Int!){
          repository(owner:$owner,name:$name){ pullRequest(number:$number){
            reviewThreads(first:100){ nodes { id isResolved
              comments(first:100){ nodes { databaseId } } } } } } }"""
        data = await self.graphql(query, {"owner": owner, "name": repo, "number": number})
        nodes = (((data.get("repository") or {}).get("pullRequest") or {})
                 .get("reviewThreads") or {}).get("nodes") or []
        for t in nodes:
            for c in ((t.get("comments") or {}).get("nodes") or []):
                if c.get("databaseId") == comment_id:
                    return t.get("id")
        return None

    async def set_review_thread_resolved(self, thread_id: str, resolved: bool) -> bool:
        mutation = ("mutation($id:ID!){ %s(input:{threadId:$id}){ thread { isResolved } } }"
                    % ("resolveReviewThread" if resolved else "unresolveReviewThread"))
        data = await self.graphql(mutation, {"id": thread_id})
        key = "resolveReviewThread" if resolved else "unresolveReviewThread"
        return bool((data.get(key) or {}).get("thread", {}).get("isResolved"))
