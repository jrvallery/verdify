"""Phase 5 — vault markdown frontmatter schemas."""

from __future__ import annotations

from datetime import UTC, date, datetime

import pytest
from pydantic import ValidationError

from verdify_schemas.vault import (
    CropVaultFrontmatter,
    DailyPlanVaultFrontmatter,
    DailyVaultFrontmatter,
    ForecastVaultFrontmatter,
    LessonsVaultFrontmatter,
)

NOW = datetime(2026, 4, 19, 1, 0, tzinfo=UTC)


class TestDailyVault:
    def test_valid(self):
        f = DailyVaultFrontmatter(
            date=date(2026, 4, 17),
            tags=["daily", "greenhouse"],
            temp_avg=64.4,
            vpd_avg=0.72,
            dli=4.0,
            cost_total="$7.82",
            water_gal=344,
            stress_vpd_h=0.0,
            stress_heat_h=0.0,
        )
        assert f.water_gal == 344

    def test_minimal(self):
        f = DailyVaultFrontmatter(date=date(2026, 4, 17))
        assert f.tags == []


class TestCropVault:
    def test_valid(self):
        f = CropVaultFrontmatter(
            name="Tomato Sungold",
            position="hydro-03",
            zone="center",
            stage="vegetative",
            planted_date=date(2026, 4, 1),
            tags=["crop", "center", "hydro"],
        )
        assert f.stage == "vegetative"

    def test_rejects_empty_name(self):
        with pytest.raises(ValidationError):
            CropVaultFrontmatter(
                name="",
                position="hydro-03",
                zone="center",
                stage="seed",
                planted_date=date(2026, 4, 1),
            )


class TestDailyPlanVault:
    def test_valid_with_nested_blocks(self):
        f = DailyPlanVaultFrontmatter(
            title="April 18, 2026",
            date=date(2026, 4, 18),
            tags=["daily-plan"],
            latest_cycle="morning",
            latest_plan_id="iris-20260418-0618",
            plan_count=2,
            climate={"temp_min_f": 48.0, "temp_max_f": 82.0, "vpd_avg_kpa": 0.72},
            stress={"heat_hours": 0.0, "vpd_high_hours": 0.2},
            cost={"electric": 2.3, "gas": 1.1, "total": 3.4},
            water={"total_gal": 344, "mister_gal": 120},
            equipment={"fan1_min": 60, "mister_south_h": 0.5},
        )
        assert f.plan_count == 2

    def test_rejects_empty_title(self):
        with pytest.raises(ValidationError):
            DailyPlanVaultFrontmatter(title="", date=date(2026, 4, 18))

    def test_rejects_negative_plan_count(self):
        with pytest.raises(ValidationError):
            DailyPlanVaultFrontmatter(title="x", date=date(2026, 4, 18), plan_count=-1)


class TestForecastVault:
    def test_valid_datetime(self):
        f = ForecastVaultFrontmatter(date=date(2026, 4, 19), last_updated=NOW)
        assert f.title == "Forecast"

    def test_valid_iso_string(self):
        f = ForecastVaultFrontmatter(date=date(2026, 4, 19), last_updated="2026-04-19T00:00:00+00:00")
        assert isinstance(f.last_updated, str)


class TestLessonsVault:
    def test_default_title(self):
        f = LessonsVaultFrontmatter(date=date(2026, 4, 19))
        assert f.title == "Lessons Learned"
