# D123 Sprint 20 — MIX finish-hold start effect

Date: 2026-10-19. Exact starting HEAD: `f43b548dc3b5d8f517a5483313e95daba6f07351`.
Source-only change. No ESP, node104, HA, deployment, service, GitHub, or physical
system access was used.

## Bounded ownership cut

The mutable `AuthorityAction.START_FINISH_HOLD` body is moved from
`ManagedChargeController._apply_authoritative_decision` into the frozen
`runtime.charge.runtime.mix_finish_hold.MixFinishHoldEffect`.

The owner preserves the existing timestamp, CV/CC mode, sticky
`finish_timer_start`, Delta-reported marker, optional persisted finish-evidence
shape, exact Imin/Delta-I or Vmax/Delta-V text, notification and
`V2_FINISH_HOLD_START` log event. Missing metric evidence still starts the
sticky hold but leaves the optional finish-evidence snapshot absent, matching
the previous `hasattr`/metric guards.

No MIX decision threshold, hold duration, target, recipe, stage transition,
session schema, Guard, lease, execution, or physical writer moved. The existing
controller retains only the decision call, typed effect invocation and evidence
logger line for this branch.

## Changed files

- `runtime/charge/runtime/mix_finish_hold.py` — frozen effect builder and one
  applicator.
- `charge_controller.py` — START_FINISH_HOLD inline mutations/action text
  replaced by typed owner invocation.
- `tests/test_d123_p3_mix_finish_hold_effect.py` — CV/CC evidence/action
  parity, missing-metric behavior and AST/no-physical-writer guards.
- D123 checklist / owner map — Sprint 20 status.

## Verification

Focused MIX/authority set: **37 PASS**.

Full offline Python 3.12 discovery using the existing repository venv and
synthetic test environment: **2,403 tests, 3 skipped, PASS**.

`python -m compileall -q` on touched Python files: PASS.
`git diff --check`: PASS.

This is source/software evidence only, not deployment or physical acceptance.

## Remaining gate

P3 still retains MIX read-model mirrors/completion evidence logging,
`_apply_authoritative_decision` dispatch/orchestration, Storage/DONE and Manual
integration, and eventual application-owned session tick. P2 Guard restore
admission remains fail-closed/deferred. P4/P5 and physical acceptance remain open.
