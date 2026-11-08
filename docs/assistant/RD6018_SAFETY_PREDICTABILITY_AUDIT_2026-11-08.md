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
1. Recovery epoch: managed_runtime_safety.get_all_live() returns immediately for idle Output OFF + no active controller without calling _clear_telemetry_grace(). A previous pending incident may survive software session retirement; add a targeted transition regression and reset only after genuinely safe idle (do not reset when hardware Output is unknown).
2. Competing watchdog loops: managed guard, soft_watchdog_loop and watchdog_loop all exist; timeout comparisons (300s managed, 360s soft heartbeat tolerance) and source clocks differ. Audit the exact flow on interrupted/partial callbacks and ambiguous Output; keep one semantic authority without loss of fail-closed behavior.
3. Single implausible battery voltage sample: trace ESP Modbus register, scaling, Native callback provenance, timestamps, and mixing with UI values. Do not suppress real undervoltage or relax hardware OVP/OCP; distinguish invalid observation from confirmed physical condition using source evidence.
4. STOP after persistent lack of fresh Native R18 remains fail-closed. Recovery clearance/quarantine and stale MIX retirement need explicit identity-locked, durable-state and real OFF scenario tests.
5. A live integrated incident timeline and physical post-stop evidence have NOT been collected. 120 focused offline tests PASS; broader safety selection running separately.

Release HOLD until exact source candidate, current production preimage, D145 profile and fresh direct ESP Native/HA corroboration are established.