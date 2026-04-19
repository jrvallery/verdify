"""Image observation schema — Gemini-vision output over camera snapshots.

Each row ties a camera capture to:
- A structured JSONB analysis (crops detected, environmental notes, actions)
- A pgvector embedding (3072-dim from gemini-embedding-2)
- Processing metadata (model, tokens, latency)

`embedding` is dimension-locked: any list whose length isn't `EMBEDDING_DIM`
(3072) gets rejected at the Pydantic boundary. Catches the class of bug
where the embedding model is swapped (e.g. to a 768-dim variant) but the
DB column still expects 3072 — currently that crashes inside asyncpg with
a cryptic vector-mismatch error; with this guard it fails at construction
with a clear message.
"""

from __future__ import annotations

from typing import Annotated

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field

# pgvector column dimension — gemini-embedding-2 emits 3072.
# If you migrate to a different model, update this AND the DB column type
# (`ALTER TABLE image_observations ALTER COLUMN embedding TYPE vector(N)`).
EMBEDDING_DIM = 3072

Embedding = Annotated[list[float], Field(min_length=EMBEDDING_DIM, max_length=EMBEDDING_DIM)]


class ImageObservation(BaseModel):
    """image_observations hypertable row — one per analyzed camera snapshot."""

    model_config = ConfigDict(extra="ignore")

    id: int | None = None
    ts: AwareDatetime
    camera: str = Field(..., min_length=1)
    zone: str = Field(..., min_length=1)
    image_path: str = Field(..., min_length=1)
    model: str = "gemini-2.0-flash"
    raw_response: dict | None = None
    crops_observed: list | dict | None = None
    environment_notes: str | None = None
    recommended_actions: list[str] | None = None
    processing_ms: int | None = Field(default=None, ge=0)
    tokens_used: int | None = Field(default=None, ge=0)
    confidence: float | None = Field(default=None, ge=0, le=1)
    embedding: Embedding | None = None
    greenhouse_id: str = "vallery"
