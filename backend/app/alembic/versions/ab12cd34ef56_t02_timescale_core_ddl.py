"""t02_timescale_core_ddl

Revision ID: ab12cd34ef56
Revises: 1a2b3c4d5e6f
Create Date: 2025-08-21 00:00:00.000000

This migration introduces TimescaleDB extensions, meta lookup tables for
sensor/actuator kinds, and core time-series hypertables used by telemetry.

It follows requirements/DATABASE.md (v2.0), sections 3 and 8.
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "ab12cd34ef56"
down_revision = "1a2b3c4d5e6f"
branch_labels = None
depends_on = None


def _create_extensions() -> None:
    # Safe to run multiple times
    op.execute("CREATE EXTENSION IF NOT EXISTS timescaledb")
    op.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto")


def _create_meta_tables() -> None:
    op.create_table(
        "sensor_kind_meta",
        sa.Column("kind", sa.Text(), primary_key=True, nullable=False),
        sa.Column("value_type", sa.Text(), nullable=False),
        sa.Column("unit", sa.Text(), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
    )

    op.create_table(
        "actuator_kind_meta",
        sa.Column("kind", sa.Text(), primary_key=True, nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
    )

    # Seed values (idempotent)
    op.execute(
        """
        INSERT INTO sensor_kind_meta(kind, value_type, unit, notes) VALUES
          ('temperature','float','°C','ambient/surface/soil'),
          ('humidity','float','%','relative humidity'),
          ('vpd','float','kPa','vapor pressure deficit'),
          ('co2','float','ppm','CO₂ concentration'),
          ('light','float','lx','photometric lux'),
          ('ppfd','float','µmol/m²/s','photosynthetic photon flux density'),
          ('soil_moisture','float','m³/m³','volumetric water content'),
          ('water_flow','float','L/min','instantaneous flow'),
          ('water_total','float','L','cumulative volume'),
          ('air_pressure','float','hPa','barometric pressure'),
          ('dew_point','float','°C','derived'),
          ('absolute_humidity','float','g/m³','derived'),
          ('enthalpy_delta','float','kJ/kg','derived in-out'),
          ('kwh','float','kWh','energy consumption'),
          ('power','float','kW','instantaneous power'),
          ('gas_consumption','float','m³','fuel usage'),
          ('wind_speed','float','m/s','external'),
          ('rainfall','float','mm','external')
        ON CONFLICT (kind) DO NOTHING;
        """
    )

    op.execute(
        """
        INSERT INTO actuator_kind_meta(kind, notes) VALUES
          ('fan','ventilation'),
          ('heater','heating'),
          ('vent','vent opening'),
          ('fogger','humidifier'),
          ('irrigation_valve','water valve'),
          ('fertilizer_valve','fert valve'),
          ('pump','general pump'),
          ('light','grow light')
        ON CONFLICT (kind) DO NOTHING;
        """
    )


def _create_timeseries_tables() -> None:
    # 8.1 sensor_reading
    op.create_table(
        "sensor_reading",
        sa.Column("time", sa.DateTime(timezone=True), nullable=False),
        sa.Column("greenhouse_id", sa.Uuid(), nullable=False),
        sa.Column("controller_id", sa.Uuid(), nullable=False),
        sa.Column("sensor_id", sa.Uuid(), nullable=False),
        sa.Column("kind", sa.Text(), nullable=False),
        sa.Column("value", sa.Float(), nullable=False),
        sa.ForeignKeyConstraint(["greenhouse_id"], ["greenhouse.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["controller_id"], ["controller.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["sensor_id"], ["sensor.id"], ondelete="CASCADE"),
    )
    # Convert to hypertable
    op.execute(
        "SELECT create_hypertable('sensor_reading', 'time', if_not_exists => TRUE, chunk_time_interval => INTERVAL '7 days')"
    )
    op.create_index("idx_sr_sensor_time", "sensor_reading", ["sensor_id", sa.text("time DESC")])
    op.create_index("idx_sr_gh_time", "sensor_reading", ["greenhouse_id", sa.text("time DESC")])

    # 8.2 actuator_event
    op.create_table(
        "actuator_event",
        sa.Column("time", sa.DateTime(timezone=True), nullable=False),
        sa.Column("greenhouse_id", sa.Uuid(), nullable=False),
        sa.Column("controller_id", sa.Uuid(), nullable=False),
        sa.Column("actuator_id", sa.Uuid(), nullable=False),
        sa.Column("state", sa.Boolean(), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.ForeignKeyConstraint(["greenhouse_id"], ["greenhouse.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["controller_id"], ["controller.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["actuator_id"], ["actuator.id"], ondelete="CASCADE"),
    )
    op.execute(
        "SELECT create_hypertable('actuator_event', 'time', if_not_exists => TRUE, chunk_time_interval => INTERVAL '7 days')"
    )
    op.create_index("idx_ae_actuator_time", "actuator_event", ["actuator_id", sa.text("time DESC")])
    op.create_index("idx_ae_gh_time", "actuator_event", ["greenhouse_id", sa.text("time DESC")])

    # 8.3 controller_status
    op.create_table(
        "controller_status",
        sa.Column("time", sa.DateTime(timezone=True), nullable=False),
        sa.Column("greenhouse_id", sa.Uuid(), nullable=False),
        sa.Column("controller_id", sa.Uuid(), nullable=False),
        sa.Column("temp_stage", sa.Integer(), nullable=True),
        sa.Column("humi_stage", sa.Integer(), nullable=True),
        sa.Column("avg_interior_temp_c", sa.Float(), nullable=True),
        sa.Column("avg_interior_rh_pct", sa.Float(), nullable=True),
        sa.Column("avg_interior_pressure_hpa", sa.Float(), nullable=True),
        sa.Column("avg_exterior_temp_c", sa.Float(), nullable=True),
        sa.Column("avg_exterior_rh_pct", sa.Float(), nullable=True),
        sa.Column("avg_exterior_pressure_hpa", sa.Float(), nullable=True),
        sa.Column("avg_vpd_kpa", sa.Float(), nullable=True),
        sa.Column("enthalpy_in_kj_per_kg", sa.Float(), nullable=True),
        sa.Column("enthalpy_out_kj_per_kg", sa.Float(), nullable=True),
        sa.Column("override_active", sa.Boolean(), nullable=True),
        sa.Column("plan_version", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(["greenhouse_id"], ["greenhouse.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["controller_id"], ["controller.id"], ondelete="CASCADE"),
    )
    op.execute(
        "SELECT create_hypertable('controller_status', 'time', if_not_exists => TRUE, chunk_time_interval => INTERVAL '7 days')"
    )
    op.create_index("idx_cs_controller_time", "controller_status", ["controller_id", sa.text("time DESC")])

    # 8.4 input_event
    op.create_table(
        "input_event",
        sa.Column("time", sa.DateTime(timezone=True), nullable=False),
        sa.Column("greenhouse_id", sa.Uuid(), nullable=False),
        sa.Column("controller_id", sa.Uuid(), nullable=False),
        sa.Column("button_kind", sa.Text(), nullable=False),
        sa.Column("latched", sa.Boolean(), nullable=False, server_default=sa.text("FALSE")),
        sa.ForeignKeyConstraint(["greenhouse_id"], ["greenhouse.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["controller_id"], ["controller.id"], ondelete="CASCADE"),
    )
    op.execute(
        "SELECT create_hypertable('input_event', 'time', if_not_exists => TRUE, chunk_time_interval => INTERVAL '7 days')"
    )
    op.create_index("idx_ie_controller_time", "input_event", ["controller_id", sa.text("time DESC")])


def upgrade() -> None:
    _create_extensions()
    _create_meta_tables()
    _create_timeseries_tables()


def downgrade() -> None:
    # Drop timeseries tables first (hypertables behave like tables for DROP)
    op.drop_index("idx_ie_controller_time", table_name="input_event")
    op.drop_table("input_event")

    op.drop_index("idx_cs_controller_time", table_name="controller_status")
    op.drop_table("controller_status")

    op.drop_index("idx_ae_gh_time", table_name="actuator_event")
    op.drop_index("idx_ae_actuator_time", table_name="actuator_event")
    op.drop_table("actuator_event")

    op.drop_index("idx_sr_gh_time", table_name="sensor_reading")
    op.drop_index("idx_sr_sensor_time", table_name="sensor_reading")
    op.drop_table("sensor_reading")

    # Meta tables last
    op.drop_table("actuator_kind_meta")
    op.drop_table("sensor_kind_meta")

    # Do not drop extensions to avoid affecting other objects using them
