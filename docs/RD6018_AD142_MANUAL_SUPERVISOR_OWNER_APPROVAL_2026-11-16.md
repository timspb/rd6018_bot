# RD6018 AD-142 — Manual supervisor Application owner approval

Date: 2026-11-16  
Status: **APPROVED — file-level Application owner; source/fake only**

## Decision

Approve `application/manual_supervisor_use_case.py` as an Application-owned Manual session supervisor orchestration module.

This resolves the specific AD069 HOLD reason that the supervisor regression still asserted the old generic ExecutionPort OFF contract. The current fake now exercises the dedicated `request_emergency_off()` contract and the selected Windows cohort passes.

## Source evidence

The module has one public operation, `supervise_manual_session(session, poll_seconds)`:
- loops while the existing session reports active;
- calls the existing session's `observe_once()`;
- sleeps using the caller-supplied polling interval;
- propagates `asyncio.CancelledError` unchanged;
- on an observer/runtime exception, requests emergency OFF through the existing `session.execution_port.request_emergency_off()`;
- transitions the existing session to FAILED and persists through its existing session owner.

It imports only asyncio. It does not import `manual_mode`, `runtime.production_runtime`, HA, ESPHome, a physical adapter, a state store, or a second lease. The Manual manager's `_run()` is a thin delegate passing itself and the existing `MANUAL_POLL_SEC`.

## Boundary and exclusions

The module owns loop/failure orchestration only. It does not own:
- Manual session state/schema or persistence;
- observation, telemetry reads or phase evidence;
- cooling/MAIN→MIX/threshold policy;
- the ExecutionPort, Safety guard, emergency OFF implementation or EdgeSafetyLease;
- the poll interval policy.

No source move, wrapper, facade, new task, state or adapter was added. Existing cancellation behavior remains: task cancellation propagates without synthesizing a runtime failure or issuing an extra OFF; ordinary observer exceptions use the existing emergency containment boundary and persist FAILED.

## Regression evidence

Windows project .venv:
- `tests/test_modularization_manual_supervisor_use_case.py`: **7 passed**.
- Full selected Manual/store/use-case/Operator Pause cohort including supervisor: **109 passed, 33 subtests passed**.
- py_compile and scoped git diff --check: PASS.

No tests were weakened or rewritten for this approval; the current supervisor fake already uses request_emergency_off.

## Authority

This approval covers only `application.manual_supervisor_use_case.py`. AD069 HOLD remains unchanged for:
- `application.manual_observer_use_case.py` (mixed observation, policy and state orchestration);
- `application.manual_phase_evidence.py` (decision/evidence owner boundary unresolved);
- `runtime/charge/evidence/manual_delta.py` (stateful evidence/reason owner unresolved);
- `application/operator_pause_use_case.py` (crosses verified OFF/ON, programming, persistence and clock updates; AD130 safety audit is not a file-level owner approval).

AD069's four previously approved Manual use cases remain unchanged. AD014's 26-owner registry snapshot is historical; do not silently edit its generated sidecar. Fold AD142 into the next deliberate owner-registry reconciliation after all decision records are reviewed.

## Safety and repository

No HA, ESP Native, node104, firmware, OTA, service restart, hardware, RD6018 Output, physical Manual action, staging, commit, push, reset, stash or clean. HEAD remains `3c692554074b27805419a9b0767133a1c8d78150`; production/release/physical acceptance remain HOLD.
