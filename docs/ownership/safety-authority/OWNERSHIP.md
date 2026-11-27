# Safety Authority — ownership contract

**Status: operating boundary documented; department functional-owner approval OPEN.** Primary ADRs remain the decision authority. This file records accepted decisions and conservative inventory classifications; placement under this department does not assign ownership.


### B902 current P1 scope reconciliation (2026-11-25)
AD083 D061 function scopes are accepted with the boundaries recorded in `docs/RD6018_AD083_CONTROL_ADOPTION_OWNER_DECISIONS_2026-11-15.md`. The file has no whole-file owner. D062 MIX authority remains separate in `rd_managed_mix.py`. The current 517-row source registry and historical 82-path subset were reconciled from B900 evidence; no registry-wide reanalysis was repeated.

## Responsibility and boundaries

- Planned responsibility: Safety Authority as defined in `docs/RD6018_MODULARIZATION_EXECUTION_PLAN_P0-P9_2026-11-17.md` (department table, lines 12–24).
- The production functional owner, cross-department state/decision owner map, and final whole-file owner assignments remain OPEN unless an exact primary ADR below approves the bounded responsibility.
- Interfaces are the existing function/module APIs cited per path; this contract authorizes no file moves, API changes, new state, side effect, or compatibility shim.
- Consumers, callsites, side effects, and dependencies are summarized from the AD148AN source/call graph review. Verify against current source before implementation; this checkout has extensive dirty WIP.

## State, decisions, and interfaces

- State and decisions remain with their specifically cited existing owners. Only a row still classified CANDIDATE / NOT APPROVED is unapproved; APPROVED path rows are limited to the cited primary ADR scope. Cross-department orchestration stays with existing callers and ports.
- Inputs/outputs follow current callable signatures and DTOs; no inferred API expansion is approved. No UI/Application direct hardware access; physical effects remain behind existing execution boundary.

## Consumers, effects, dependencies, tests, migration

- Exact source paths and caller/test evidence are listed in the inventory below. These paths are evidence pointers, not authorization to change them.
- Migration constraint: preserve current public imports, persisted formats, operation order, safety/verified-OFF semantics, and caller behavior. Any future extraction needs a separate bounded ADR and focused parity tests.
- Risk: matrix source observations came from a dirty checkout; candidate recommendations are not approvals, and some rows lack production reachability evidence.

## 2026-11-25 — B900 current functional scope reconciliation

The B900 review records accepted function/module scopes against current production callers and the cited primary decisions. These entries do not imply blanket department sign-off or whole-file approval. The current 517-row source registry and historical 82-path approval subset were reconciled from existing B893/B899 ledgers; categories were mapped without replaying or double-counting prior rows. B902 accepts the bounded D061 function scopes in `rd_managed_adoption.py` after false/exception/cancellation verification; its whole-file owner remains intentionally blank, and D062 MIX authority remains in `rd_managed_mix.py`.

## Path assignment register

| Classification | Path | Primary ADR / scope | Caller evidence / tests |
|---|---|---|---|
| REGISTER NOTE | — | Individual path decisions appear below; department functional-owner sign-off remains OPEN. |
| BOUNDED AD014 — whole-file owner remains blank | `runtime/charge/strategy/adopted_mix_admission.py` | AD014, lines 3, 10 — already-running MIX admission predicate only; whole-file owner remains blank. | Pure chemistry/current/prior-budget validation; called by rd_managed_mix.py. Tests: `tests/test_modularization_adopted_mix_admission.py` |
| ACCEPTED FUNCTION SCOPE — whole-file owner blank | `application/execution_intent/policy.py` | `ExecutionSafetyPolicy.validate` is the pure data-only allow/limit/deny rule over supplied intent and configured bounds. Application owns use-case sequence; ExecutionPort/Physical Execution owns effects. No whole-file ADR assignment is inferred. | Exported through `application.execution_intent`; used at the existing execution-intent validation boundary. Tests: `tests/test_d123_p4_recipe_target_policy.py`, `tests/test_execution_port_policy_boundary.py`, `tests/test_link_session_recovery_policy.py` |
| APPROVED (whole-file final owner) | `runtime/charge/strategy/main_guard_admission.py` | AD066 line 8 — No journal write or physical output. | Read-only MAIN Guard admission contract and typed result; consumed by Application runtime. Tests: `tests/test_main_guard_admission.py` |
| APPROVED (whole-file final owner) | `runtime/safety/critical_telemetry.py` | AD082 line 12 — Acquisition/provenance remain Telemetry. | Pure supplied-value classification consumed by managed guard critical telemetry check. Tests: No path-specific test identified in this bounded matrix; focused test evidence remains OPEN. |
| MIXED-SCOPE | `runtime/safety/edge_lease.py` | AD082 line 10 — Policy/lifecycle approved; transport invocation excluded to Physical Execution. | Lease state/lifecycle and transport-facing _press/edge invocation methods; constructed in strict guard path. Tests: `tests/test_runtime_edge_lease.py` |
| DORMANT / TEST-ONLY — no production owner | `runtime/safety/engine.py` | AD082 conservative status — current imports consume `SafetyDecision` type only; no production engine construction/evaluation caller exists. Do not activate it. Existing production safety remains with RuntimeSafetyGuard/ManagedGuard and output_policy. | Evaluate APIs are exercised by isolated unit tests only. Tests: `tests/test_battery_fault_engine.py`, `tests/test_recipe_engine.py`, `tests/test_user_recipe_engine.py` |
| MIXED-SCOPE | `runtime/safety/managed_guard.py` | AD056 master plan lines 983, 964–980; AD082 lines 27–33 — Existing Safety coordinator; inherited/execution seams do not confer adapter/Output ownership. | Managed guard inherits strict guard and handles telemetry recovery, thermal integrity, admission, trips and containment; production installer exists. Tests: No path-specific test identified in this bounded matrix; focused test evidence remains OPEN. |
| MIXED-SCOPE | `runtime/safety/output_policy.py` | AD082 line 11 — Effects and adapter execution are explicitly excluded. | DTOs, snapshot normalization and SafetySupervisor verdicts; consumed by preflight/coordinator/execution path. Tests: No path-specific test identified in this bounded matrix; focused test evidence remains OPEN. |
| MIXED-SCOPE | `runtime/safety/strict_guard.py` | AD056 master plan lines 982, 964–980; AD082 boundary — Safety guard with physical-facing wrappers; retain Physical Execution boundary. | Inherits runtime guard and wraps lease/live reads/setpoints/output operations; managed guard subclasses and installs it. Tests: No path-specific test identified in this bounded matrix; focused test evidence remains OPEN. |
| MIXED-SCOPE | `runtime/safety/telemetry_recovery.py` | AD082 line 13 — Telemetry owns source facts/freshness; guard/recovery owns lifecycle and quarantine. | Pure unsafe-observation and callback-recovery classifiers consumed by managed guard. Tests: No path-specific test identified in this bounded matrix; focused test evidence remains OPEN. |
| MIXED-SCOPE | `runtime/safety/temperature_integrity.py` | AD082 line 14; AD143 line 10 separates thresholds — Durable persistence mechanism is an adapter detail; thermal thresholds are separately owned. | Integrity monitor, anomaly/latch/re-arm state; consumed by managed guard. Tests: No path-specific test identified in this bounded matrix; focused test evidence remains OPEN. |
| APPROVED (whole-file final owner) | `runtime/safety/thermal_variables.py` | AD143 line 10 — Threshold configuration only; no observer sequencing or monitor lifecycle. | Typed Manual external-battery thermal thresholds consumed by Manual observer path. Tests: No path-specific test identified in this bounded matrix; focused test evidence remains OPEN. |

