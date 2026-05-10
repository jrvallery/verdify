-- 112-embeddings-unified.sql
-- =============================================================================
-- Iris loop overhaul — Phase 3: vectorized retrieval over four corpora.
--
-- The 30-day baseline showed Iris sees only the top-10 active lessons by
-- confidence + validation count (50 active total). Codex flagged this as a
-- fragile top-K ordering — if the dominant condition tomorrow isn't covered
-- by today's top 10, Iris flies blind. Site content and the planner playbook
-- are not retrievable at all today (site_content table exists but is empty).
--
-- This migration:
--   1. Creates verdify_embeddings — single table indexing four corpora
--      (lesson, plan, site_doc, playbook) by content + 3072-dim embedding.
--   2. Creates playbook_content — store chunked planner playbook + skills.
--   3. Fixes the latent dim mismatch from migration 074 (image_observations
--      live schema is vector(3072) but the original 074 index was 768-dim;
--      the index never got created on this DB, so we add it at the right
--      dim here).
--   4. Adds fn_search_embeddings() for top-K cosine similarity retrieval.
-- =============================================================================

BEGIN;

-- pgvector should already be enabled by migration 074; idempotent guard.
CREATE EXTENSION IF NOT EXISTS vector;

-- -----------------------------------------------------------------------------
-- 1. verdify_embeddings — unified embedding store
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS verdify_embeddings (
    id           BIGSERIAL PRIMARY KEY,
    source_type  TEXT NOT NULL
                 CHECK (source_type IN ('lesson','plan','site_doc','playbook')),
    source_id    TEXT NOT NULL,
    chunk_idx    INTEGER NOT NULL DEFAULT 0,
    content      TEXT NOT NULL,
    content_hash TEXT NOT NULL,            -- sha256(content); skips re-embed
    embedding    vector(3072) NOT NULL,    -- OpenAI text-embedding-3-large
    metadata     JSONB,                    -- { confidence, planner_score, ... }
    embedded_at  TIMESTAMPTZ DEFAULT now(),
    UNIQUE (source_type, source_id, chunk_idx)
);

-- ivfflat doesn't support 3072 in older pgvector builds; use hnsw if available
-- but fall back gracefully. Since we don't know the pgvector version a priori,
-- create an index using cosine ops with hnsw (works in pgvector ≥0.5.0).
DO $$
BEGIN
    -- Try hnsw first (best for 3072-dim)
    BEGIN
        EXECUTE 'CREATE INDEX IF NOT EXISTS verdify_embeddings_hnsw
                 ON verdify_embeddings USING hnsw (embedding vector_cosine_ops)
                 WITH (m = 16, ef_construction = 64)';
    EXCEPTION WHEN OTHERS THEN
        -- Older pgvector: ivfflat works up to 2000 dims, so this will likely
        -- fail for 3072. Leave the table without a vector index and rely on
        -- sequential scan; embedding count is bounded (~hundreds of lessons,
        -- thousands of plan + site chunks), so this is acceptable until the
        -- pgvector version is bumped.
        RAISE NOTICE 'hnsw index creation failed; embeddings will use seq scan';
    END;
END$$;

CREATE INDEX IF NOT EXISTS verdify_embeddings_source_type_idx
    ON verdify_embeddings (source_type);
CREATE INDEX IF NOT EXISTS verdify_embeddings_source_id_idx
    ON verdify_embeddings (source_type, source_id);

COMMENT ON TABLE verdify_embeddings IS
  'Unified embedding store for lessons, plans, site docs, and the planner '
  'playbook. Embedded with OpenAI text-embedding-3-large (3072-dim). '
  'Populated by scripts/embed-corpora.py.';

-- -----------------------------------------------------------------------------
-- 2. playbook_content — chunked planner playbook + skills
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS playbook_content (
    id           BIGSERIAL PRIMARY KEY,
    source_path  TEXT NOT NULL,            -- e.g. 'docs/planner/greenhouse-playbook.md'
    chunk_idx    INTEGER NOT NULL,
    heading      TEXT,                     -- nearest preceding markdown heading
    content      TEXT NOT NULL,
    content_hash TEXT NOT NULL,
    updated_at   TIMESTAMPTZ DEFAULT now(),
    UNIQUE (source_path, chunk_idx)
);

CREATE INDEX IF NOT EXISTS playbook_content_source_idx
    ON playbook_content (source_path);

COMMENT ON TABLE playbook_content IS
  'Chunked rows from docs/planner/greenhouse-playbook.md + agent-host '
  'skills/greenhouse-planner.md. Source of truth for the "playbook" source_type '
  'in verdify_embeddings.';

-- -----------------------------------------------------------------------------
-- 3. Fix the latent migration 074 dim mismatch.
--    Live image_observations.embedding is vector(3072) (manually altered),
--    but the original 074 migration created an ivfflat index at 768-dim that
--    never landed on this DB. Add the proper 3072-dim index here so the
--    fn_similar_observations() function actually has an index to use.
-- -----------------------------------------------------------------------------
DO $$
BEGIN
    BEGIN
        EXECUTE 'CREATE INDEX IF NOT EXISTS idx_imgobs_embedding_hnsw
                 ON image_observations USING hnsw (embedding vector_cosine_ops)
                 WITH (m = 16, ef_construction = 64)';
    EXCEPTION WHEN OTHERS THEN
        RAISE NOTICE 'image_observations hnsw index creation failed; relying on seq scan';
    END;
END$$;

-- -----------------------------------------------------------------------------
-- 4. fn_search_embeddings(query_embedding, top_k, source_types[]) → matches
--    Returns top-K rows from verdify_embeddings filtered by source_type and
--    ordered by cosine similarity to the input embedding.
-- -----------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION fn_search_embeddings(
    query_embedding vector(3072),
    p_top_k         INTEGER DEFAULT 10,
    p_source_types  TEXT[]  DEFAULT ARRAY['lesson','plan','site_doc','playbook']
)
RETURNS TABLE (
    source_type TEXT,
    source_id   TEXT,
    chunk_idx   INTEGER,
    content     TEXT,
    metadata    JSONB,
    distance    FLOAT
)
LANGUAGE plpgsql
STABLE
AS $$
BEGIN
    RETURN QUERY
    SELECT e.source_type, e.source_id, e.chunk_idx, e.content, e.metadata,
           (e.embedding <=> query_embedding)::float AS distance
      FROM verdify_embeddings e
     WHERE e.source_type = ANY(p_source_types)
     ORDER BY e.embedding <=> query_embedding
     LIMIT p_top_k;
END;
$$;

COMMENT ON FUNCTION fn_search_embeddings(vector, INTEGER, TEXT[]) IS
  'Top-K cosine-similarity retrieval over verdify_embeddings. Caller is '
  'responsible for embedding the query string (OpenAI text-embedding-3-large) '
  'before passing it to this function.';

COMMIT;
