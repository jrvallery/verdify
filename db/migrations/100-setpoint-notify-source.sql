-- Include setpoint source in NOTIFY payload so the real-time ESP32 listener
-- can suppress rows that originated from ESP32 state echoes. Without source,
-- reconnect publishes every Number state as source='esp32' and the listener
-- pushes those echoes straight back to firmware.

CREATE OR REPLACE FUNCTION notify_setpoint_change()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    PERFORM pg_notify(
        'setpoint_changed',
        json_build_object(
            'parameter', NEW.parameter,
            'value', NEW.value,
            'source', NEW.source
        )::text
    );
    RETURN NEW;
END;
$$;
