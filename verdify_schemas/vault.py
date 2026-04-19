"""Vault markdown frontmatter schemas.

Every auto-generated markdown page in the Obsidian vault has typed
frontmatter. Renderers build a Pydantic model, dump to YAML, and write
the `.md` file. A renderer that forgets a field or emits a wrong type
fails at the schema boundary instead of shipping broken YAML to the
Quartz build.

Writers covered:
- vault-daily-writer.py          → DailyVaultFrontmatter      (/daily/YYYY-MM-DD.md)
- vault-crop-writer.py           → CropVaultFrontmatter       (/crops/{slug}.md)
- generate-daily-plan.py         → DailyPlanVaultFrontmatter  (/website/plans/YYYY-MM-DD.md)
- generate-forecast-page.py      → ForecastVaultFrontmatter   (/website/forecast/index.md)
- generate-lessons-page.py       → LessonsVaultFrontmatter    (/website/intelligence/lessons.md)
"""

from __future__ import annotations

from datetime import date as DateType

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field


class VaultFrontmatter(BaseModel):
    """Common base — every vault page has a title and tags."""

    model_config = ConfigDict(extra="allow", str_strip_whitespace=True)

    tags: list[str] = Field(default_factory=list)


class DailyVaultFrontmatter(VaultFrontmatter):
    """/daily/YYYY-MM-DD.md — vault-daily-writer.py output.

    Populated from daily_summary DB row. Stable key names are relied on by
    Obsidian dataview queries; don't rename without auditing the vault.
    """

    date: DateType
    temp_avg: float | None = None
    vpd_avg: float | None = None
    dli: float | None = None
    cost_total: str | None = None  # Rendered as "$1.61" string for Obsidian display
    water_gal: int | None = None
    stress_vpd_h: float | None = None
    stress_heat_h: float | None = None


class CropVaultFrontmatter(VaultFrontmatter):
    """/crops/{slug}.md — vault-crop-writer.py output."""

    name: str = Field(..., min_length=1)
    variety: str | None = None
    position: str
    zone: str
    stage: str
    planted_date: DateType


class DailyPlanVaultFrontmatter(VaultFrontmatter):
    """/website/plans/YYYY-MM-DD.md — generate-daily-plan.py output.

    Combines daily_summary + plan_journal + active setpoints into one page.
    The nested sub-dicts (climate, stress, cost, water, equipment, setpoints,
    experiment) are Obsidian-dataview-friendly scalar blocks — no deep nesting.
    """

    title: str = Field(..., min_length=1)
    date: DateType
    type: str = "plan"

    latest_cycle: str | None = None
    latest_plan_id: str | None = None
    plan_count: int | None = Field(default=None, ge=0)

    # Sub-blocks — free-form dicts of scalar KPIs. Keeping these as dict
    # lets the renderer dump whatever daily_summary produces without a
    # second-layer model that also has to stay in sync with the DB.
    climate: dict = Field(default_factory=dict)
    stress: dict = Field(default_factory=dict)
    cost: dict = Field(default_factory=dict)
    water: dict = Field(default_factory=dict)
    equipment: dict = Field(default_factory=dict)
    setpoints: dict = Field(default_factory=dict)
    experiment: dict | None = None


class ForecastVaultFrontmatter(VaultFrontmatter):
    """/website/forecast/index.md — generate-forecast-page.py output."""

    title: str = "Forecast"
    date: DateType
    last_updated: AwareDatetime | str  # Renderer can emit ISO string OR datetime


class LessonsVaultFrontmatter(VaultFrontmatter):
    """/website/intelligence/lessons.md — generate-lessons-page.py output."""

    title: str = "Lessons Learned"
    date: DateType
