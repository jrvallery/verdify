-- Migration 013: Add new columns to climate table
-- All NULLable — sensors not yet connected. No data impact on existing rows.

-- pH / EC (P1: Atlas Scientific EZO sensors)
ALTER TABLE climate ADD COLUMN IF NOT EXISTS ph_input           FLOAT;
ALTER TABLE climate ADD COLUMN IF NOT EXISTS ec_input           FLOAT;
ALTER TABLE climate ADD COLUMN IF NOT EXISTS ph_runoff_wall     FLOAT;
ALTER TABLE climate ADD COLUMN IF NOT EXISTS ec_runoff_wall     FLOAT;
ALTER TABLE climate ADD COLUMN IF NOT EXISTS ph_runoff_center   FLOAT;
ALTER TABLE climate ADD COLUMN IF NOT EXISTS ec_runoff_center   FLOAT;

-- Substrate moisture (P1: STEMMA capacitive sensors)
ALTER TABLE climate ADD COLUMN IF NOT EXISTS moisture_north     FLOAT;
ALTER TABLE climate ADD COLUMN IF NOT EXISTS moisture_south     FLOAT;
ALTER TABLE climate ADD COLUMN IF NOT EXISTS moisture_center    FLOAT;

-- PAR / True DLI (P1: Apogee SQ-520)
ALTER TABLE climate ADD COLUMN IF NOT EXISTS ppfd               FLOAT;
ALTER TABLE climate ADD COLUMN IF NOT EXISTS dli_par_today      FLOAT;

-- Barometric pressure (P2: BME280)
ALTER TABLE climate ADD COLUMN IF NOT EXISTS pressure_hpa       FLOAT;

-- Leaf temperature (P3: MLX90614 IR)
ALTER TABLE climate ADD COLUMN IF NOT EXISTS leaf_temp_north    FLOAT;
ALTER TABLE climate ADD COLUMN IF NOT EXISTS leaf_temp_south    FLOAT;

-- Leaf wetness (P3: capacitive)
ALTER TABLE climate ADD COLUMN IF NOT EXISTS leaf_wetness_north FLOAT;
ALTER TABLE climate ADD COLUMN IF NOT EXISTS leaf_wetness_south FLOAT;

-- Wind (P3: anemometer or Open-Meteo expansion)
ALTER TABLE climate ADD COLUMN IF NOT EXISTS wind_speed_mph     FLOAT;
ALTER TABLE climate ADD COLUMN IF NOT EXISTS wind_direction_deg FLOAT;

-- Outdoor PAR (P3: outdoor sensor or Tempest conversion)
ALTER TABLE climate ADD COLUMN IF NOT EXISTS outdoor_ppfd       FLOAT;
