"""
Configuration materialization and ETag generation for Project Verdify.

This module implements the deterministic config builder that gathers all greenhouse
configuration data, serializes it consistently, and generates strong ETags for
caching and change detection.
"""

import hashlib
import json
import uuid
from datetime import datetime, timezone
from typing import Any

from sqlmodel import Session, select

from app.models import (
    Actuator,
    Controller,
    ControllerButton,
    FanGroup,
    FanGroupMember,
    Greenhouse,
    Sensor,
    SensorZoneMap,
    StateMachineRow,
    Zone,
)


class ConfigBuilder:
    """Deterministic configuration builder with ETag support."""

    def __init__(self, session: Session):
        self.session = session

    def build_config(
        self, greenhouse_id: uuid.UUID, version: int | None = None
    ) -> dict[str, Any]:
        """
        Build complete configuration payload for a greenhouse.

        Args:
            greenhouse_id: Target greenhouse UUID
            version: Override version number (if None, auto-increments)

        Returns:
            Complete configuration payload matching ConfigPayload schema

        Raises:
            ValueError: If greenhouse not found or validation fails
        """
        # 1. Load greenhouse
        greenhouse = self._load_greenhouse(greenhouse_id)

        # 2. Load all related entities
        controllers = self._load_controllers(greenhouse_id)
        sensors = self._load_sensors(greenhouse_id)
        actuators = self._load_actuators(greenhouse_id)
        zones = self._load_zones(greenhouse_id)
        fan_groups = self._load_fan_groups(greenhouse_id)
        buttons = self._load_buttons(greenhouse_id)
        state_rules = self._load_state_rules(greenhouse_id)

        # 3. Validate configuration
        self._validate_config(greenhouse, controllers, sensors, actuators, state_rules)

        # 4. Determine version
        if version is None:
            version = self._get_next_version(greenhouse_id)

        # 5. Build canonical payload
        payload = {
            "version": version,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "greenhouse": self._serialize_greenhouse(greenhouse),
            "baselines": self._serialize_baselines(greenhouse),
            "rails": self._serialize_rails(greenhouse),
            "controllers": self._serialize_controllers(controllers),
            "sensors": self._serialize_sensors(sensors, zones),
            "actuators": self._serialize_actuators(actuators, zones),
            "fan_groups": self._serialize_fan_groups(fan_groups),
            "buttons": self._serialize_buttons(buttons),
            "state_rules": self._serialize_state_rules(state_rules),
        }

        return payload

    def generate_etag(self, payload: dict[str, Any]) -> str:
        """
        Generate strong ETag from canonical payload.

        Args:
            payload: Configuration payload

        Returns:
            Strong ETag in format "config:v<version>:<sha8>"
        """
        # Create canonical JSON without generated_at for stable hashing
        canonical_payload = payload.copy()
        canonical_payload.pop("generated_at", None)

        # Sort keys for deterministic serialization
        canonical_json = json.dumps(
            canonical_payload, sort_keys=True, separators=(",", ":")
        )

        # Generate SHA-256 hash
        hash_bytes = hashlib.sha256(canonical_json.encode("utf-8")).hexdigest()
        sha8 = hash_bytes[:8]

        version = payload["version"]
        return f"config:v{version}:{sha8}"

    def _load_greenhouse(self, greenhouse_id: uuid.UUID) -> Greenhouse:
        """Load greenhouse by ID."""
        statement = select(Greenhouse).where(Greenhouse.id == greenhouse_id)
        greenhouse = self.session.exec(statement).first()
        if not greenhouse:
            raise ValueError(f"Greenhouse {greenhouse_id} not found")
        return greenhouse

    def _load_controllers(self, greenhouse_id: uuid.UUID) -> list[Controller]:
        """Load all controllers for greenhouse."""
        statement = select(Controller).where(Controller.greenhouse_id == greenhouse_id)
        return list(self.session.exec(statement).all())

    def _load_sensors(self, greenhouse_id: uuid.UUID) -> list[Sensor]:
        """Load all sensors for greenhouse."""
        statement = (
            select(Sensor)
            .join(Controller)
            .where(Controller.greenhouse_id == greenhouse_id)
        )
        return list(self.session.exec(statement).all())

    def _load_actuators(self, greenhouse_id: uuid.UUID) -> list[Actuator]:
        """Load all actuators for greenhouse."""
        statement = (
            select(Actuator)
            .join(Controller)
            .where(Controller.greenhouse_id == greenhouse_id)
        )
        return list(self.session.exec(statement).all())

    def _load_zones(self, greenhouse_id: uuid.UUID) -> list[Zone]:
        """Load all zones for greenhouse."""
        statement = select(Zone).where(Zone.greenhouse_id == greenhouse_id)
        return list(self.session.exec(statement).all())

    def _load_fan_groups(self, greenhouse_id: uuid.UUID) -> list[FanGroup]:
        """Load all fan groups for greenhouse."""
        statement = (
            select(FanGroup)
            .join(Controller)
            .where(Controller.greenhouse_id == greenhouse_id)
        )
        return list(self.session.exec(statement).all())

    def _load_buttons(self, greenhouse_id: uuid.UUID) -> list[ControllerButton]:
        """Load all controller buttons for greenhouse."""
        statement = (
            select(ControllerButton)
            .join(Controller)
            .where(Controller.greenhouse_id == greenhouse_id)
        )
        return list(self.session.exec(statement).all())

    def _load_state_rules(self, greenhouse_id: uuid.UUID) -> list[StateMachineRow]:
        """Load all state machine rules for greenhouse."""
        statement = select(StateMachineRow).where(
            StateMachineRow.greenhouse_id == greenhouse_id
        )
        return list(self.session.exec(statement).all())

    def _get_next_version(self, greenhouse_id: uuid.UUID) -> int:
        """Get next version number for greenhouse."""
        from app.models import ConfigSnapshot

        statement = (
            select(ConfigSnapshot.version)
            .where(ConfigSnapshot.greenhouse_id == greenhouse_id)
            .order_by(ConfigSnapshot.version.desc())
            .limit(1)
        )
        latest_version = self.session.exec(statement).first()
        return (latest_version + 1) if latest_version else 1

    def _validate_config(
        self,
        greenhouse: Greenhouse,
        controllers: list[Controller],
        sensors: list[Sensor],
        actuators: list[Actuator],
        state_rules: list[StateMachineRow],
    ) -> None:
        """
        Validate configuration completeness and constraints.

        Raises:
            ValueError: If validation fails
        """
        errors = []

        # Check climate controller singleton
        climate_controllers = [c for c in controllers if c.is_climate_controller]
        if len(climate_controllers) != 1:
            errors.append(
                f"Expected exactly 1 climate controller, got {len(climate_controllers)}"
            )

        # Check state machine completeness (49 grid cells + 1 fallback)
        grid_rules = [r for r in state_rules if not r.is_fallback]
        fallback_rules = [r for r in state_rules if r.is_fallback]

        if len(grid_rules) != 49:
            errors.append(f"Expected 49 grid state rules, got {len(grid_rules)}")

        if len(fallback_rules) != 1:
            errors.append(
                f"Expected exactly 1 fallback rule, got {len(fallback_rules)}"
            )

        # Check all temp/humi stage combinations are covered
        expected_stages = set()
        for temp_stage in range(-3, 4):
            for humi_stage in range(-3, 4):
                expected_stages.add((temp_stage, humi_stage))

        actual_stages = set((r.temp_stage, r.humi_stage) for r in grid_rules)
        missing_stages = expected_stages - actual_stages
        if missing_stages:
            errors.append(f"Missing state rule combinations: {missing_stages}")

        if errors:
            raise ValueError("Configuration validation failed: " + "; ".join(errors))

    def _serialize_greenhouse(self, greenhouse: Greenhouse) -> dict[str, Any]:
        """Serialize greenhouse for config payload."""
        return {
            "id": str(greenhouse.id),
            "title": greenhouse.name,  # Map name -> title for API compatibility
            "min_temp_c": greenhouse.min_temp_c,
            "max_temp_c": greenhouse.max_temp_c,
            "min_vpd_kpa": greenhouse.min_vpd_kpa,
            "max_vpd_kpa": greenhouse.max_vpd_kpa,
            "enthalpy_open_kjkg": greenhouse.enthalpy_open_kjkg,
            "enthalpy_close_kjkg": greenhouse.enthalpy_close_kjkg,
            "site_pressure_hpa": greenhouse.site_pressure_hpa,
        }

    def _serialize_baselines(self, greenhouse: Greenhouse) -> dict[str, Any]:
        """Serialize baseline thresholds from greenhouse."""
        # Use sensible defaults since baseline fields don't exist yet in the model
        # TODO: Add baseline_temp_stages and baseline_humi_stages to Greenhouse model
        return {
            "temp_thresholds": {
                "minus3": 15.0,
                "minus2": 17.0,
                "minus1": 19.0,
                "zero": 21.0,
                "plus1": 23.0,
                "plus2": 25.0,
                "plus3": 27.0,
            },
            "vpd_thresholds": {
                "minus3": 0.4,
                "minus2": 0.6,
                "minus1": 0.8,
                "zero": 1.0,
                "plus1": 1.2,
                "plus2": 1.4,
                "plus3": 1.6,
            },
            "hysteresis": {"temp_c": 0.5, "vpd_kpa": 0.1},
        }

    def _serialize_rails(self, greenhouse: Greenhouse) -> dict[str, Any]:
        """Serialize safety rails from greenhouse."""
        return {
            "min_temp_c": greenhouse.min_temp_c,
            "max_temp_c": greenhouse.max_temp_c,
            "min_vpd_kpa": greenhouse.min_vpd_kpa,
            "max_vpd_kpa": greenhouse.max_vpd_kpa,
        }

    def _serialize_controllers(
        self, controllers: list[Controller]
    ) -> list[dict[str, Any]]:
        """Serialize controllers, sorted by device_name for determinism."""
        sorted_controllers = sorted(controllers, key=lambda c: c.device_name or "")
        return [
            {
                "controller_id": str(c.id),
                "device_name": c.device_name,
                "is_climate_controller": c.is_climate_controller,
            }
            for c in sorted_controllers
        ]

    def _serialize_sensors(
        self, sensors: list[Sensor], zones: list[Zone]
    ) -> list[dict[str, Any]]:
        """Serialize sensors with zone mappings, sorted by ID for determinism."""
        zone_map = {z.id: z for z in zones}

        # Load sensor-zone mappings
        sensor_zone_maps = {}
        for sensor in sensors:
            statement = select(SensorZoneMap).where(
                SensorZoneMap.sensor_id == sensor.id
            )
            mappings = self.session.exec(statement).all()
            sensor_zone_maps[sensor.id] = [m.zone_id for m in mappings]

        sorted_sensors = sorted(sensors, key=lambda s: str(s.id))
        return [
            {
                "sensor_id": str(s.id),
                "controller_id": str(s.controller_id),
                "name": s.name,
                "kind": s.kind,
                "scope": s.scope,
                "include_in_climate_loop": s.include_in_climate_loop,
                "zone_ids": [str(zid) for zid in sensor_zone_maps.get(s.id, [])],
                "poll_interval_s": s.poll_interval_s or 60,
            }
            for s in sorted_sensors
        ]

    def _serialize_actuators(
        self, actuators: list[Actuator], zones: list[Zone]
    ) -> list[dict[str, Any]]:
        """Serialize actuators, sorted by ID for determinism."""
        sorted_actuators = sorted(actuators, key=lambda a: str(a.id))
        return [
            {
                "actuator_id": str(a.id),
                "controller_id": str(a.controller_id),
                "name": a.name,
                "kind": a.kind,
                "relay_channel": a.relay_channel,
                "min_on_ms": a.min_on_ms or 1000,
                "min_off_ms": a.min_off_ms or 1000,
                "zone_id": str(a.zone_id) if a.zone_id else None,
            }
            for a in sorted_actuators
        ]

    def _serialize_fan_groups(self, fan_groups: list[FanGroup]) -> list[dict[str, Any]]:
        """Serialize fan groups with members, sorted by ID for determinism."""
        result = []

        for fan_group in sorted(fan_groups, key=lambda fg: str(fg.id)):
            # Load fan group members
            statement = select(FanGroupMember).where(
                FanGroupMember.fan_group_id == fan_group.id
            )
            members = self.session.exec(statement).all()

            result.append(
                {
                    "fan_group_id": str(fan_group.id),
                    "controller_id": str(fan_group.controller_id),
                    "name": fan_group.name,
                    "members": [
                        {"actuator_id": str(m.actuator_id)}
                        for m in sorted(members, key=lambda m: str(m.actuator_id))
                    ],
                }
            )

        return result

    def _serialize_buttons(
        self, buttons: list[ControllerButton]
    ) -> list[dict[str, Any]]:
        """Serialize controller buttons, sorted by ID for determinism."""
        sorted_buttons = sorted(buttons, key=lambda b: str(b.id))
        return [
            {
                "button_id": str(b.id),
                "controller_id": str(b.controller_id),
                "button_kind": b.button_kind,
                "stage_override": b.stage_override,
                "timeout_s": b.timeout_s,
            }
            for b in sorted_buttons
        ]

    def _serialize_state_rules(
        self, state_rules: list[StateMachineRow]
    ) -> dict[str, Any]:
        """Serialize state machine rules as grid + fallback."""
        grid_rules = [r for r in state_rules if not r.is_fallback]
        fallback_rules = [r for r in state_rules if r.is_fallback]

        # Sort grid rules by temp_stage, then humi_stage for determinism
        sorted_grid = sorted(grid_rules, key=lambda r: (r.temp_stage, r.humi_stage))

        grid = []
        for rule in sorted_grid:
            grid.append(
                {
                    "temp_stage": rule.temp_stage,
                    "humi_stage": rule.humi_stage,
                    "must_on_actuators": sorted(
                        str(aid) for aid in (rule.must_on_actuators or [])
                    ),
                    "must_off_actuators": sorted(
                        str(aid) for aid in (rule.must_off_actuators or [])
                    ),
                    "must_on_fan_groups": [
                        {"fan_group_id": str(fan_group_id), "on_count": on_count}
                        for fan_group_id, on_count in sorted(
                            (rule.fan_on_counts or {}).items()
                        )
                    ],
                }
            )

        # Fallback rule
        fallback = None
        if fallback_rules:
            rule = fallback_rules[0]  # Should be exactly one
            fallback = {
                "is_fallback": True,
                "must_on_actuators": sorted(
                    str(aid) for aid in (rule.must_on_actuators or [])
                ),
                "must_off_actuators": sorted(
                    str(aid) for aid in (rule.must_off_actuators or [])
                ),
                "must_on_fan_groups": [
                    {"fan_group_id": str(fan_group_id), "on_count": on_count}
                    for fan_group_id, on_count in sorted(
                        (rule.fan_on_counts or {}).items()
                    )
                ],
            }

        return {"grid": grid, "fallback": fallback}
