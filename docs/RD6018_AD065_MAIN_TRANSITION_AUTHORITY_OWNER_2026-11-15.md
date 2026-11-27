# P1-AD065 — MAIN transition authority owner decision
Date: 2026-11-15
Status: ACCEPTED — file-level owner classification only.

## Decision

Assign `runtime/charge/strategy/main_authority.py` to **Engine / Charge Stages**.

`decide_main_transition` is the pure, canonical MAIN stage-transition policy. It consumes the already-produced policy decision, first-stage evidence, profile/intent, elapsed/hold values, recovery budget and optional pinned adaptive-plateau verdict, then returns one typed `AuthorityDecision`. It does not mutate the controller, persist state, render UI, read physical transport, operate Safety leases, or execute effects.

## Source and call evidence

- Production callsites: `runtime/charge/runtime/main_scaffold.py` and `runtime/charge/programs/native_recipe_policy.py`.
- `main_scaffold.py` remains the existing runtime/application integration that applies the returned decision through existing typed effects and the existing Safety veto.
- `native_recipe_policy.py` is a recipe adapter and delegates to the same MAIN decision owner; it does not create a second policy.
- The module consumes Telemetry/evidence values (`FirstStageAssessment`, adaptive plateau verdict) and a prior `RecoveryDecision`, but its owned output is the MAIN transition choice: CONTINUE, STOP_AND_DIAGNOSE, ENTER_DESULFATION, ENTER_MIX, ADVANCE_AGM_STEP, COMPLETE_NORMAL or COMPLETE_TO_SAFE_WAIT.
- The adaptive EFB plateau branch remains disabled unless the existing pinned-recipe opt-in is true; it consumes evidence but does not let the observer authorize HV. Existing recovery budget and external Safety veto/effect ordering remain in force.

## Rejected classifications

- **Telemetry:** supplies first-stage and plateau evidence; does not own the stage transition.
- **Safety Authority:** supplies the policy decision/veto and remains the independent admission/containment owner; MAIN authority consumes that input.
- **Application:** callsites orchestrate invocation/effects; the policy itself is pure domain decision logic.

## Verification

Windows project `.venv`, Python UTF-8 mode:
- `tests/test_charge_authority.py`
- `tests/test_v3_main_authority_migration.py`
- `tests/test_native_recipe_main_policy_overrides.py`
- `tests/test_native_recipe_policy_parity.py`
- `tests/test_main_guard_admission.py` (symlink-only test deselected for Windows host privilege)

Result: **42 passed, 1 deselected, 155 subtests passed**.

## Related unresolved boundary

`runtime/charge/strategy/main_guard_admission.py` remains **PENDING / NO FILE-LEVEL APPROVAL**. The primary admission function is a Safety gate, but the same module also exports `read_canonical_session`, which is reused by `runtime/startup_recovery.py` for recovery/restore observations. Do not force a single owner or move this helper without checking the existing `runtime/charge/persistence.py` contract and import graph. No source change was made.

## Scope

No source, tests, thresholds, recipe defaults, lease, stage mapping, Safety veto, effect, ExecutionPort, firmware, physical equipment or deployment changed. This is an owner decision only.
