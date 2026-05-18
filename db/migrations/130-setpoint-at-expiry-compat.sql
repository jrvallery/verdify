-- 130-setpoint-at-expiry-compat.sql
--
-- Keep the legacy vallery-only fn_setpoint_at(param, ts) compatible with the
-- greenhouse-aware overload from migration 119. Historical operator overlays
-- can now be expired without continuing to affect band/compliance graphs that
-- still call the two-argument helper.

CREATE OR REPLACE FUNCTION fn_setpoint_at(p_param text, p_ts timestamptz)
RETURNS double precision
LANGUAGE sql STABLE
AS $$
    WITH latest AS (
        SELECT value, expired_at
          FROM setpoint_changes
         WHERE parameter = p_param
           AND ts <= p_ts
           AND CASE
               WHEN p_param IN ('temp_high', 'temp_low') THEN value BETWEEN 30 AND 120
               WHEN p_param IN ('vpd_high', 'vpd_low') THEN value BETWEEN 0.1 AND 5.0
               ELSE true
           END
         ORDER BY ts DESC
         LIMIT 1
    ), active AS (
        SELECT value
          FROM latest
         WHERE expired_at IS NULL OR expired_at > p_ts
    ), fallback AS (
        SELECT CASE
            WHEN p_param = 'temp_low' THEN (SELECT temp_low FROM fn_band_setpoints(p_ts))
            WHEN p_param = 'temp_high' THEN (SELECT temp_high FROM fn_band_setpoints(p_ts))
            WHEN p_param = 'vpd_low' THEN (SELECT house_vpd_low FROM fn_house_vpd_control_band(p_ts))
            WHEN p_param = 'vpd_high' THEN (SELECT house_vpd_high FROM fn_house_vpd_control_band(p_ts))
            ELSE NULL::double precision
        END AS value
        WHERE EXISTS (SELECT 1 FROM latest WHERE expired_at IS NOT NULL AND expired_at <= p_ts)
    )
    SELECT COALESCE((SELECT value FROM active), (SELECT value FROM fallback));
$$;

CREATE OR REPLACE FUNCTION fn_setpoint_at(
    p_greenhouse_id text,
    p_param text,
    p_ts timestamptz
)
RETURNS double precision
LANGUAGE sql STABLE
AS $$
    WITH latest AS (
        SELECT value, expired_at
          FROM setpoint_changes
         WHERE greenhouse_id = p_greenhouse_id
           AND parameter = p_param
           AND ts <= p_ts
         ORDER BY ts DESC
         LIMIT 1
    ), active AS (
        SELECT value
          FROM latest
         WHERE expired_at IS NULL OR expired_at > p_ts
    ), fallback AS (
        SELECT CASE
            WHEN p_param = 'temp_low' THEN (SELECT temp_low FROM fn_band_setpoints(p_ts))
            WHEN p_param = 'temp_high' THEN (SELECT temp_high FROM fn_band_setpoints(p_ts))
            WHEN p_param = 'vpd_low' THEN (SELECT house_vpd_low FROM fn_house_vpd_control_band(p_ts))
            WHEN p_param = 'vpd_high' THEN (SELECT house_vpd_high FROM fn_house_vpd_control_band(p_ts))
            ELSE NULL::double precision
        END AS value
        WHERE EXISTS (SELECT 1 FROM latest WHERE expired_at IS NOT NULL AND expired_at <= p_ts)
    )
    SELECT COALESCE((SELECT value FROM active), (SELECT value FROM fallback));
$$;
