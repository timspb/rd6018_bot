# Physical Execution — ownership contract

**Status: operating boundary documented; department functional-owner approval OPEN.** Primary ADRs remain the decision authority. This file records accepted decisions and conservative inventory classifications; placement under this department does not assign ownership.


### B902 current P1 scope reconciliation (2026-11-25)
AD083 D061 function scopes are accepted with the boundaries recorded in `docs/RD6018_AD083_CONTROL_ADOPTION_OWNER_DECISIONS_2026-11-15.md`. The file has no whole-file owner. D062 MIX authority remains separate in `rd_managed_mix.py`. The current 517-row source registry and historical 82-path subset were reconciled from B900 evidence; no registry-wide reanalysis was repeated.

## Responsibility and boundaries

- Planned responsibility: Physical Execution as defined in `docs/RD6018_MODULARIZATION_EXECUTION_PLAN_P0-P9_2026-11-17.md` (department table, lines 12–24).
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
| ADAPTER/COORDINATOR | `runtime/physical/connectors/esp_direct.py` | AD006 lines 3, 11 — AD006 explicitly says adapter classification does not confer exclusive physical-command authority or bypass permission. | Delegating ESP Native connector selected through existing connector factory/facade. Tests: No path-specific test identified in this bounded matrix; focused test evidence remains OPEN. |
| MIXED-SCOPE | `application/execution_port.py` | AD056, master plan lines 977–978 — Physical boundary approval does not make all embedded decisions one owner; retain Safety policy separation. | Transaction orchestration spans policy evaluation, adapter calls and verification. Tests: `tests/test_execution_port_policy_boundary.py`, `tests/test_production_start_execution_port.py` |
| APPROVED FUNCTION/MODULE SCOPE — Physical Execution | `application/main_guard_transaction.py` | AD071 primary decision table explicitly records this as ALREADY APPROVED BY AD056; AD071 reaffirms the existing assignment. Scope is the existing MAIN Guard transaction through ExecutionPort. Safety protection, controller state and persistence remain delegated owners. | Invoked by existing `application/execution_port.py` methods and composed by `application/main_guard_runtime.py`. Tests: `tests/test_main_guard_transaction.py` |
| ADAPTER/COORDINATOR | `application/safe_output_coordinator.py` | AD056, master plan lines 977–978 — Coordinator is not a new policy owner; no separate final owner assignment. | Coordinates existing SafetySupervisor and verified Output transaction. Tests: No path-specific test identified in this bounded matrix; focused test evidence remains OPEN. |

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

## 2026-11-19 — Emergency OFF preemption batch 08

- The current contract remains one app-scoped `ExecutionPort` and `GuardExecutionOwnerLock` for normal actions; `ExecutionPort.request_emergency_off()` reaches the existing Safety owner without awaiting the app lock. The Safety owner retains its existing OFF serialization/readback path.
- Fake-only event-barrier coverage was added to `tests/test_guard_execution_owner_lock.py` for separate-task preemption, false/exception outcomes and absent receipt. The suite is not yet accepted: Linux Python 3.12 collection is blocked by missing `python-dotenv`; native Windows host run is pending. Evidence: `.recipe-studio-local/REPORT_RD6018_P3_EMERGENCY_OFF_BATCH08_20261119.md`.
- This note changes no whole-file owner assignment, API, lock, physical behavior or acceptance status. P3 software and physical acceptance remain HOLD.

## 2026-11-18 — P7 HassClient dual-resource close and connector façade boundary

- R7.2 Codex source audit `rd6018-p7-hass-api-connector-facade-audit-20261118-01` found no justified split of `hass_api.py`: it is the compatibility façade for configured connector delegation and optional HA REST sidecar, not a second Native subscription/receipt or physical execution owner. Report `.recipe-studio-local/REPORT_RD6018_P7_HASS_API_FACADE_AUDIT_20261118.md`; existing whole-file/department ownership approval remains OPEN.
- Concrete close-path bug: `HassClient.close()` returned immediately after `self._physical_backend.close()` and skipped separate `self._session.close()` when a backend without `get_state()` caused HA sidecar REST session creation. Independent Windows project Python 3.14.5 RED: `tests/test_physical_connector_composition.py::test_close_releases_physical_backend_and_ha_sidecar_session` failed (`session.closed=False`).
- Narrow correction only in `hass_api.py::close`: close configured physical backend and, in `finally`, close an independently open HA REST sidecar even if backend close raises. No new state/DTO/transport owner, no physical control/lease/receipt/stop logic change.
- Added two fake-only cases in `tests/test_physical_connector_composition.py`: normal dual-resource closure and HA sidecar closure despite synthetic backend-close exception. Independent Windows Python 3.14.5 **GREEN: 34 PASS** across five modules (`test_physical_connector_composition`, `test_hass_fallback_freshness`, `test_v3_independent_connectors`, `test_v3_physical_bridge_discovery`, `test_production_lifecycle_shutdown`), exit 0 (9.62s). Prior post-fix 33 PASS cohort superseded by 34 PASS.
- Scoped `git diff --check` PASS; existing unrelated dirty hass_api changes preserved. HEAD `3c69255`, staged=0, broad worktree WIP retained. No HA/ESP/network/node104/hardware/Output/setpoint/lease/firmware/deploy.
- **P7 HassClient dual-resource shutdown subgate ACCEPTED (source/fake). P7 overall OPEN; P8 release/physical HOLD.** Next: P7 real dynamic composition patches/duplicated owners with test-backed scope, not mechanical façade splitting.

