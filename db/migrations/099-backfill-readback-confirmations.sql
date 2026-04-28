-- Backfill setpoint confirmations now that more firmware tunables expose
-- cfg_* readbacks. Rows whose requested value matches the latest ESP32
-- readback should not stay permanently unconfirmed just because the readback
-- sensor was added after the push.

WITH latest_readback AS (
    SELECT DISTINCT ON (parameter)
           parameter,
           value,
           ts
      FROM setpoint_snapshot
     ORDER BY parameter, ts DESC
)
UPDATE setpoint_changes sc
   SET confirmed_at = latest_readback.ts
  FROM latest_readback
 WHERE sc.parameter = latest_readback.parameter
   AND sc.confirmed_at IS NULL
   AND sc.ts <= latest_readback.ts
   AND abs(sc.value - latest_readback.value)
         / greatest(abs(latest_readback.value), 1e-3) < 0.01
   AND NOT EXISTS (
       SELECT 1
         FROM setpoint_changes newer
        WHERE newer.parameter = sc.parameter
          AND COALESCE(newer.greenhouse_id, '') = COALESCE(sc.greenhouse_id, '')
          AND newer.ts > sc.ts
          AND newer.ts <= latest_readback.ts
          AND abs(newer.value - latest_readback.value)
                / greatest(abs(latest_readback.value), 1e-3) >= 0.01
   );
