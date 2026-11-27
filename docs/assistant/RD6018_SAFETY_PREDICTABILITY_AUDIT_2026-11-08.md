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

## 2026-11-08 — Safety module relocation and one-observer acceptance (SOURCE ONLY)

Branch `feature/main-mix-countdown-display`, source migration continuing from `e627346`. Actual production guard classes relocated without shadow modules or import compatibility facades: `runtime_safety.py` -> `runtime/safety/runtime_guard.py`, `runtime_safety_strict.py` -> `runtime/safety/strict_guard.py`, `managed_runtime_safety.py` -> `runtime/safety/managed_guard.py`. Production/bootstrap/tests migrated to exact new module imports. Pure concerns split to sibling `critical_telemetry.py`, `electrical_envelope.py`, `foreign_output.py`, `communication_watchdog.py`, and existing freshness/recovery modules. `ProductionRuntimeLifecycle` starts one `run_safety_watchdogs` observer, no old watchdog loops in production runtime; preserved soft 10s / communications 30s cadence and 300s grace. Latched soft incident suppresses competing communication OFF; execution owner remains unchanged.

Pinned D061 historical acceptance overlay `tools/acceptance_guard/adapters.py` was restored byte-identically, SHA256 `d0f8a85772833e81e68c2c3291415beb7b9a9c02aa0b0d849e0acec84923e66c`; no re-sealing. After staging exact new source paths for source inventory, architectural/physical-call inventory 24 PASS, D061/ESP/migration regression 82 PASS. Full WSL suite after module relocation and overlay restoration: **3064 PASS, 3 SKIPPED, 6 WARNINGS, 0 FAIL, exit 0, 388.65s** (log `/tmp/rd6018_full_safety_modularization_final_20261108.log`). Found and fixed D124 release risk classification: every `runtime/safety/` path is now a Python control change requiring targeted validation and fresh Native OFF; historical classifications remain recognized. Post-classifier focused tests 16 PASS. No physical ESP/RD/HA action or node104 deployment.

Any follow-up movement of edge-lease or external-temperature modules requires a new exact source test run and must not be represented by these previous full-suite results.

## 2026-11-08 — Safety guard relocation source acceptance

Relocated runtime_safety.py, runtime_safety_strict.py and managed_runtime_safety.py into runtime/safety/{runtime_guard,strict_guard,managed_guard}.py without shadow compatibility files. One safety watchdog task replaces two production-runtime observers; critical telemetry, electrical envelope, foreign Output and communication timeout have separate pure policy modules. All physical effects still use the existing ExecutionPort. Exact D061 overlay remains original SHA256 d0f8a85772833e81e68c2c3291415beb7b9a9c02aa0b0d849e0acec84923e66c; never re-sealed. WSL full suite: **3064 PASS / 3 SKIP / 6 warnings / 0 FAIL**, 388.65s; log /tmp/rd6018_full_safety_modularization_final_20261108.log. D124 release-control classification now covers all runtime/safety/ changes; targeted 16 PASS. No node104 deployment or physical operation.

## 2026-11-08 — Safe Output decomposition (source-only candidate)

After commit `be7e908` (edge lease and temperature modules, full 3065 PASS/3 SKIP), removed the mixed root `safe_output.py`. Its unchanged `SafetyPolicy`, `TelemetrySnapshot`, `snapshot_from_live`, `SafetySupervisor` and decisions now live only in `runtime/safety/output_policy.py` (pure safety). The existing `SafeOutputCoordinator` and its V/I/OVP/OCP readback/verified Output-enable transaction now live only in `application/safe_output_coordinator.py` (effects through existing adapter; no new executor). Updated imports and exact actuator inventory; D124 release classifier includes both new paths. Historical D061 overlays remained untouched. Found logger import error with three red snapshot tests, fixed without changing safety rules; focused tests 82 PASS. Initial full suite 3064 PASS, 1 FAIL in an architecture test still treating all application paths as non-executors; narrowed exemption to three explicitly identified execution-boundary files, 22 architectural tests PASS. Final full suite is running separately; **do not claim acceptance or deploy until exit 0 is established**. No node104 or ESP actions.

## 2026-11-08 — safe_output source-only decomposition

After commit be7e908 (edge lease/temperature: 3065 PASS, 3 SKIP), removed mixed safe_output.py: pure SafetyPolicy/TelemetrySnapshot/SafetySupervisor/snapshot_from_live now in runtime/safety/output_policy.py; existing SafeOutputCoordinator and verified enable transaction now in application/safe_output_coordinator.py. Single execution path retained; D124 and strict actuator-call inventory updated. Three telemetry test failures from moved logger fixed; focused 82 PASS. Initial full suite 3064 PASS, 1 architectural source-location test FAIL. Narrowly updated static inventory exemption to specifically named preexisting execution files plus new coordinator; 22 architectural tests PASS. Final full suite still pending, release HOLD. No node104 or ESP actions.

## 2026-11-08 — Safe Output split accepted in source

Former mixed root `safe_output.py` removed. Pure `SafetyPolicy`, `SafetySupervisor`, `TelemetrySnapshot` and read-only `snapshot_from_live` now only `runtime/safety/output_policy.py`; existing verified V/I/OVP/OCP/readback/Output transaction `SafeOutputCoordinator` now only `application/safe_output_coordinator.py`. No second executor or altered numeric policy. Updated production imports, D124 release admission, exact actuator inventory, and narrow architecture allow-list of established execution files. Red regression (3 logger errors) fixed by retaining diagnostic logging in the policy; architectural location regression fixed with exact executor-path exemption, without weakening other source checks. Full WSL suite on staged tree: **3065 passed, 3 skipped, 6 warnings, 0 failed, exit 0, 385.31 seconds**; log `/tmp/rd6018_safe_output_full_final_20261108.log`. Existing production remains untouched; deployment requires fresh node104 read-only proof, paired D145 profile and new exact archive.
