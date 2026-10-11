import psycopg
from pgvector.psycopg import register_vector
from app.config import settings

SCHEMA = f"""
CREATE EXTENSION IF NOT EXISTS vector;
CREATE TABLE IF NOT EXISTS repository_snapshots (
 repo_full_name TEXT NOT NULL, commit_sha TEXT NOT NULL,
 indexed_at TIMESTAMPTZ NOT NULL DEFAULT now(),
 file_count INTEGER NOT NULL DEFAULT 0, chunk_count INTEGER NOT NULL DEFAULT 0,
 PRIMARY KEY(repo_full_name, commit_sha));
CREATE TABLE IF NOT EXISTS context_chunks (
 repo_full_name TEXT NOT NULL, commit_sha TEXT NOT NULL, chunk_id TEXT NOT NULL,
 file_path TEXT NOT NULL, chunk_index INTEGER NOT NULL, content_hash TEXT NOT NULL,
 content_type TEXT NOT NULL, content TEXT NOT NULL, embedding vector({int(settings.embedding_dimensions)}) NOT NULL,
 PRIMARY KEY(repo_full_name, commit_sha, chunk_id));
CREATE INDEX IF NOT EXISTS context_chunks_repo_commit_idx ON context_chunks(repo_full_name, commit_sha);
CREATE TABLE IF NOT EXISTS code_symbols (
 repo_full_name TEXT NOT NULL, commit_sha TEXT NOT NULL, symbol_id TEXT NOT NULL,
 name TEXT NOT NULL, kind TEXT NOT NULL, file_path TEXT NOT NULL,
 start_line INTEGER, end_line INTEGER, signature TEXT,
 PRIMARY KEY(repo_full_name, commit_sha, symbol_id));
CREATE INDEX IF NOT EXISTS code_symbols_name_idx ON code_symbols(repo_full_name, commit_sha, name);
CREATE TABLE IF NOT EXISTS code_edges (
 repo_full_name TEXT NOT NULL, commit_sha TEXT NOT NULL, source_id TEXT NOT NULL,
 target_id TEXT NOT NULL, edge_type TEXT NOT NULL, evidence_path TEXT, evidence_line INTEGER,
 PRIMARY KEY(repo_full_name, commit_sha, source_id, target_id, edge_type));
CREATE INDEX IF NOT EXISTS code_edges_source_idx ON code_edges(repo_full_name, commit_sha, source_id);
CREATE TABLE IF NOT EXISTS repository_catalog (
 repo_full_name TEXT PRIMARY KEY, primary_language TEXT NOT NULL DEFAULT 'Unknown',
 description TEXT NOT NULL DEFAULT '', default_branch TEXT, latest_sha TEXT,
 indexed_at TIMESTAMPTZ NOT NULL DEFAULT now(), file_count INTEGER NOT NULL DEFAULT 0,
 chunk_count INTEGER NOT NULL DEFAULT 0, symbol_count INTEGER NOT NULL DEFAULT 0,
 edge_count INTEGER NOT NULL DEFAULT 0);
CREATE TABLE IF NOT EXISTS review_runs (
 id BIGSERIAL PRIMARY KEY, repo_full_name TEXT NOT NULL, pr_number INTEGER NOT NULL,
 pr_title TEXT NOT NULL DEFAULT '', pr_url TEXT NOT NULL DEFAULT '', commit_sha TEXT NOT NULL DEFAULT '',
 risk TEXT NOT NULL DEFAULT 'unknown', recommendation TEXT NOT NULL DEFAULT 'review_required',
 finding_count INTEGER NOT NULL DEFAULT 0, reviewed_at TIMESTAMPTZ NOT NULL DEFAULT now());
CREATE INDEX IF NOT EXISTS review_runs_repo_idx ON review_runs(repo_full_name, reviewed_at DESC);
CREATE TABLE IF NOT EXISTS review_findings (
 id BIGSERIAL PRIMARY KEY, review_id BIGINT NOT NULL REFERENCES review_runs(id) ON DELETE CASCADE,
 repo_full_name TEXT NOT NULL, pr_number INTEGER NOT NULL, title TEXT NOT NULL DEFAULT '',
 severity TEXT NOT NULL DEFAULT 'medium', category TEXT NOT NULL DEFAULT 'general',
 file_path TEXT NOT NULL DEFAULT '', evidence TEXT NOT NULL DEFAULT '', failure_scenario TEXT NOT NULL DEFAULT '',
 impact TEXT NOT NULL DEFAULT '', recommendation TEXT NOT NULL DEFAULT '', status TEXT NOT NULL DEFAULT 'open',
 line_no INTEGER, anchor_line INTEGER, comment_kind TEXT, comment_id BIGINT,
 comment_url TEXT, comment_body TEXT, status_actor TEXT, status_updated_at TIMESTAMPTZ,
 created_at TIMESTAMPTZ NOT NULL DEFAULT now(), resolved_at TIMESTAMPTZ);
CREATE INDEX IF NOT EXISTS review_findings_status_idx ON review_findings(status, severity);
CREATE TABLE IF NOT EXISTS owner_credentials (
 owner TEXT PRIMARY KEY, owner_login TEXT NOT NULL,
 token_ciphertext TEXT NOT NULL, token_hint TEXT NOT NULL, key_fingerprint TEXT NOT NULL,
 verified_login TEXT, scopes TEXT, repo_access_count INTEGER, owner_is_org BOOLEAN,
 last_verified_at TIMESTAMPTZ, last_verification_status TEXT, last_verification_detail TEXT,
 created_at TIMESTAMPTZ NOT NULL DEFAULT now(), updated_at TIMESTAMPTZ NOT NULL DEFAULT now());
CREATE TABLE IF NOT EXISTS credential_audit (
 id BIGSERIAL PRIMARY KEY, owner TEXT NOT NULL, action TEXT NOT NULL,
 actor_addr TEXT, actor_forwarded_chain TEXT, actor_ua TEXT, detail TEXT,
 created_at TIMESTAMPTZ NOT NULL DEFAULT now());
-- Per-repository onboarding settings. A repository with no row here indexes exactly as it did
-- before this table existed - the built-in filters in app/repository.py are applied regardless and
-- are deliberately NOT recorded here, so they cannot leak through an API response.
CREATE TABLE IF NOT EXISTS repository_settings (
 repo_full_name TEXT PRIMARY KEY, description TEXT NOT NULL DEFAULT '',
 include_patterns TEXT[] NOT NULL DEFAULT ARRAY[]::TEXT[],
 exclude_patterns TEXT[] NOT NULL DEFAULT ARRAY[]::TEXT[],
 onboarded_by TEXT NOT NULL DEFAULT '', onboarded_at TIMESTAMPTZ NOT NULL DEFAULT now(),
 status TEXT NOT NULL DEFAULT 'active');
-- Browser sessions. The id is 256 bits of randomness and is the whole cookie, which is why it
-- needs no signature; holding the row server-side is what makes revocation possible. The GitHub
-- OAuth token is ciphertext, encrypted with the same key as owner credentials.
CREATE TABLE IF NOT EXISTS sessions (
 id TEXT PRIMARY KEY, username TEXT NOT NULL, ldap_dn TEXT NOT NULL DEFAULT '',
 display_name TEXT NOT NULL DEFAULT '', role TEXT NOT NULL DEFAULT 'user',
 github_login TEXT, github_repos TEXT[] NOT NULL DEFAULT ARRAY[]::TEXT[],
 github_repos_at TIMESTAMPTZ,
 github_token_ciphertext TEXT,
 created_at TIMESTAMPTZ NOT NULL DEFAULT now(), expires_at TIMESTAMPTZ NOT NULL,
 last_seen_at TIMESTAMPTZ NOT NULL DEFAULT now());
CREATE INDEX IF NOT EXISTS sessions_expires_idx ON sessions(expires_at);
"""
# NOTE: the index on (comment_kind, comment_id) deliberately lives in MIGRATIONS below, not in
# SCHEMA. On an existing database CREATE TABLE IF NOT EXISTS is a no-op, so those columns only
# appear after the ALTER TABLEs run — referencing them any earlier fails with UndefinedColumn.

