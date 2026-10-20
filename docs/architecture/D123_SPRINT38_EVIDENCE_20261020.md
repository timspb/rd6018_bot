# D123 Sprint 38 — trace evidence event logging ownership

## Scope and baseline

Source-only work started at exact clean HEAD
`c6d0c43bca064eba22f175cdc05179d6497a1561` on
`codex/d118-start-lease-repair-20261019`. No live node104, ESP, HA,
deployment, firmware, recipe, threshold, or physical operation was performed.
P2 MAIN Guard restore admission remains fail-closed and deferred.

## Ownership cut

Moved the four analyzed-signal evidence log projections (current minimum,
voltage maximum, CV current reversal, CC voltage reversal) from controller
`tick` to `runtime.charge.evidence.trace_context.log_analysis_events`.
Preserved logger name, event gating, exact message formats, numeric formatting,
stage/session context, and timestamps. Signal-context construction and
first-stage assessment still use the local `metrics` value; no decision or
actuator authority changed.

## Validation

- Focused trace/evidence/MAIN/MIX/recovery/analyzer suite: **44 PASS**.
- Full Python 3.12 offline unittest discovery with synthetic
  `TG_TOKEN=123456789:d123-sprint38`: **2,428 PASS / 3 skipped**
  (**2,431 tests run**).
- `python -m compileall -q .`: PASS.
- `git diff --check`: PASS.
- Python environment: `/home/home-pc/rd6018-v3-deploy/.venv` (Python 3.12).

## Remaining P3 boundary

This cut closes only completion-evidence log projection. Central authority
dispatch still has subclass overrides in diagnostic/MIX-active characterization
controllers, and tick/trace assembly remains a transitional controller route.
Terminal persistence stays canonical in `runtime.charge.persistence`; do not
split the verified receipt -> stage edge -> save order. No P3 completion,
deployment, or physical acceptance is claimed.
