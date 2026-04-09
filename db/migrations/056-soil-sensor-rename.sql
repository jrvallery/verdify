-- 056-soil-sensor-rename.sql
-- Rename soil columns: south→south_1, east→south_2 (both in south zone)
-- No east soil sensor installed.

ALTER TABLE climate RENAME COLUMN soil_moisture_south TO soil_moisture_south_1;
ALTER TABLE climate RENAME COLUMN soil_temp_south TO soil_temp_south_1;
ALTER TABLE climate RENAME COLUMN soil_ec_south TO soil_ec_south_1;
ALTER TABLE climate RENAME COLUMN soil_moisture_east TO soil_moisture_south_2;
ALTER TABLE climate RENAME COLUMN soil_temp_east TO soil_temp_south_2;
-- west stays as-is