## 2026-11-19 — P7 registered unmanaged Output OFF callback regression candidate (batch 10)

- Run `rd6018-mod-p7-runtime-facade-decomposition-luna-20261119-10`, starting HEAD `4102b347`, branch `feature/main-mix-countdown-display`. Current callback sequence remains `rd_ownership_recovery._ownership_output_off → existing manager.guard verified OFF → existing lease disarm → operator confirmation`; no production source or physical owner changed.
- Added fake-only registered-handler coverage in `tests/test_rd_ownership_recovery.py`: success follows verified OFF then disarm; verified-OFF exception returns alert and prevents disarm/success response. RED collection was attempted but blocked before test execution by missing Linux `aiogram`; do not claim RED/GREEN acceptance. Python 3.12 `py_compile` and `git diff --check` pass. Native Windows cohort command and limitations are in `.recipe-studio-local/REPORT_RD6018_P7_RUNTIME_DECOMPOSITION_BATCH10_20261119.md`.
- No source ownership move was justified: runtime functions already delegate under the existing P7 crosswalk; HassClient dual-resource close fix already has prior RED/GREEN evidence; AD080 remains NO FILE-LEVEL APPROVAL. This regression candidate is pending host acceptance. P7 OPEN, P8 HOLD; AD148T final owner blank, existing P3/P4 acceptance unchanged. No node104, HA/ESP, Output, setpoint, lease, firmware, service, deployment or remote Git action.


## 2026-11-18 — P7 transport outage classification ownership extraction

- P7 real boundary: `runtime/production_runtime.py` previously owned two transport/safety exception classifiers while also composing application runtime and physical recovery call sites. Moved unchanged `_is_physical_transport_error` and `_is_recoverable_link_boundary_error` into `runtime/physical/transports/error_policy.py`. Production runtime retains direct compatibility imports and both existing call sites. The new module is pure exception classification: no I/O, effect owner, output command, manager, state machine or alternate safety authority.
- Transport distinction preserved: connection and aiohttp errors and explicitly recognized link failure messages are transport outages; a bare TimeoutError can be an unconfirmed *safety verification*, not a link failure. An accepted OFF with unconfirmed switch state remains separately recoverable without falsely asserting physical OFF.
- Added explicit owner identity, aiohttp ClientError, and bare safety TimeoutError regression cases to `tests/test_transport_outage_policy.py`. Independent Windows project Python venv six-module cohort: **49 PASS**, exit 0; `py_compile` and `git diff --check` PASS.
- P7 transport-classification subgate **ACCEPTED/PASS**, P7 overall still OPEN. P3 physical proof and P4 restart/recovery not claimed complete. BW600 must later implement independently validated actual-load and switch feedback, not infer remote Load OFF from an error class or current=0. No node104/HA/ESP/hardware/deploy/GitHub changes.


## 2026-11-19 — independent P3 Emergency OFF preemption batch-08 acceptance

- HOME-PC Codex Luna run `rd6018-p3-emergency-off-preemption-luna-20261119-08` completed (exit=0); R7.2 event `c77c0a7054624d118de16e008f859943` was emitted. The executor's sandbox route-inspection error is not a host-run failure.
- Existing `tests/test_guard_execution_owner_lock.py` gained three fake-only event-controlled async cases: emergency OFF completes in another task while a normal setter still holds the GuardExecutionOwnerLock; false/exception OFF outcomes do not report success; missing OFF receipt is not fabricated. No production code/physical owner changed.
- Independent native Windows project-venv six-module cohort: **47 PASS + 2 subtests PASS**, exit 0. D074 does not collect on Windows because its fixture imports Unix-only `fcntl`; independently ran it on Linux Python 3.12 using `PYTHONPATH=tools:.`: **13 PASS**, exit 0. `py_compile` and `git diff --check` PASS. **P3 emergency OFF preemption SOFTWARE/FAKE subgate ACCEPTED**. Hardware emergency OFF, causal post-command readback, live Native receipt, P3 production/physical and P8 release remain HOLD.
- No node104, charging Output, HA/ESP live access, setpoint, lease, firmware, deploy or remote Git operation.


## 2026-11-19 — P7 batch-10 independent acceptance

