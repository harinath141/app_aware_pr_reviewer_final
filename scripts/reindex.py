"""Re-index repositories that already have a snapshot on record.

Indexing short-circuits when a (repo, commit) pair is already stored, so a repository indexed
before an analyzer change keeps its old symbols and edges indefinitely — no push will refresh the
same commit. This re-runs indexing for the snapshot already on record, regenerating symbols and
edges in place. `Indexer.index_archive` deletes and re-inserts them for that exact pair.

    python scripts/reindex.py owner/name [owner/other ...]
    python scripts/reindex.py --all

Embeddings are reused by content hash, so an unchanged commit makes no embedding calls and costs
nothing against the LLM endpoint. It does re-download each repository archive from GitHub, using
the same per-owner credential resolution as the webhook.

Deliberately a CLI and not an HTTP route: the app has no authentication, so an endpoint that
downloads a repository archive on demand would be a trivial way to exhaust the host.
"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config import settings  # noqa: E402
from app.credentials import NoCredentialError, credential_client  # noqa: E402
from app.db import connect  # noqa: E402
from app.indexer import Indexer  # noqa: E402


def select(arguments: list[str]) -> list[tuple[str, str]]:
    with connect() as conn:
        if arguments == ["--all"]:
            return conn.execute(
                "SELECT repo_full_name, latest_sha FROM repository_catalog"
                " WHERE latest_sha IS NOT NULL ORDER BY repo_full_name").fetchall()
        return conn.execute(
            "SELECT repo_full_name, latest_sha FROM repository_catalog"
            " WHERE repo_full_name = ANY(%s) ORDER BY repo_full_name", (arguments,)).fetchall()


async def run(arguments: list[str]) -> int:
    if not arguments:
        print(__doc__)
        return 2

    rows = select(arguments)
    if not rows:
        print("No catalogued repository matched, or none has a snapshot to re-index.")
        return 1

    indexer = Indexer()
    failures = 0
    for repo, commit_sha in rows:
        owner, _, name = repo.partition("/")
        label = f"{repo}@{commit_sha[:8]}"
        try:
            gh = credential_client(owner)
            archive = await gh.get_archive(owner, name, commit_sha, settings.max_archive_bytes)
            result = await indexer.index_archive(repo, commit_sha, archive)
            print(f"{label}  credential={gh.source}  symbols={result['symbols']}"
                  f"  edges={result['edges']}  chunks={result['chunks']}"
                  f"  new_embeddings={result['new_unique_embeddings']}")
        except NoCredentialError as exc:
            failures += 1
            print(f"{label}  FAILED: no credential ({exc})")
        except Exception as exc:  # noqa: BLE001 - one bad repo must not stop the rest
            failures += 1
            print(f"{label}  FAILED: {type(exc).__name__}: {exc}")

    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(run(sys.argv[1:])))
