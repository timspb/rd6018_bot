# D123 Sprint 18 — STOP_AND_DIAGNOSE effect ownership

Date: 2026-10-19. Exact starting HEAD: `9972f1991103b195a9e14222a51b0d2efb188039`.
Source-only change. No ESP, node104, HA, deployment, service, GitHub, or physical
system access was used.

## Bounded ownership cut

The remaining `ManagedChargeController._stop_and_diagnose` mutation body is
removed. All existing callers now route through
`runtime.charge.runtime.stop_diagnose.apply_stop_and_diagnose`, which builds a
frozen `StopDiagnoseEffect` and applies the exact existing fail-closed DONE
transition.

Preserved behavior: previous-stage capture, one stage-history edge to DONE,
recovery/final SAFE_WAIT clearing, exact `log_event_end`, stage/Ah clocks,
finish-timer clearing, MAIN evidence reset, exact `turn_off` / notification /
`V2_STOP_DIAGNOSE` actions, canonical session save ordering, and save-failure
pre-save mutation semantics. The owner contains no RD setter or
`application.execution_port` call. AuthorityDecision logic, recipes, Guard,
lease, persistence schema, verified-enable ordering and physical routing are
unchanged.

## Changed files

- `runtime/charge/runtime/stop_diagnose.py` — frozen input/effect, builder and
  single mutation/session-save applicator.
- `charge_controller.py` — old `_stop_and_diagnose` method deleted; callers
  invoke the canonical owner directly.
- `tests/test_d123_p3_stop_diagnose_effect.py` — immutable action parity,
  DONE/history/session-save semantics, save-failure ordering and AST guards.
- `tests/test_production_controller.py` — terminal persistence test calls the
  canonical owner instead of the deleted controller method.
- D123 checklist / owner map — Sprint 18 ownership and remaining gates.

## Verification

Focused related set: **58 PASS**.

Full offline Python 3.12 discovery using the existing repository venv and
synthetic test environment: **2,395 tests, 3 skipped, PASS**.

`python -m compileall -q` on touched Python files: PASS.
`git diff --check`: PASS.

This is software/source evidence only, not deployment or physical acceptance.

## Remaining gate

P3 still has Storage/DONE integration, Manual integration, remaining
central-controller stage application/orchestration, and eventual application-owned
session tick. P2 Guard restore admission remains fail-closed/deferred. P4/P5 and
physical acceptance remain open.
