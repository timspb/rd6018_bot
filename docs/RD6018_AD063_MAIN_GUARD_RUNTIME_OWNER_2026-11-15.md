# P1-AD063 — MAIN Guard runtime orchestration owner decision
Date: 2026-11-15
Status: ACCEPTED — file-level owner classification only; no runtime implementation change.

## Decision

Assign `application/main_guard_runtime.py` to **Application**.

Its responsibility is the one-shot orchestration of an already-proposed MAIN Guard Iset reduction inside the existing production `data_logger` owner lock. It validates the current session/MAIN/EFB identity, HANDS_OFF exclusion, existing Safety/Native EdgeSafetyLease state, creates the existing canonical checkpoint writer, invokes the existing ExecutionPort transaction, and updates/quarantines the existing in-memory state from the transaction result.

This module does not create a task, timer, poller, lease owner, checkpoint store, physical adapter, or alternate writer. It does not turn Output ON. The physical Iset transaction remains owned by ExecutionPort; canonical session persistence remains owned by `CanonicalMainGuardCheckpoint`; read-only admission remains owned by `MainGuardAdmission`; the MAIN proposal/evidence remains owned by the existing Engine/Telemetry modules; Safety/edge lease remains the veto/admission owner.

## Source/call evidence reviewed

- Production import and invocation are in `runtime/production_runtime.py` within the existing `data_logger` path (import near line 61; call near line 1284 at review).
- The caller has already acquired the existing owner lock and only calls the function when the existing MAIN shadow produces a proposal and manual OFF conditions are absent.
- The function re-checks that the current task owns the same ExecutionPort guard lock, the pending proposal still matches, the canonical session identity/stage/chemistry still match, HANDS_OFF is false, Safety lease enforcement is enabled, renewals are not suspended, and a fresh Native lease read is armed/not tripped/not quarantined with acceptable Modbus age and remaining lease.
- Only then does it call `port.execute_main_current_guard_reduction(...)`; it never calls HassClient or a physical connector directly.
- Verified results update the existing shadow and controller Iset mirror. An ambiguous/failed transaction after hardware invocation or confirmed OFF quarantines through the existing `SessionRecoveryGuard`; it does not silently resume the prior target.
- Existing focused tests: `tests/test_d109_main_guard_runtime.py` (Native lease provenance, HANDS_OFF, lease rejection, verified reduction/persistence, ambiguous hardware ACK quarantine), `tests/test_d109_main_guard_checkpoint.py`, `tests/test_main_guard_admission.py`, `tests/test_main_guard_shadow.py`, and `tests/test_main_guard_transaction.py`.

## Rejected classifications

- **Safety Authority:** the module consumes and rechecks Safety/lease state but does not own the Safety policy, lease lifecycle or independent veto implementation.
- **Physical Execution:** it delegates the complete Iset transaction to the existing ExecutionPort and has no direct transport writer.
- **Sessions & Persistence:** it creates the existing checkpoint adapter for a transaction; it does not own the durable document format or storage lifecycle.
- **Engine / Charge Stages:** it consumes an already-proposed MAIN Guard reduction and does not derive the charge decision.

## Scope and invariants

This is a file-level owner decision only. No source, test, numeric threshold, lease duration, poll cadence, MAIN algorithm, OVP/OCP policy, persistence format, Output behavior, Safety rule, ExecutionPort transaction, firmware, physical equipment or deployment changed. Preserve the existing lock, Native lease, HANDS_OFF, cold-start, verified readback and quarantine contracts.

## Repository baseline

Branch: `feature/main-mix-countdown-display`
HEAD: `3c692554074b27805419a9b0767133a1c8d78150`
Dirty entries before this decision: 354; preserve all existing WIP.
`runtime/production_runtime.py`: 2007 LOC.


## 2026-11-15 — P1-AD064 MAIN Guard quarantine diagnostic boundary regression ACCEPTED

Independent regression found a stale assertion in `tests/test_d109_main_guard_runtime.py`: it expected raw `protection_code` / R16 age data to be copied into Application quarantine text. The current `application/main_guard_runtime.py::_quarantine_reason` intentionally excludes that raw field; raw protection representation remains owned by Telemetry/Safety/diagnostics. Corrected the test to assert that `protection_code` is absent from the Application reason. This is a test-contract correction only; production source and behavior are unchanged, and the revised assertion strengthens the owner boundary rather than weakening coverage.

Changed path: `tests/test_d109_main_guard_runtime.py` only. Windows project .venv with `PYTHONUTF8=1`: five-module cohort (`test_d109_main_guard_runtime`, `test_d109_main_guard_checkpoint`, `test_main_guard_admission`, `test_main_guard_shadow`, `test_main_guard_transaction`) **76 passed, 1 deselected, 43 subtests passed**. The deselected case requires symlink creation and is blocked by Windows host privilege (WinError 1314); WSL collection is currently blocked before assertions by missing `python-dotenv`. No dependency was installed. The Windows UTF-8 mode avoids a separate cp1251 source-read issue. No physical, HA, ESP, firmware, OTA, service or deployment action.
