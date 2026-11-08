# RD6018 protection / false-positive / session retirement audit — 2026-11-08

Scope: source-only and offline, HEAD observed 5c071ba. No node104 / ESP / HA writes, no Output actuation or deployment.

## Ownership map
- Pure intent policy: runtime/safety/engine.py.
- Runtime managed safety effects and one 300-second recovery epoch: managed_runtime_safety.py, runtime/safety/telemetry_recovery.py.
- Native callback transport and coherence: runtime/physical/transports/esp128.py and esp128_callback_coherence.py.
- Physical OFF/ON strict receipts: runtime_safety.py, runtime_safety_strict.py, canonical ExecutionPort.
- Watchdogs: runtime/safety/soft_watchdog.py and watchdog_policy.py, plus runtime/production_runtime.py::watchdog_loop.
- Operator retirement: operator_managed_stop.py; recovery quarantine: application/session_recovery_guard.py, session_recovery_service.py, operator_recovery_clearance.py; edge lease: edge_safety_lease.py.
This is modular by domain, but production effects remain spread across three substantial runtime classes and multiple loops. Do not introduce another safety owner.

## Verified source behaviors
- Partial Native callback delay when Output/protection evidence is fresh/normal: one bounded 300s wait with charge ticks deferred; missing/stale values are not command authority.
- Known OVP/OCP/OPP or measured absolute violation preempts the wait.
- Output OFF unconfirmed: ON inhibited, bounded 60s OFF retries only on fresh ON evidence, incident-level notification deduplication.
- Operator AUTO STOP fallback accepts only a post-attempt ESP Native SensorState R18 OFF + I≈0 and unchanged session identity; cannot retire using cached HA/switch data.
- Implausible battery_voltage 0.010 V is NOT classified as a transient callback delay; it causes immediate fail-closed if safety relevant. This conservatism prevents unproven measurements from controlling the charger but may produce nuisance STOP if the transport produces an isolated bogus value.

## Open risks to resolve
1. Recovery epoch FIXED IN SOURCE: verified red regression (old incident timestamp survived idle OFF), then guard clears the epoch only when no managed controller remains AND Output is fresh OFF. Unknown or stale Output preserves the epoch. Extended regression now PASS; focused guard/STOP/watchdog cohort **66 PASS**. Not deployed; no physical evidence.
2. Competing watchdog loops: managed guard, soft_watchdog_loop and watchdog_loop all exist; timeout comparisons (300s managed, 360s soft heartbeat tolerance) and source clocks differ. Audit the exact flow on interrupted/partial callbacks and ambiguous Output; keep one semantic authority without loss of fail-closed behavior.
3. Single implausible battery voltage sample: trace ESP Modbus register, scaling, Native callback provenance, timestamps, and mixing with UI values. Do not suppress real undervoltage or relax hardware OVP/OCP; distinguish invalid observation from confirmed physical condition using source evidence.
4. STOP after persistent lack of fresh Native R18 remains fail-closed. Recovery clearance/quarantine and stale MIX retirement need explicit identity-locked, durable-state and real OFF scenario tests.
5. A live integrated incident timeline and physical post-stop evidence have NOT been collected. 120 focused offline tests PASS; broader safety selection running separately.

Release HOLD until exact source candidate, current production preimage, D145 profile and fresh direct ESP Native/HA corroboration are established.
## 2026-11-08 — Safety package decomposition (source only)

On feature branch, moved the two previously separate production watchdog loops out of runtime/production_runtime.py. ProductionRuntimeLifecycle now schedules exactly one run_safety_watchdogs(app) task from runtime/safety/watchdog_runtime.py, preserving 10s soft and 30s communication polling. Pure communication timeout policy is runtime/safety/communication_watchdog.py with the canonical 300s WATCHDOG_TIMEOUT_S; polling cadences are typed in runtime/safety/communication_variables.py. A latched soft-watchdog incident suppresses the competing communication OFF effect; existing ExecutionPort remains the single physical executor. No additional observer task, timing authority, hardware command, or lease change.

Managed pure classifications extracted from the large managed guard: runtime/safety/critical_telemetry.py, runtime/safety/electrical_envelope.py, and runtime/safety/foreign_output.py. Existing methods delegate only; the guard remains the sole incident epoch/effects owner. Contract tests of watchdog source ownership migrated from legacy production runtime AST to new modules (old loops truly removed). Focused pre-foreign-extraction cohort 86 PASS; post-foreign-extraction cohort 58 PASS; broader tests and final module relocation pending. Physical node104 and ESP untouched. Source not deployed.
