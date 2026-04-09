-- 074-pgvector-embeddings.sql
-- Add vector embeddings to image_observations for semantic similarity search

ALTER TABLE image_observations ADD COLUMN IF NOT EXISTS embedding vector(768);

CREATE INDEX IF NOT EXISTS idx_imgobs_embedding ON image_observations
    USING ivfflat (embedding vector_cosine_ops) WITH (lists = 10);

-- Function: find similar observations by cosine distance
CREATE OR REPLACE FUNCTION fn_similar_observations(target_id INT, max_results INT DEFAULT 5)
RETURNS TABLE (
    id INT, ts TIMESTAMPTZ, camera TEXT, zone TEXT, confidence FLOAT,
    crops_observed JSONB, distance FLOAT
) AS $$
BEGIN
    RETURN QUERY
    SELECT io.id, io.ts, io.camera, io.zone, io.confidence,
        io.crops_observed, (io.embedding <=> (SELECT embedding FROM image_observations WHERE image_observations.id = target_id)) AS distance
    FROM image_observations io
    WHERE io.embedding IS NOT NULL
      AND io.id != target_id
    ORDER BY io.embedding <=> (SELECT embedding FROM image_observations WHERE image_observations.id = target_id)
    LIMIT max_results;
END;
$$ LANGUAGE plpgsql;
