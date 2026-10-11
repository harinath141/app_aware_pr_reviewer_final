import hashlib
import json
import re
from openai import AsyncOpenAI
from app.config import settings
from app.db import connect
from app.analyzer import analyze_files, chunk_text, stable_id
from app.file_policy import FilePolicy, policy_for
from app.repository import safe_extract_tar_gz

def sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()

def infer_language(files: dict[str, str]) -> str:
    counts = {}
    ext_map = {".py":"Python", ".js":"JavaScript", ".jsx":"JavaScript", ".mjs":"JavaScript",
        ".cjs":"JavaScript", ".ts":"TypeScript", ".tsx":"TypeScript", ".java":"Java",
        ".go":"Go", ".rs":"Rust", ".rb":"Ruby", ".php":"PHP", ".cs":"C#",
        ".cpp":"C++", ".c":"C", ".kt":"Kotlin", ".swift":"Swift", ".dart":"Dart"}
    from pathlib import PurePosixPath
    for path in files:
        name = PurePosixPath(path).name.lower()
        lang = ext_map.get(PurePosixPath(path).suffix.lower())
        if name == "dockerfile": lang = "Dockerfile"
        if lang: counts[lang] = counts.get(lang, 0) + 1
    return max(counts, key=counts.get) if counts else "Unknown"

def infer_description(files: dict[str, str]) -> str:
    readme = next((v for k, v in files.items() if k.lower() in {"readme.md", "readme.rst", "readme.txt"}), "")
    lines = [re.sub(r"^#+\s*", "", x).strip() for x in readme.splitlines() if x.strip()]
    lines = [x for x in lines if not x.startswith(("!", "[![", "```", "<"))]
    if lines:
        title = lines[0][:180]
        body = next((x for x in lines[1:] if len(x) > 35), "")
        return (title + (" — " + body[:260] if body else ""))[:420]
    if "package.json" in files:
        try:
            data = json.loads(files["package.json"])
            if data.get("description"): return str(data["description"])[:420]
            if data.get("name"): return f"Application package: {data['name']}"
        except Exception: pass
    if "pyproject.toml" in files:
        m = re.search(r"(?m)^description\s*=\s*[\"'](.+?)[\"']", files["pyproject.toml"])
        if m: return m.group(1)[:420]
    if "requirements.txt" in files or "pyproject.toml" in files: return "Python application; summary will improve when a README or project description is available."
    return "Description inferred from repository documentation and manifests; add a README to make this profile more useful."

