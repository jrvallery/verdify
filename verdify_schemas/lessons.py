"""Planner lessons schemas.

- PlannerLesson: full row shape (planner_lessons table).
- LessonAction: MCP `lessons_manage` tool input envelope (replaces free-form
  `action: str, data: str` pair).
"""

from __future__ import annotations

from typing import Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field

LessonConfidence = Literal["low", "medium", "high"]


class LessonCreate(BaseModel):
    """MCP lessons_manage.create data payload."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    category: str = Field(..., min_length=1, max_length=100)
    condition: str = Field(..., min_length=1, max_length=500)
    lesson: str = Field(..., min_length=1, max_length=2000)
    confidence: LessonConfidence = "low"


class LessonUpdate(BaseModel):
    """MCP lessons_manage.update data payload — selective patch."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    category: str | None = Field(default=None, max_length=100)
    condition: str | None = Field(default=None, max_length=500)
    lesson: str | None = Field(default=None, max_length=2000)
    confidence: LessonConfidence | None = None


class LessonValidate(BaseModel):
    """MCP lessons_manage.validate data payload — optional confidence upgrade."""

    model_config = ConfigDict(extra="forbid")

    confidence: LessonConfidence | None = None


LessonActionKind = Literal["list", "create", "update", "deactivate", "validate"]


class LessonAction(BaseModel):
    """MCP `lessons_manage` tool input envelope."""

    model_config = ConfigDict(extra="forbid")

    action: LessonActionKind
    lesson_id: int | None = None
    data: LessonCreate | LessonUpdate | LessonValidate | None = None


class PlannerLesson(BaseModel):
    """planner_lessons table row — full persisted shape."""

    model_config = ConfigDict(extra="ignore")

    id: int | None = None
    created_at: AwareDatetime | None = None
    category: str
    condition: str
    lesson: str
    confidence: LessonConfidence = "low"
    times_validated: int = Field(default=1, ge=0)
    last_validated: AwareDatetime | None = None
    source_plan_ids: list[str] | None = None
    superseded_by: int | None = None
    is_active: bool = True
    greenhouse_id: str = "vallery"
