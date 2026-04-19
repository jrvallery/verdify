"""Image observation schema — Gemini-vision output over camera snapshots.

Each row ties a camera capture to:
- A structured JSONB analysis (crops detected, environmental notes, actions)
- A pgvector embedding (3072-dim from gemini-embedding-2)
- Processing metadata (model, tokens, latency)

The embedding is declared as `list[float]` for portability; consumers that
want vector-search operations talk to pgvector directly. Sprint 23+ will add
a proper pgvector-aware shape and similarity helpers.
"""

from __future__ import annotations

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field


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
    # pgvector column — declared as permissive list[float]; length 3072 in practice.
    # Full vector-typed shape + pg-side operators: Sprint 23 pgvector support.
    embedding: list[float] | None = None
    greenhouse_id: str = "vallery"
