-- 051-estimated-plant-dli.sql
-- Estimated actual plant DLI correcting for sensor limitations
--
-- The LDR sensor reads 25-40% of actual plant-available light due to:
--   - Saturation above ~28K lux
--   - Morning tree shadow blocking direct sun
--   - Inability to see grow light spectrum
-- Correction: sensor_dli × 3.5 for saturation/gap + grow_light_hours × 0.8 mol/hr

CREATE OR REPLACE VIEW v_estimated_plant_dli AS
SELECT
    ds.date,
    ROUND(COALESCE(ds.dli_final, 0)::numeric, 1)           AS sensor_dli,
    ROUND((COALESCE(ds.dli_final, 0) * 3.5)::numeric, 1)   AS corrected_solar_dli,
    ROUND((COALESCE(ds.runtime_grow_light_min, 0) / 60.0)::numeric, 1) AS grow_light_hours,
    ROUND((COALESCE(ds.runtime_grow_light_min, 0) / 60.0 * 0.8)::numeric, 1) AS grow_light_dli,
    ROUND((COALESCE(ds.dli_final, 0) * 3.5
         + COALESCE(ds.runtime_grow_light_min, 0) / 60.0 * 0.8)::numeric, 1) AS estimated_plant_dli,
    CASE
        WHEN (COALESCE(ds.dli_final, 0) * 3.5
            + COALESCE(ds.runtime_grow_light_min, 0) / 60.0 * 0.8) < 12 THEN 'LOW'
        WHEN (COALESCE(ds.dli_final, 0) * 3.5
            + COALESCE(ds.runtime_grow_light_min, 0) / 60.0 * 0.8) > 30 THEN 'HIGH'
        ELSE 'OK'
    END AS dli_status
FROM daily_summary ds
ORDER BY ds.date DESC;

COMMENT ON VIEW v_estimated_plant_dli IS
    'Estimated actual plant DLI: sensor × 3.5 correction + grow light hours × 0.8 mol/hr. LOW<12, OK=12-30, HIGH>30.';
