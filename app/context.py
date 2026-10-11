from app.db import connect
from app.config import settings

def retrieve_context(repo: str, commit_sha: str, query_vector: list[float],
                     changed_paths: list[str]) -> list[dict]:
    conn = connect()
    try:
        rows = conn.execute("""SELECT file_path,content,content_type,
            1-(embedding <=> %s::vector) AS similarity FROM context_chunks
            WHERE repo_full_name=%s AND commit_sha=%s
            ORDER BY embedding <=> %s::vector LIMIT %s""",
            (query_vector, repo, commit_sha, query_vector, settings.max_context_chunks)).fetchall()
        out, seen = [], set()
        for path, content, kind, score in rows:
            key = (path, content)
            if key not in seen:
                out.append({"path": path, "content": content, "type": kind, "similarity": float(score)})
                seen.add(key)
        if changed_paths:
            symbols = conn.execute("""SELECT symbol_id,name,kind,file_path,start_line,end_line,signature
                FROM code_symbols WHERE repo_full_name=%s AND commit_sha=%s AND file_path=ANY(%s) LIMIT 150""",
                (repo, commit_sha, changed_paths)).fetchall()
            ids = [s[0] for s in symbols]
            neighbors = []
            if ids:
                neighbors = conn.execute("""SELECT DISTINCT s.symbol_id,s.name,s.kind,s.file_path,
                    s.start_line,s.end_line,s.signature FROM code_edges e JOIN code_symbols s
                    ON s.repo_full_name=e.repo_full_name AND s.commit_sha=e.commit_sha AND s.symbol_id=e.target_id
                    WHERE e.repo_full_name=%s AND e.commit_sha=%s AND e.source_id=ANY(%s) LIMIT 100""",
                    (repo, commit_sha, ids)).fetchall()
            for s in symbols + neighbors:
                content = f"Symbol: {s[1]} ({s[2]})\nFile: {s[3]}:{s[4]}-{s[5]}\nSignature: {s[6] or ''}"
                key = (s[3], content)
                if key not in seen:
                    out.append({"path": s[3], "content": content, "type": "symbol_graph", "similarity": None})
                    seen.add(key)
        return out[:settings.max_context_chunks + 20]
    finally:
        conn.close()
