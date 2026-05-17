# Guardrail transition fixes - 2026-05-16

Objective: complete, test, validate, and deploy the next fixes identified from
the control-loop audit.

## Deliverables

| Fix | Artifact | Evidence |
|---|---|---|
| Guardrail-aware transition audit | `db/migrations/120-plan-transition-guardrail-audit.sql` | Adds `fn_plan_transition_audit(...)` and `v_plan_transition_audit_36h` with statuses `already_at_value`, `matched`, `guardrailed`, `held_by_guardrail`, `missed`, `mismatch`. Applied live to TimescaleDB. |
| Explicit unchanged guardrail holds | `ingestor/tasks.py::_write_clamp_audit_rows()` | Writes `setpoint_clamps` rows with `status='held_by_guardrail'` and plan metadata when no ESP32 setpoint push is emitted. |
| Guardrail dependence in scoring | `v_plan_guardrail_scorecard`, `fn_plan_anchor_score(...)`, `mcp/server.py::plan_evaluate()` | Anchor score subtracts deterministic guardrail penalty; `plan_evaluate` returns the guardrail scorecard. |
| Planner context includes transition holds | `scripts/gather-plan-context.sh` | Adds `GUARDRAIL-AWARE TRANSITION AUDIT` section from `fn_plan_transition_audit`. |
| Hot/dry `VENTILATE` review surface | `scripts/gather-plan-context.sh` | Adds sampled 24h hot/dry ventilation utilization: temp/VPD excess plus fan2/fog/mister percentages. No firmware OTA or control-law change was made for this guardrail-transition slice. |
| Bias-corrected VPD forecast | `scripts/gather-plan-context.sh` | Adds next-24h corrected temp/VPD/solar priors from `v_forecast_accuracy_lead_buckets`; corrected VPD is raw forecast minus rolling recent bias. |

## Live validation

| Check | Result |
|---|---|
| Migration applied | `db/migrations/120-plan-transition-guardrail-audit.sql` applied with `ON_ERROR_STOP=1`. |
| Transition audit query | `fn_plan_transition_audit(NULL, '36 hours', '10 minutes')` returned live statuses. |
| Guardrail scorecard query | `v_plan_guardrail_scorecard` returned live per-plan penalty rows. |
| Planner context script | `timeout 180 scripts/gather-plan-context.sh > /tmp/verdify-plan-context-120.out` exited 0 and included forecast calibration, transition audit, and hot/dry utilization sections. |
| Services deployed | `sudo systemctl restart verdify-ingestor.service verdify-mcp.service`; both returned `active`. |
| Open alerts after deploy | No open rows returned from `alert_log WHERE disposition='open'`. |

## Test evidence

| Command | Result |
|---|---|
| `make lint` | Passed. |
| `/srv/greenhouse/.venv/bin/pytest tests/test_08_observability.py tests/test_12_fidelity.py -q` | Passed. |
| `make test` | `373 passed, 2 skipped, 1 xfailed`. |
| `make site-doctor` | Passed with 0 errors; 2 stale-snapshot warnings unrelated to this change. |

## Notes

- This document covers the guardrail-transition slice only. The later lighting automation/reconciliation slice in the same working branch does change firmware files and is documented in `docs/lighting-automation-audit-2026-05-16.md`.
- Historical `missed` rows can still appear for pre-migration guardrail holds
  because the prior dispatcher did not emit hold rows. Future holds now land in
  `setpoint_clamps` with plan metadata and `held_by_guardrail` status.
