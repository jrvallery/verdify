#!/usr/bin/env bash
# Export scrubbed public sample datasets for launch readers.
#
# The files intentionally exclude device identifiers, local IPs, trigger UUIDs,
# alert routing, hostnames, and raw sensor entity names.

set -euo pipefail

OUT_DIR=${1:-/mnt/iris/verdify-vault/website/static/data}
DB=(docker exec -i verdify-timescaledb psql -U verdify -d verdify -q -v ON_ERROR_STOP=1)

mkdir -p "$OUT_DIR"

"${DB[@]}" >"$OUT_DIR/verdify-sample-7d-climate.csv" <<'SQL'
COPY (
  WITH climate_5m AS (
    SELECT
      time_bucket('5 minutes', ts) AS bucket_utc,
      round(avg(temp_avg)::numeric, 2) AS temp_avg_f,
      round(avg(rh_avg)::numeric, 2) AS rh_avg_pct,
      round(avg(vpd_avg)::numeric, 3) AS vpd_avg_kpa,
      round(avg(outdoor_temp_f)::numeric, 2) AS outdoor_temp_f,
      round(avg(outdoor_rh_pct)::numeric, 2) AS outdoor_rh_pct,
      round(avg(solar_irradiance_w_m2)::numeric, 1) AS solar_irradiance_w_m2,
      round(max(dli_today)::numeric, 2) AS dli_today_mol_m2,
      round(max(water_total_gal)::numeric, 3) AS water_total_gal,
      round(max(mister_water_today)::numeric, 3) AS mister_water_today_gal,
      round(avg(hydro_ph)::numeric, 2) AS hydro_ph,
      round(avg(hydro_ec_us_cm)::numeric, 0) AS hydro_ec_us_cm,
      round(avg(soil_moisture_south_1)::numeric, 2) AS soil_moisture_south_1_pct,
      round(avg(soil_temp_south_1)::numeric, 2) AS soil_temp_south_1_f,
      count(*) AS source_samples
    FROM climate
    WHERE ts >= now() - interval '7 days'
    GROUP BY 1
  )
  SELECT
    to_char(bucket_utc AT TIME ZONE 'America/Denver', 'YYYY-MM-DD HH24:MI') AS bucket_local,
    temp_avg_f,
    rh_avg_pct,
    vpd_avg_kpa,
    outdoor_temp_f,
    outdoor_rh_pct,
    solar_irradiance_w_m2,
    dli_today_mol_m2,
    water_total_gal,
    mister_water_today_gal,
    hydro_ph,
    hydro_ec_us_cm,
    soil_moisture_south_1_pct,
    soil_temp_south_1_f,
    source_samples
  FROM climate_5m
  ORDER BY bucket_utc
) TO STDOUT WITH CSV HEADER;
SQL

"${DB[@]}" >"$OUT_DIR/verdify-sample-30d-plan-outcomes.csv" <<'SQL'
COPY (
  SELECT
    date,
    to_char(created_at AT TIME ZONE 'America/Denver', 'YYYY-MM-DD HH24:MI') AS created_local,
    plan_id,
    round(temp_mae_f, 2) AS temp_mae_f,
    round(vpd_mae_kpa, 3) AS vpd_mae_kpa,
    round(solar_mae_w, 1) AS solar_mae_w,
    round(compliance_pct::numeric, 1) AS compliance_pct,
    round(temp_compliance_pct::numeric, 1) AS temp_compliance_pct,
    round(vpd_compliance_pct::numeric, 1) AS vpd_compliance_pct,
    round(stress_hours_heat::numeric, 2) AS stress_hours_heat,
    round(stress_hours_vpd_high::numeric, 2) AS stress_hours_vpd_high,
    round(stress_hours_cold::numeric, 2) AS stress_hours_cold,
    round(stress_hours_vpd_low::numeric, 2) AS stress_hours_vpd_low,
    round(water_used_gal::numeric, 2) AS water_used_gal,
    round(mister_water_gal::numeric, 2) AS mister_water_gal,
    round(kwh::numeric, 2) AS kwh,
    round(therms_estimated::numeric, 3) AS therms_estimated,
    round(cost_total::numeric, 2) AS cost_total_usd,
    outcome_score,
    hypothesis,
    expected_outcome,
    actual_outcome
  FROM v_forecast_plan_outcome_mart
  WHERE date >= current_date - interval '30 days'
  ORDER BY date, created_at
) TO STDOUT WITH CSV HEADER;
SQL

cat >"$OUT_DIR/verdify-sample-readme.txt" <<EOF
Verdify public sample dataset
Generated: $(date -Is)

Files:
- verdify-sample-7d-climate.csv: 5-minute greenhouse climate/weather/hydro/soil sample for the most recent 7 days.
- verdify-sample-30d-plan-outcomes.csv: plan/outcome scorecard rows for the most recent 30 days.

Timestamps are rendered in America/Denver local time. The export intentionally omits local IPs, device IDs, trigger UUIDs, alert channels, hostnames, and raw sensor entity names.
EOF

printf 'Wrote public sample datasets to %s\n' "$OUT_DIR"
