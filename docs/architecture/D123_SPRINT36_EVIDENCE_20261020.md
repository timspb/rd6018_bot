# D123 Sprint 36 — retire SAFE_WAIT compatibility router

## Scope and baseline

Source-only work started at exact clean HEAD
`7740bbb6f80f2ebd621647db8f00cfa434d8ddf1` on
`codex/d118-start-lease-repair-20261019`. No live node104, ESP, HA,
deployment, GitHub, firmware, recipe, threshold, or physical operation was
performed. P2 MAIN Guard restore admission remains fail-closed and deferred.

## Ownership cut

Removed `ManagedChargeController._handle_safe_wait_stage_override`, a
compatibility router with no production call sites. Its behavior tests now call
the canonical recovery or final SAFE_WAIT authority owner directly. The
authoritative `tick` decision path remains the production route. Tests continue
to verify requested actions, unknown-output fail-closed behavior, session-bound
verified token, commit ordering, and persisted Storage intent. No authority,
execution, or physical transaction behavior changed.

## Validation

- Focused SAFE_WAIT/recovery/transaction regression: **30 PASS**.
- Full Python 3.12 offline unittest discovery with synthetic
  `TG_TOKEN=123456789:d123-sprint36`: **2,426 PASS / 3 skipped**
  (**2,429 tests run**).
- `python -m compileall -q .`: PASS.
- `git diff --check`: PASS.
- Python environment: `/home/home-pc/rd6018-v3-deploy/.venv` (Python 3.12).

## Remaining boundary

P3 remains partial. `_handle_mix_stage_override` is another test-only legacy
characterization hook; tick evidence/trace assembly, terminal persistence,
Manual integration, and P2 Guard restore admission remain. Inspect each as a
separate bounded cut. `runtime.production_runtime` still constructs and calls
`ManagedChargeController`; do not start P4. No physical acceptance or
deployment is claimed.
