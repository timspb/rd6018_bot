# P1-AD069 — Manual workflow owner decisions
Date: 2026-11-15
Status: PARTIAL ACCEPTANCE — four cohesive Application modules approved; five modules remain pending.

## Decisions

| Module | Primary owner | Decision |
|---|---|---|
| `application/manual_cooling_use_case.py` | Application | APPROVED as-is |
| `application/manual_mix_transition_use_case.py` | Application | APPROVED as-is |
| `application/manual_start_use_case.py` | Application | APPROVED as-is |
| `application/manual_stop_use_case.py` | Application | APPROVED as-is |
| `application/manual_observer_use_case.py` | NO FILE-LEVEL APPROVAL | HOLD — combines observer collection, policy evaluation and orchestration/state updates |
| `application/manual_phase_evidence.py` | NO FILE-LEVEL APPROVAL | HOLD — pure phase-evidence/decision rules; boundary between Telemetry and Engine/Charge Stages needs explicit decision |
| `application/manual_supervisor_use_case.py` | NO FILE-LEVEL APPROVAL | HOLD — Application orchestration candidate, but supervisor failure contract has a stale fake ExecutionPort assertion; test contract must be reconciled before approval |
| `application/operator_pause_use_case.py` | NO FILE-LEVEL APPROVAL | HOLD — orchestrates verified OFF/ON, programming, persistence and pause-clock updates; existing tests still assert pre-extraction AST/physical wiring and the runtime tests lack the current startup-authority fixture |
| `runtime/charge/evidence/manual_delta.py` | NO FILE-LEVEL APPROVAL | HOLD — stateful manual-delta evidence/reason logic; overlaps Telemetry evidence and Engine phase decisions; no single file owner justified yet |

## Evidence for the four approvals

The four approved modules are cohesive Application use cases. They coordinate user-requested workflows and delegate domain decisions, persistence, Safety admission and physical actions to existing owners. No module owns a physical adapter or bypasses the existing ExecutionPort boundary.

- **Cooling:** coordinates the manual cooling entry/exit workflow and delegates existing physical operations through the host ExecutionPort; it does not own thermal thresholds, the underlying stage lifecycle or Safety/Output implementation.
- **MIX transition:** coordinates the manual MAIN→MIX workflow and applies the existing lifecycle decision; it does not own the phase policy/evidence model, recovery budget, Safety verdict or physical implementation.
- **Start:** coordinates the operator start workflow, existing session initialization and the host's existing execution/persistence interfaces; it does not own admission policy, lease, Output driver or session storage format.
- **Stop:** coordinates operator stop, verified stop and existing session finalization; it does not own the Safety authority, physical adapter, lease or durable persistence implementation.

The modules remain where they are. No code move, wrapper, facade or new package is needed. This is an owner classification, not an implementation change.

## Regression evidence

Windows project `.venv`:
- Four-module focused cohort:
  `test_modularization_manual_cooling_use_case.py`,
  `test_modularization_manual_mix_transition_use_case.py`,
  `test_modularization_manual_start_use_case.py`,
  `test_modularization_manual_stop_use_case.py`.
  Result: **21 passed**.
- A wider manual workflow cohort was also exercised. Its 17 failures are concentrated in modules that remain unapproved: parity tests reading an unavailable/stale `HEAD:manual_mode.py` baseline, pause baseline/cutover tests asserting pre-extraction helper locations, physical-wiring AST tests asserting pre-extraction wrappers, and two operator-pause runtime tests blocked by the test fixture's unresolved edge startup-authority gate. The run had **71 passed, 17 failed, 21 subtests passed**. These failures are not represented as PASS and do not justify weakening the tests or approving the affected modules.
- Separate lifecycle contract test `test_supervisor_requests_emergency_off_on_observer_failure` fails because its fake ExecutionPort asserts the old generic `disable_calls` contract while production supervisor uses the dedicated `request_emergency_off` contract. Keep supervisor pending until the fixture asserts the actual dedicated contract.

No test was changed to obtain these results. The broad failures are recorded as blockers for the corresponding modules, not ignored.

## Prior decisions reconciled

AD016 phase lifecycle extraction, AD019 MIX hold, AD021 manual delta epoch parity and AD023 cooling delta reset remain in force. AD069 does not change their behavior, timers, evidence thresholds, stage rules, delta epochs, recovery budget, Safety/lease contracts or execution ordering.

## Authority exclusions

All four approved Application use cases are orchestration owners only. They do not become owners of:
- RD6018 Output/physical transport or native ESP callbacks;
- Safety authority, startup/edge admission or the 900-second Safety Lease;
- raw R16/protection telemetry or native age interpretation;
- canonical session schema, persistence storage or recovery restore;
- charge-stage/phase policy and evidence thresholds outside their orchestration contract.

## Repository and safety

No source, test, CSV, generated registry, or repository metadata was changed for AD069. No staging, commit, push, reset, clean, stash or checkout. No HA, ESPHome, node104, firmware, OTA, service restart, physical equipment or deployment action. Existing WIP preserved; release remains HOLD.


## 2026-11-15 — Correction: owner census source reconciliation after AD069

The AD069 cumulative figures (32 primary decisions / 53 effective decisions / 446 remaining) are a manual reconciliation of the AD061 baseline plus the tracked AD062–AD069 decision records. They are **not** the current value of the old AD014 sidecar. Re-running `.recipe-studio-local/count_owner_approvals.py` against `mod_p1_owner_decisions_ad014_20261113.csv` still yields its historical snapshot: 499 total / 43 recorded effective approvals / 456 pending; high-risk 73 total / 8 recorded approved / 12 explicit UNAPPROVED / 53 blank; critical 15/15. AD069's four decisions are not yet folded into that sidecar or the AD012 generated inventory. Do not describe the cumulative 53 as a value read directly from the four sidecar fields, and do not silently rewrite the generated CSV. A deliberate registry refresh must reconcile all tracked AD062–AD069 decision documents first.
