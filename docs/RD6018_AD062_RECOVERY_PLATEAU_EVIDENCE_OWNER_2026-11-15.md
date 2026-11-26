# P1-AD062 — Recovery plateau evidence owner decision
Date: 2026-11-15
Status: ACCEPTED — source ownership classification only; no implementation or deployment authorization.

## Decision

Assign both `runtime/charge/evidence/recovery_plateau_observer.py` and `runtime/charge/evidence/recovery_plateau_policy.py` to **Telemetry**.

The observer owns bounded continuity/sample evidence for a pinned EFB Recovery/Conditioning MAIN observation. The policy evaluates that evidence and returns a typed `PlateauResult`. Neither module owns charge-stage selection, Safety veto, session orchestration, persistence, or physical execution.

Keep the adjacent owners separate:
- `application/charge_session_tick.py` — Application: invokes the observer inside the existing MAIN tick and publishes the evidence projection.
- `runtime/charge/evidence/recovery_plateau_observer.py` and `recovery_plateau_policy.py` — Telemetry: maintain/evaluate observation evidence only.
- `runtime/charge/strategy/main_authority.py` — Engine / Charge Stages: sole stage-transition decision owner.
- Existing Safety veto and existing effect/ExecutionPort path retain their current owners.

## Source evidence reviewed

- The observer is imported at the existing MAIN tick callsite in `application/charge_session_tick.py` (the only production source caller found by repository grep).
- Observer state is limited to its recipe, bounded sample deque, previous session identity and previous target voltage. It resets on ineligibility, session/target discontinuity, invalid CV/temperature/data, non-monotonic time, or gaps over 600 seconds.
- The rolling observation window is bounded by the existing recipe maximum (120 minutes); no timer, background task, poller, store, actuator, lease, or physical adapter is created.
- `observe_recovery_plateau` is a pure evidence calculation. It returns OBSERVING / CONFIRMED / PROGRESSING / INCONCLUSIVE / INVALID; it does not dispatch a stage effect.
- The existing MAIN tick is the only orchestration caller. The typed verdict is consumed downstream by the existing MAIN authority only under the explicit pinned-recipe opt-in; AD053/AD054 already document and test that handoff and Safety-veto precedence.
- Focused source/test inventory: `tests/test_recovery_plateau_observer.py` (8 tests), `tests/test_recovery_plateau_policy.py` (9 tests), and `tests/test_recovery_plateau_recipe_authority.py` (10 tests, including the two accepted integration/veto tests). These are existing evidence, not tests rerun for this documentation decision.

## Rejected classifications

- **Engine / Charge Stages:** rejected for the observer and policy because they produce evidence, not a stage-transition decision. `main_authority.py` remains the Engine owner.
- **Application:** rejected for the evidence modules because their production caller only orchestrates their invocation; the modules do not own workflow sequencing.
- **Safety Authority:** rejected because evidence validity is not a Safety admission/containment decision and the modules have no actuator/lease authority.

## Scope and invariants

This is an owner-registry/documentation decision only. No source, test, recipe default, threshold, stage mapping, timer, polling cadence, persistence, Safety policy, ExecutionPort path, ESPHome/HA/node104 state, firmware, or deployment was changed. Adaptive behavior remains subject to the existing pinned-recipe opt-in, existing MAIN authority, existing Safety veto, and existing physical/deployment gates.

## Repository baseline

Branch: `feature/main-mix-countdown-display`
HEAD: `3c692554074b27805419a9b0767133a1c8d78150`
Dirty entries at review: 353; preserve all existing WIP.
`runtime/production_runtime.py`: 2007 LOC.