- HOME-PC Luna run `rd6018-mod-p7-runtime-facade-decomposition-luna-20261119-10` exit=0; R7.2 event `2ea10d8a314246f9820ad97ab898e602` ACK first attempt. Independent native Windows project venv five-module cohort **58 PASS**, exit=0.
- Two fake-only tests exercise actual registered unmanaged Output OFF handler: verified OFF precedes lease disarm and success acknowledgement; verified-OFF failure returns alert without disarming or reporting success. No production source/physical changes. Bounded P7 callback software subgate ACCEPTED; P7 overall OPEN, AD080 whole-file owner HOLD, P8 and physical acceptance HOLD.


## 2026-11-19 — P2 Native callback provenance batch 11

- Active `ESPHomeTransport` readback/receipt contract is reached through the existing connector and HassClient owner; it does not create another physical command owner. Each subscription callback is now bound to the exact connected client and generation. A callback from a replaced client is ignored before it can mutate state or receipt evidence. Fake RED/GREEN regression is `tests/test_esp_home_transport.py::test_late_callback_from_old_connection_cannot_satisfy_native_baseline`; it asserts unknown R18, ESP Native source, current generation, absent subscription timestamp, and retained reconnect block.
- Existing active ON/OFF/V/I dispatch still crosses the app-scoped `application.ExecutionPort` and Safety/HassClient boundary. No connector API, department assignment, or physical behavior contract was otherwise changed. The all-P2 contract and P8 physical gates remain open/hold. See `.recipe-studio-local/REPORT_RD6018_P2_CONTRACT_PROVENANCE_BATCH11_20261119.md`.


## 2026-11-19 — independent P2 ESP Native reconnect provenance acceptance, batch 11

- HOME-PC Codex Luna run `rd6018-mod-p2-contract-provenance-luna-20261119-11` exit=0; completion event `814ce29513a9435cbe799e40f2b19936` was emitted on this chat's R7.2 route. ACK was not yet verified at the time of this independent review; do not infer it from a different event.
- Reproduced RED for a late callback from the replaced ESP Native client: after reconnect it could refill current-generation R18 evidence cache. Existing `ESPHomeTransport` now binds subscription callback to source client+generation and ignores obsolete callbacks. Regression crosses `ESPHomeTransport → ESPDirectConnector → HassClient.get_native_physical_output_report` and confirms unknown R18 without fresh new-generation callback.
- Independently ran native Windows project venv eight-module transport/receipt/physical connector/source suite: **88 PASS, 17 subtests PASS, one Linux-only D106 test deselected** due to Unix-only `fcntl`. D106 was separately attempted in bare Linux Python but blocked on missing `aioesphomeapi`; its PASS must not be inferred. Executor ran 42 fake tests GREEN with temporary import stubs, which is not replacement for full platform test. Python compile and Git diff check PASS.
- **P2 Native callback provenance/reconnect source/fake subgate ACCEPTED.** P2/P6 full integrated contracts, P3 physical OFF/Native receipt, P8 full Windows/Linux and production release remain OPEN/HOLD. No node104, live HA/ESP, battery, Output, setpoint, lease, firmware, deploy or push.

## 2026-11-19 — P7 ESP Native reconnect/lifecycle provenance, batch 27

Existing transport owner captures connection-close client+generation and ignores late events from replaced clients. Explicit close requires a complete callback baseline on the next connection; incomplete reconnect keeps Native reads unknown and ON admission blocked. Fake coverage is pending independent Windows execution; Linux import is blocked by missing `aioesphomeapi`. No physical/live acceptance. See `.recipe-studio-local/REPORT_RD6018_P7_NATIVE_RECONNECT_BATCH27_20261119.md`.


## 2026-11-19 — independent P7 Native reconnect batch-27 acceptance

- HOME-PC Codex Luna `rd6018-mod-p7-native-reconnect-luna-20261119-27` completed exit 0; R7.2 event emitted. Existing `runtime/physical/transports/esp128.py` fixes stale old-client/old-generation close callback invalidating the current subscription, and invalidates Native readback after close until current-generation callback baseline is complete. No HA fallback or actuator authority change.
- Independent native Windows project .venv targeted ESP Native/HA/physical connector cohort **51 PASS + 5 subtests**, 1 known D106 test deselected due to pre-existing Unix-only `fcntl` import. Expanded Native+HA+production lifecycle/entrypoint/D061 registered callbacks cohort **81 PASS + 22 subtests**, same 1 D106 deselected, exit 0. Compile and `git diff --check` PASS. Do not count excluded D106 as PASS or whole-suite acceptance.
- P7 reconnect source/fake subgate ACCEPTED; P7 overall remains PARTIAL, P8 full physical/release HOLD, AD083/AD148 final-owner HOLD. No node104/live HA/ESP, Output, setpoints, charging, lease, firmware, deployment or remote push.
