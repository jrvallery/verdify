-- Persist ESP32 heap-fragmentation diagnostics as first-class columns.
--
-- Free heap alone is misleading on this controller: recent WDT windows showed
-- acceptable total free kB while the largest allocatable block collapsed.

ALTER TABLE diagnostics
    ADD COLUMN IF NOT EXISTS heap_min_free_kb double precision,
    ADD COLUMN IF NOT EXISTS heap_largest_free_block_kb double precision;

CREATE INDEX IF NOT EXISTS idx_diagnostics_heap_largest_block_low
    ON diagnostics (heap_largest_free_block_kb, ts DESC)
    WHERE heap_largest_free_block_kb IS NOT NULL
      AND heap_largest_free_block_kb < 18;

CREATE INDEX IF NOT EXISTS idx_diagnostics_heap_min_free_low
    ON diagnostics (heap_min_free_kb, ts DESC)
    WHERE heap_min_free_kb IS NOT NULL
      AND heap_min_free_kb < 20;

COMMENT ON COLUMN diagnostics.heap_min_free_kb IS
    'ESP32 minimum free heap since boot, in kB; persists the Minimum Free Heap sensor.';
COMMENT ON COLUMN diagnostics.heap_largest_free_block_kb IS
    'ESP32 largest allocatable heap block, in kB; primary fragmentation signal for heap-pressure alerts.';
