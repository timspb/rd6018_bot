# D123 Sprint 33 — DESULFATION completion authority ownership

## Scope and baseline

Source-only work started at exact clean HEAD
`e0ee41f3d9b322026e396743e4add6905b039a1b` on
`codex/d118-start-lease-repair-20261019`. No live node104, ESP, HA,
deployment, GitHub, firmware, recipe, threshold, or physical operation was
performed. P2 MAIN Guard restore admission remains fail-closed and deferred.

## Ownership cut

Moved DESULFATION elapsed-time evaluation and its completion-effect dispatch
from `ManagedChargeController._apply_authoritative_decision` into the existing
`runtime.charge.runtime.recovery_scaffold.apply_desulfation_authority_tick`.
The controller retains authoritative-stage/current-stage admission and one
dispatch. The owner calls the unchanged `decide_desulfation`, preserves the
existing `max(0, timestamp - stage_start_time)` elapsed calculation, and uses
the unchanged `_main_target(temp)` selection and
`complete_desulfation_to_safe_wait` typed effect route.

At the existing two-hour completion boundary, successful identity validation
still returns `COMPLETE_TO_SAFE_WAIT` with the same decision reason. Invalid
identity/capture still returns `CONTINUE` with the exact
`desulfation_completion_session_identity_invalid` reason and does not invent a
stage transition. The owner contains no ExecutionPort or direct RD setter
dependency. Recovery/final SAFE_WAIT handling, persistence, Guard/lease,
recipes, and physical transaction ownership are unchanged.

## Validation

- Focused DESULFATION/recovery/SAFE_WAIT/authority regression: **40 PASS**.
- Full Python 3.12 offline unittest discovery with synthetic
  `TG_TOKEN=123456789:d123-sprint33`: **2,426 PASS / 3 skipped**
  (**2,429 tests run**).
- `python -m compileall -q .`: PASS.
- `git diff --check`: PASS.
- Python environment: `/home/home-pc/rd6018-v3-deploy/.venv` (Python 3.12).

## Remaining boundary

P3 remains partial. Recovery/final SAFE_WAIT routing, outer stage dispatch,
tick evidence/trace assembly, terminal persistence ownership, and Manual
integration remain outside this cut. `runtime.production_runtime` still
constructs and calls `ManagedChargeController`; do not start P4 before P2/P3
convergence is convincingly complete. No physical acceptance or deployment is
claimed.