class Indexer:
    def __init__(self):
        self.client = AsyncOpenAI(api_key=settings.llm_api_key,
            base_url=settings.embedding_base_url or settings.llm_base_url)

    async def embed(self, texts: list[str]) -> list[list[float]]:
        vectors = []
        for start in range(0, len(texts), 64):
            response = await self.client.embeddings.create(
                model=settings.embedding_model, input=texts[start:start + 64])
            for item in sorted(response.data, key=lambda x: x.index):
                if len(item.embedding) != settings.embedding_dimensions:
                    raise ValueError("Embedding dimensions mismatch: update EMBEDDING_DIMENSIONS and db schema")
                vectors.append(item.embedding)
        return vectors

    async def index_archive(self, repo: str, commit_sha: str, archive: bytes,
                            policy: FilePolicy | None = None,
                            stats: dict | None = None) -> dict:
        # A repository that was never onboarded has no settings row, which resolves to an empty
        # policy - and an empty policy allows everything. So indexing behaviour for existing
        # repositories is unchanged by this parameter existing.
        if policy is None:
            policy = policy_for(repo)
        files = safe_extract_tar_gz(archive, policy, stats)
        symbols, edges = analyze_files(files)
        # code_edges is keyed on (repo, commit, source, target, edge_type), so a relationship
        # found at several call sites would be collapsed by ON CONFLICT DO NOTHING. Fold those
        # here, otherwise repository_catalog.edge_count advertises rows the table never keeps -
        # measured on one repository: 154 reported, 109 stored.
        edges = list({(e.source_id, e.target_id, e.edge_type): e for e in edges}.values())
        language = infer_language(files)
        description = infer_description(files)
        chunks = []
        for path, content in files.items():
            for idx, chunk in enumerate(chunk_text(content, settings.max_chunk_chars)):
                if chunk.strip():
                    chunks.append({"chunk_id": stable_id(path, str(idx)), "file_path": path,
                        "chunk_index": idx, "content_hash": sha(chunk),
                        "content_type": "source_or_document", "content": chunk})
        conn = connect()
        try:
            hashes = list({c["content_hash"] for c in chunks})
            reusable = {}
            if hashes:
                rows = conn.execute(
                    "SELECT DISTINCT ON (content_hash) content_hash, embedding FROM context_chunks "
                    "WHERE repo_full_name=%s AND content_hash = ANY(%s) ORDER BY content_hash, commit_sha DESC",
                    (repo, hashes)).fetchall()
                reusable = {r[0]: r[1] for r in rows}
            unique_missing = {}
            for c in chunks:
                if c["content_hash"] not in reusable:
                    unique_missing.setdefault(c["content_hash"], c["content"])
            new_vectors = await self.embed(list(unique_missing.values())) if unique_missing else []
            vectors = {**reusable, **dict(zip(unique_missing.keys(), new_vectors))}
            with conn.transaction():
                for table in ("context_chunks", "code_symbols", "code_edges"):
                    conn.execute(f"DELETE FROM {table} WHERE repo_full_name=%s AND commit_sha=%s",
                                 (repo, commit_sha))
                for c in chunks:
                    conn.execute("""INSERT INTO context_chunks
                    (repo_full_name,commit_sha,chunk_id,file_path,chunk_index,content_hash,content_type,content,embedding)
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                    (repo, commit_sha, c["chunk_id"], c["file_path"], c["chunk_index"],
                     c["content_hash"], c["content_type"], c["content"], vectors[c["content_hash"]]))
                for s in symbols:
                    conn.execute("""INSERT INTO code_symbols
                    (repo_full_name,commit_sha,symbol_id,name,kind,file_path,start_line,end_line,signature)
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                    (repo, commit_sha, s.symbol_id, s.name, s.kind, s.file_path,
                     s.start_line, s.end_line, s.signature))
                for e in edges:
                    conn.execute("""INSERT INTO code_edges
                    (repo_full_name,commit_sha,source_id,target_id,edge_type,evidence_path,evidence_line)
                    VALUES (%s,%s,%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING""",
                    (repo, commit_sha, e.source_id, e.target_id, e.edge_type, e.evidence_path, e.evidence_line))
                conn.execute("""INSERT INTO repository_snapshots(repo_full_name,commit_sha,file_count,chunk_count)
                    VALUES (%s,%s,%s,%s) ON CONFLICT(repo_full_name,commit_sha) DO UPDATE SET
                    indexed_at=now(),file_count=EXCLUDED.file_count,chunk_count=EXCLUDED.chunk_count""",
                    (repo, commit_sha, len(files), len(chunks)))
                conn.execute("""INSERT INTO repository_catalog
                    (repo_full_name,primary_language,description,latest_sha,indexed_at,file_count,chunk_count,symbol_count,edge_count)
                    VALUES (%s,%s,%s,%s,now(),%s,%s,%s,%s)
                    ON CONFLICT(repo_full_name) DO UPDATE SET primary_language=EXCLUDED.primary_language,
                    description=CASE WHEN EXCLUDED.description <> '' THEN EXCLUDED.description ELSE repository_catalog.description END,
                    latest_sha=EXCLUDED.latest_sha,indexed_at=now(),file_count=EXCLUDED.file_count,
                    chunk_count=EXCLUDED.chunk_count,symbol_count=EXCLUDED.symbol_count,edge_count=EXCLUDED.edge_count""",
                    (repo, language, description, commit_sha, len(files), len(chunks), len(symbols), len(edges)))
            # The embedding-reuse SELECT above opens an implicit transaction, which makes the
            # block above a nested SAVEPOINT rather than a committing transaction. Without this
            # explicit commit, close() below rolls back the entire snapshot.
            conn.commit()
            return {"repo": repo, "commit_sha": commit_sha, "files": len(files),
                    "chunks": len(chunks), "symbols": len(symbols), "edges": len(edges),
                    "language": language, "description": description,
                    "new_unique_embeddings": len(unique_missing)}
        finally:
            conn.close()