## Unassigned decision rules

- **APPROVED:** individually APPROVED rows are approved only within the cited primary ADR scope.
- **CANDIDATE / NOT APPROVED:** only rows still marked CANDIDATE / NOT APPROVED remain unresolved; B900 resolved the six reviewed paths at their current bounded scopes.
- **BOUNDED AD014:** preserve the five exact function/state boundaries and keep whole-file final owner blank.
- **MIXED-SCOPE / ADAPTER/COORDINATOR / INSUFFICIENT-EVIDENCE:** retain their documented function scopes; do not infer whole-file owners.
- **HOLD:** `rd_managed_adoption.py` retains AD083 function boundaries and its concrete D061 verified-OFF containment gap; no whole-file owner is assigned.

## Sources

- `docs/RD6018_MODULARIZATION_EXECUTION_PLAN_P0-P9_2026-11-17.md` — canonical department names, P1 checklist and status.
- `.recipe-studio-local/REPORT_MOD_P1_AD148AN_FINAL_OWNER_MATRIX_20261117.md` — 81-path evidence/classification matrix; recommendations only.
- `.recipe-studio-local/REPORT_RD6018_P1_FINAL_OWNER_PERSISTENCE_RESOLUTION_20261118.md` — 37/5/39 reconciliation and approved persistence model.
- Exact primary ADR references are recorded per path above; ADR text, not this summary, governs scope.


### 2026-11-19 — P7 data_logger batch 29 boundary evidence

The 656-line production `data_logger()` cycle was reviewed for a safe telemetry/recovery extraction. No owner was assigned: AD082's `runtime/safety/telemetry_recovery.py` scope is the existing pure unsafe-observation/callback-recovery classifier, and telemetry normalization does not own Native reconnect lifecycle or whole-cycle admission. The fake recovery-barrier regression is recorded in `.recipe-studio-local/REPORT_RD6018_P7_DATA_LOGGER_BATCH29_20261119.md`; this note does not extend the approved API or alter the mixed-scope classification.


## 2026-11-19 — independent P7 data_logger boundary batch-29 acceptance

- HOME-PC Codex Luna `rd6018-mod-p7-data-logger-split-luna-20261119-29` exited 0 and emitted R7.2 event `c0a608b50baa49f9ac5c2cc54eff2ca3`. Existing `data_logger()` 656-line single-cycle loop and all production source unchanged: existing owner contracts do not authorize splitting Native reconnect admission across Safety/Telemetry/Application. No invented secondary control loop or manager. Added source/fake regression evidence for physical read routing, Native outage/unknown/pending marker deferral, no tick/sample or Output/V/I writes and one lifecycle loop.
- Independent Windows project `.venv` original six-module source/recovery cohort before change **44 PASS + 32 subtests**. Expanded tests initially exposed shared `_run_one_cycle()` helper tuple mismatch in AD155 tests after appending an `add_record` spy; corrected AD155 fixture unpacking, with unchanged assertions. Final six-module Windows cohort **46 PASS + 35 subtests PASS**, exit 0; targeted recovery module **4 PASS + 3 subtests**. `py_compile` and `git diff --check` PASS. Linux collection missing `python-dotenv`, not behavior FAIL or PASS.
- P7 single-loop recovery and provenance source/fake subgate ACCEPTED, but no production extraction approved. Original P0–P9 checkbox/status unchanged: P7 PARTIAL, P8 physical/full release HOLD, AD083/AD148 whole-file HOLD. No node104/live HA/ESP, Output, setpoints, lease, firmware, service, deployment or remote push.
