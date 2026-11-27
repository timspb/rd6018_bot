# P1-AD073 — Recovery quarantine owner decisions
Date: 2026-11-15
Status: THREE HIGH-RISK FILE OWNERS APPROVED AS-IS; no code movement.

## Decisions

| Module | Primary owner | Decision |
|---|---|---|
| `application/operator_recovery_clearance.py` | Application | APPROVED as-is |
| `application/session_recovery_guard.py` | Recovery & Ownership | APPROVED as-is |
| `runtime/journal/recovery_quarantine.py` | Recovery & Ownership | APPROVED as-is |

## Evidence

### Application — OperatorRecoveryClearanceService
Production wiring is in `production_bootstrap.py:182–194`; the service is installed with the existing Telegram authority, canonical ExecutionPort, RecoveryQuarantineJournal and ControllerSessionRetirement adapter. The single `clear()` use case sequences:
1. canonical owner lock and quarantine precondition;
2. explicit operator authority result;
3. exact session/incident identity binding;
4. fresh typed verified-OFF evidence through ExecutionPort;
5. controller session retirement;
6. durable quarantine tombstone;
7. controller retirement finalization;
8. in-memory guard release only after durable completion.

It does not call HA/ESP/Modbus directly, own physical OFF, own the session writer, or implement Telegram identity policy. It is a cohesive Application orchestration owner. Relevant tests: `test_d087_recovery_clearance_integration.py`, `test_operator_managed_stop.py`, `test_d086_recovery_retirement.py`.

Known stale source comment: module docstring lines 1–5 says the coordinator is unwired until three owners exist, while production_bootstrap currently wires the authority, retirement adapter and journal. This is a documentation defect only; do not infer the service is inactive.

### Recovery & Ownership — SessionRecoveryGuard
The 60-line module owns only process-local sticky quarantine state and the automatic-control gate. `quarantine()` latches RAM before invoking the injected durable incident writer; persistence failure propagates while the process remains quarantined. Durable production mode forbids RAM-only operator rearm; the only production release is the coordinator-only final step after session and journal retirement. It has no physical actuator or filesystem authority.

Consumers include ExecutionPort, MainGuardRuntime, SessionRecoveryService, production lifecycle and startup recovery. The durable journal is a separate collaborator, not a second in-memory guard. Relevant tests: `test_session_recovery_guard.py`, `test_session_recovery_service.py`, `test_modularization_session_recovery_contract.py`.

### Recovery & Ownership — RecoveryQuarantineJournal
The journal is the single durable owner of the quarantine incident schema (v1), identity binding and retirement tombstone schema (v2), including strict fail-closed load, prior retired incident archive, and atomic incident/tombstone writes. It delegates generic atomic file replacement to `runtime.charge.session_atomic.atomic_session_write`; it does not own the canonical charge-session document or Output. Production composition loads the journal before constructing the canonical ExecutionPort/guard and binds it as the guard's durable persistence callback (`production_bootstrap.py:165–179`).

Relevant tests: `test_recovery_quarantine_journal.py`, `test_d087_recovery_clearance_integration.py`, `test_d086_recovery_retirement.py`.

## Dependency note — no move authorized

`runtime/journal/recovery_quarantine.py` imports the immutable `RecoveryGuardState` DTO from `application.session_recovery_guard`. This is a narrow dependency-direction exception (Persistence/Recovery implementation importing an Application package), not a second owner or mixed side effect. Do not add a new shared package to fix one dataclass. Keep the exception visible for the P2 passive import-boundary inventory; if later repaired, use an existing neutral domain owner and preserve the exact DTO/API.

## Authority exclusions

- Application service owns workflow ordering only; it does not own authorization policy, Native OFF provenance, controller session persistence, quarantine schema, Safety admission or physical Output.
- SessionRecoveryGuard owns RAM quarantine state only; durable incident bytes remain with RecoveryQuarantineJournal.
- RecoveryQuarantineJournal owns only the recovery incident/tombstone schema and path; canonical charge_session.json remains with runtime.charge.persistence.
- No new authorization, crypto token, key, queue, worker, physical owner or recovery state store.

## Verification and safety

This is source-based owner approval; tests were inspected but **NOT RUN** in this decision. No source, tests, CSV, generated registry, firmware, HA, ESP Native, hardware, node104, service, lease, Output or deployment was touched. No code moves. Branch/HEAD remain `feature/main-mix-countdown-display / 3c692554074b27805419a9b0767133a1c8d78150`; dirty WIP preserved; release HOLD.
