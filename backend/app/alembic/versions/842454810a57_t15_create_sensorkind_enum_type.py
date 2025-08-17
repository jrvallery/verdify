"""T15: Create SensorKind enum type

Revision ID: 842454810a57
Revises: 15c9254bb092
Create Date: 2025-08-15 14:45:54.391286

"""
from alembic import op
import sqlalchemy as sa
import sqlmodel.sql.sqltypes


# revision identifiers, used by Alembic.
revision = '842454810a57'
down_revision = '15c9254bb092'
branch_labels = None
depends_on = None


def upgrade():
    # Create the SensorKind enum type
    sensorkind_enum = sa.Enum(
        'TEMPERATURE', 'HUMIDITY', 'VPD', 'CO2', 'LIGHT', 'SOIL_MOISTURE',
        'WATER_FLOW', 'WATER_TOTAL', 'DEW_POINT', 'ABSOLUTE_HUMIDITY',
        'ENTHALPY_DELTA', 'AIR_PRESSURE', 'KWH', 'GAS_CONSUMPTION', 'PPFD',
        'WIND_SPEED', 'RAINFALL', 'POWER',
        name='sensorkind'
    )
    sensorkind_enum.create(op.get_bind())

    # Update existing sensor.kind values to match new enum values
    # Map old values to new enum values
    op.execute("""
        UPDATE sensor SET kind =
        CASE
            WHEN kind = 'temperature' THEN 'TEMPERATURE'
            WHEN kind = 'humidity' THEN 'HUMIDITY'
            WHEN kind = 'co2' THEN 'CO2'
            WHEN kind = 'light' THEN 'LIGHT'
            WHEN kind = 'soil_moisture' THEN 'SOIL_MOISTURE'
            ELSE 'TEMPERATURE'  -- Default fallback
        END
    """)

    # Update existing sensor_zone_map.kind values to match new enum values
    op.execute("""
        UPDATE sensor_zone_map SET kind =
        CASE
            WHEN kind = 'temperature' THEN 'TEMPERATURE'
            WHEN kind = 'humidity' THEN 'HUMIDITY'
            WHEN kind = 'co2' THEN 'CO2'
            WHEN kind = 'light' THEN 'LIGHT'
            WHEN kind = 'soil_moisture' THEN 'SOIL_MOISTURE'
            ELSE 'TEMPERATURE'  -- Default fallback
        END
    """)

    # Alter sensor.kind column to use the enum
    op.execute("ALTER TABLE sensor ALTER COLUMN kind TYPE sensorkind USING kind::sensorkind")

    # Alter sensor_zone_map.kind column to use the enum
    op.execute("ALTER TABLE sensor_zone_map ALTER COLUMN kind TYPE sensorkind USING kind::sensorkind")

    # Remove deprecated columns from sensor table
    # These are being removed because they're not in the OpenAPI spec
    op.drop_column('sensor', 'model')
    op.drop_column('sensor', 'unit')
    op.drop_column('sensor', 'value')


def downgrade():
    # Add back the removed columns
    op.add_column('sensor', sa.Column('value', sa.DOUBLE_PRECISION(precision=53), autoincrement=False, nullable=True))
    op.add_column('sensor', sa.Column('unit', sa.VARCHAR(), autoincrement=False, nullable=True))
    op.add_column('sensor', sa.Column('model', sa.VARCHAR(), autoincrement=False, nullable=True))

    # Convert enum back to VARCHAR
    op.alter_column('sensor_zone_map', 'kind',
                   existing_type=sa.Enum('TEMPERATURE', 'HUMIDITY', 'VPD', 'CO2', 'LIGHT', 'SOIL_MOISTURE', 'WATER_FLOW', 'WATER_TOTAL', 'DEW_POINT', 'ABSOLUTE_HUMIDITY', 'ENTHALPY_DELTA', 'AIR_PRESSURE', 'KWH', 'GAS_CONSUMPTION', 'PPFD', 'WIND_SPEED', 'RAINFALL', 'POWER', name='sensorkind'),
                   type_=sa.VARCHAR(),
                   existing_nullable=False)

    op.alter_column('sensor', 'kind',
                   existing_type=sa.Enum('TEMPERATURE', 'HUMIDITY', 'VPD', 'CO2', 'LIGHT', 'SOIL_MOISTURE', 'WATER_FLOW', 'WATER_TOTAL', 'DEW_POINT', 'ABSOLUTE_HUMIDITY', 'ENTHALPY_DELTA', 'AIR_PRESSURE', 'KWH', 'GAS_CONSUMPTION', 'PPFD', 'WIND_SPEED', 'RAINFALL', 'POWER', name='sensorkind'),
                   type_=sa.VARCHAR(),
                   existing_nullable=False)

    # Convert enum values back to lowercase
    op.execute("""
        UPDATE sensor SET kind =
        CASE
            WHEN kind = 'TEMPERATURE' THEN 'temperature'
            WHEN kind = 'HUMIDITY' THEN 'humidity'
            WHEN kind = 'CO2' THEN 'co2'
            WHEN kind = 'LIGHT' THEN 'light'
            WHEN kind = 'SOIL_MOISTURE' THEN 'soil_moisture'
            ELSE 'temperature'
        END
    """)

    op.execute("""
        UPDATE sensor_zone_map SET kind =
        CASE
            WHEN kind = 'TEMPERATURE' THEN 'temperature'
            WHEN kind = 'HUMIDITY' THEN 'humidity'
            WHEN kind = 'CO2' THEN 'co2'
            WHEN kind = 'LIGHT' THEN 'light'
            WHEN kind = 'SOIL_MOISTURE' THEN 'soil_moisture'
            ELSE 'temperature'
        END
    """)

    # Drop the enum type
    sa.Enum(name='sensorkind').drop(op.get_bind())
