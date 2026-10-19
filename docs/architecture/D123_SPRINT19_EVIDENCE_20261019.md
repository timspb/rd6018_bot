# D123 Sprint 19 — AGM MAIN step-advance effect

Date: 2026-10-19. Exact starting HEAD: `26902ff1ef1fae862c4d4b9bd4871d891856f8de`.
Source-only change. No ESP, node104, HA, deployment, service, GitHub, or physical
system access was used.

## Bounded ownership cut

The former `ManagedChargeController._advance_agm_step` mutation/action body is
removed. The sole `AuthorityAction.ADVANCE_AGM_STEP` caller now builds a frozen
`AgmStepAdvanceEffect` in `runtime.charge.runtime.agm_step_advance` and applies
it once.

The exact prior order is preserved: AGM index advances first, stage/Ah clocks
and Delta/blanking plus MAIN evidence are reset, then the existing
`_main_target(temp)` is evaluated using the new index, followed by the existing
phase-limit helper. No target formula or temperature/envelope logic is copied.
The exact set_voltage/set_current, OVP/OCP, phase-current mirror, notification,
and `V2_AGM_STEP_N` event are preserved.

The effect owner has no RD setter, Output intent, execution-port, persistence,
Guard, lease, or recipe ownership. Decision authority remains
`decide_main_transition`.

## Changed files

- `runtime/charge/runtime/agm_step_advance.py` — frozen effect and one
  applicator.
- `charge_controller.py` — old `_advance_agm_step` deleted; sole decision
  branch builds/applies the typed effect.
- `tests/test_d123_p3_agm_step_advance_effect.py` — index clamp/immutability,
  exact target/limits/reset parity, cold temperature-compensation parity, and
  AST no-old-owner/no-physical-writer guards.
- D123 checklist / owner map — Sprint 19 status and remaining gates.

## Verification

Focused AGM/MAIN authority set: **34 PASS**.

Full offline Python 3.12 discovery using the existing repository venv and
synthetic test environment: **2,399 tests, 3 skipped, PASS**.

`python -m compileall -q` on touched Python files: PASS.
`git diff --check`: PASS.

This is source/software evidence only, not deployment or physical acceptance.

## Remaining gate

P3 still retains remaining `_apply_authoritative_decision` orchestration,
Storage/DONE and Manual integration, and the final application-owned session
tick cut. P2 Guard restore admission remains fail-closed/deferred. P4/P5 and
physical acceptance remain open.