# Columns added after the first release. CREATE TABLE IF NOT EXISTS will not alter a table that
# already exists, so every new column must also be listed here. ADD COLUMN IF NOT EXISTS is
# idempotent, so this is safe to run on every startup.
MIGRATIONS = """
ALTER TABLE review_findings ADD COLUMN IF NOT EXISTS line_no INTEGER;
ALTER TABLE review_findings ADD COLUMN IF NOT EXISTS anchor_line INTEGER;
ALTER TABLE review_findings ADD COLUMN IF NOT EXISTS comment_kind TEXT;
ALTER TABLE review_findings ADD COLUMN IF NOT EXISTS comment_id BIGINT;
ALTER TABLE review_findings ADD COLUMN IF NOT EXISTS comment_url TEXT;
ALTER TABLE review_findings ADD COLUMN IF NOT EXISTS comment_body TEXT;
ALTER TABLE review_findings ADD COLUMN IF NOT EXISTS status_actor TEXT;
ALTER TABLE review_findings ADD COLUMN IF NOT EXISTS status_updated_at TIMESTAMPTZ;
CREATE UNIQUE INDEX IF NOT EXISTS review_findings_comment_idx
  ON review_findings(comment_kind, comment_id) WHERE comment_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS credential_audit_owner_idx ON credential_audit(owner, created_at DESC);
"""

def connect():
    conn = psycopg.connect(settings.database_url)
    register_vector(conn)
    return conn

def init_db():
    with psycopg.connect(settings.database_url) as conn:
        conn.execute(SCHEMA)
        conn.execute(MIGRATIONS)
        # Backfill catalog rows for repositories indexed before the dashboard existed.
        conn.execute("""INSERT INTO repository_catalog
            (repo_full_name,primary_language,description,latest_sha,indexed_at,file_count,chunk_count,symbol_count,edge_count)
            SELECT DISTINCT ON (s.repo_full_name) s.repo_full_name,'Unknown',
                'Application profile will be enriched after the next repository push.',s.commit_sha,s.indexed_at,
                s.file_count,s.chunk_count,
                (SELECT count(*) FROM code_symbols cs WHERE cs.repo_full_name=s.repo_full_name AND cs.commit_sha=s.commit_sha),
                (SELECT count(*) FROM code_edges ce WHERE ce.repo_full_name=s.repo_full_name AND ce.commit_sha=s.commit_sha)
            FROM repository_snapshots s ORDER BY s.repo_full_name,s.indexed_at DESC
            ON CONFLICT (repo_full_name) DO NOTHING""")
        conn.commit()
