# Telemetry / Evidence — ownership contract

**Status: operating boundary documented; department functional-owner approval OPEN.** Primary ADRs remain the decision authority. This file records accepted decisions and conservative inventory classifications; placement under this department does not assign ownership.


### B902 current P1 scope reconciliation (2026-11-25)
AD083 D061 function scopes are accepted with the boundaries recorded in `docs/RD6018_AD083_CONTROL_ADOPTION_OWNER_DECISIONS_2026-11-15.md`. The file has no whole-file owner. D062 MIX authority remains separate in `rd_managed_mix.py`. The current 517-row source registry and historical 82-path subset were reconciled from B900 evidence; no registry-wide reanalysis was repeated.

## Responsibility and boundaries

- Planned responsibility: Telemetry / Evidence as defined in `docs/RD6018_MODULARIZATION_EXECUTION_PLAN_P0-P9_2026-11-17.md` (department table, lines 12–24).
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
| APPROVED (whole-file final owner) | `runtime/charge/evidence/adopted_mix_prior_age.py` | AD010 lines 11, 13–14; AD010A line 7 — No history acquisition, adoption, timer anchor or actuation. High confidence. | Pure prior-age projection/selection; called by rd_managed_mix.py, rd_managed_mix_adoption.py, and D062 test control. Tests: `tests/test_modularization_adopted_mix_prior_age.py` |
| BOUNDED AD014 — whole-file owner remains blank | `runtime/charge/evidence/adopted_mix_sample_decision.py` | AD014, lines 3, 8 — timestamp eligibility/coherent sample projection only; whole-file owner remains blank. | Timestamp eligibility and coherent sample projection; invoked from rd_managed_mix.py:633–647. Tests: `tests/test_modularization_adopted_mix_sample_decision.py` |
| BOUNDED AD014 — whole-file owner remains blank | `runtime/charge/evidence/adopted_mix_source_timestamp.py` | AD014, lines 3, 7 — selected metadata timestamp projection only; whole-file owner remains blank. | Projects selected HA-shaped metadata timestamps; called via rd_managed_mix.py:335–337, 632–635. Tests: No path-specific test identified in this bounded matrix; focused test evidence remains OPEN. |
| APPROVED (whole-file final owner) | `runtime/telemetry/snapshot.py` | AD008 lines 7, 9 — Carrier only; freshness and ESP authority excluded. | Frozen telemetry carrier; constructed by source.py, consumed by accumulator/history and recorder interface. Tests: `tests/test_d123_p4_diagnostic_snapshot_ownership.py`, `tests/test_operator_panel_snapshot_integration.py`, `tests/test_operator_snapshot_provider.py` |
| APPROVED (whole-file final owner) | `ha_history.py` | AD006 line 10 — Not Native OFF proof or physical writer. | HA Recorder history adaptation and continuous-ON evidence; consumed by existing recovery/adoption paths. Tests: `tests/test_ha_history.py` |
| APPROVED (whole-file final owner) | `runtime/charge/evidence/recovery_plateau_observer.py` | AD062 lines 7–15, 19–23 — Evidence only; Application orchestrates and MAIN selects transition. | Bounded sample continuity observer called from application/charge_session_tick.py:259–303. Tests: `tests/test_recovery_plateau_observer.py` |
| APPROVED (whole-file final owner) | `runtime/charge/evidence/recovery_plateau_policy.py` | AD062 lines 7–15, 22–23 — Evidence calculation only; no stage dispatch or actuation. | Pure verdict calculation called by observer and consumed by MAIN path. Tests: `tests/test_recovery_plateau_policy.py` |
| APPROVED (whole-file final owner) | `runtime/telemetry/recorder.py` | AD078 lines 10, 30–31 — **No production construction/call found** by AD078. Narrow owner contract is approved, but runtime reachability is limited; do not infer active production use. | Interface and in-memory adapter record supplied snapshots. Tests: No path-specific test identified in this bounded matrix; focused test evidence remains OPEN. |

## Unassigned decision rules

- **APPROVED:** individually APPROVED rows are approved only within the cited primary ADR scope.
- **CANDIDATE / NOT APPROVED:** only rows still marked CANDIDATE / NOT APPROVED remain unresolved.
- **BOUNDED AD014:** preserve the five exact function/state boundaries and keep whole-file final owner blank.
- **MIXED-SCOPE / ADAPTER/COORDINATOR / INSUFFICIENT-EVIDENCE:** remain unassigned.
- **HOLD:** `rd_managed_adoption.py` remains under AD083 HOLD and is not part of the 81-row matrix.

## Sources

- `docs/RD6018_MODULARIZATION_EXECUTION_PLAN_P0-P9_2026-11-17.md` — canonical department names, P1 checklist and status.
- `.recipe-studio-local/REPORT_MOD_P1_AD148AN_FINAL_OWNER_MATRIX_20261117.md` — 81-path evidence/classification matrix; recommendations only.
- `.recipe-studio-local/REPORT_RD6018_P1_FINAL_OWNER_PERSISTENCE_RESOLUTION_20261118.md` — 37/5/39 reconciliation and approved persistence model.
- Exact primary ADR references are recorded per path above; ADR text, not this summary, governs scope.

## 2026-11-18 — P7 HassClient dual-resource close and connector façade boundary

- R7.2 Codex source audit `rd6018-p7-hass-api-connector-facade-audit-20261118-01` found no justified split of `hass_api.py`: it is the compatibility façade for configured connector delegation and optional HA REST sidecar, not a second Native subscription/receipt or physical execution owner. Report `.recipe-studio-local/REPORT_RD6018_P7_HASS_API_FACADE_AUDIT_20261118.md`; existing whole-file/department ownership approval remains OPEN.
- Concrete close-path bug: `HassClient.close()` returned immediately after `self._physical_backend.close()` and skipped separate `self._session.close()` when a backend without `get_state()` caused HA sidecar REST session creation. Independent Windows project Python 3.14.5 RED: `tests/test_physical_connector_composition.py::test_close_releases_physical_backend_and_ha_sidecar_session` failed (`session.closed=False`).
- Narrow correction only in `hass_api.py::close`: close configured physical backend and, in `finally`, close an independently open HA REST sidecar even if backend close raises. No new state/DTO/transport owner, no physical control/lease/receipt/stop logic change.
- Added two fake-only cases in `tests/test_physical_connector_composition.py`: normal dual-resource closure and HA sidecar closure despite synthetic backend-close exception. Independent Windows Python 3.14.5 **GREEN: 34 PASS** across five modules (`test_physical_connector_composition`, `test_hass_fallback_freshness`, `test_v3_independent_connectors`, `test_v3_physical_bridge_discovery`, `test_production_lifecycle_shutdown`), exit 0 (9.62s). Prior post-fix 33 PASS cohort superseded by 34 PASS.
- Scoped `git diff --check` PASS; existing unrelated dirty hass_api changes preserved. HEAD `3c69255`, staged=0, broad worktree WIP retained. No HA/ESP/network/node104/hardware/Output/setpoint/lease/firmware/deploy.
- **P7 HassClient dual-resource shutdown subgate ACCEPTED (source/fake). P7 overall OPEN; P8 release/physical HOLD.** Next: P7 real dynamic composition patches/duplicated owners with test-backed scope, not mechanical façade splitting.

## 2026-11-18 — P1/P2 provenance owner evidence

- AD014's approvals for `adopted_mix_source_timestamp.py` and `adopted_mix_sample_decision.py` remain bounded pure projections/eligibility decisions. They do not establish a whole-file owner, physical freshness proof, or a production normalized-evidence pipeline.
- The P6 provenance audit found `runtime.telemetry.source.normalize_live()` has no production caller. Its unit tests do not make it the live control/UI evidence authority; do not connect it as a second route without an explicit owner and consumer contract.
- `HA102Transport.get_live_values()` retains the accepted source-derived metadata/freshness correction. `get_snapshot()` fetch-time timestamp semantics remain outside this batch pending consumer and verification-policy review. Native callback receipt and HA readback remain distinct evidence sources.
- See `.recipe-studio-local/REPORT_RD6018_P0P9_BATCH_LUNA_20261118_01.md`. No final-owner value or new telemetry contract is approved here.

## 2026-11-18 — P2/P6 Native and HA evidence provenance audit

- Current call path: `HassClient.get_native_guard_pre_on_snapshot()` accepts this input only from an `ESPDirectConnector`, reads `get_all_live()`, and independently checks each Guard key's `esp_native_api` source, callback native type, monotonic subscription timestamp, and age. It never falls back to HA REST or a fetch timestamp. The optional lease callback is separately typed as `BinarySensorState`; it is not merged into the electrical readbacks.
- `ESPHomeTransport._on_state()` records callback receipt times/types and cache values by typed entity identity. Connection close advances the Native connection generation and clears caches/receipts; `get_live_values()` waits for a complete required callback batch after reconnect and otherwise retains ON fail-closed. Missing/invalid R18 maps to `switch="unknown"`; only an actual Native R18 report can support physical-output proof. Command terminal receipt remains separate from later physical readback.
- `HA102Transport.get_live_values()` separately carries HA source heartbeat (`last_reported`/`last_updated`), fetch time and age. Its diagnostic `get_snapshot()` uses the oldest required HA source heartbeat and marks incomplete metadata unknown. Neither is Native callback proof or command ACK. `runtime.telemetry.source.normalize_live()` has no production caller and remains a pure dormant helper.
- Reviewed `tests/test_esp_home_transport.py` reconnect/stale/type cases, `tests/test_esp_output_command_receipt.py`, `tests/test_main_guard_pre_on.py`, `tests/test_verified_off_contract.py`, `tests/test_hass_fallback_freshness.py`, and `tests/test_v3_telemetry_source.py`. No supported P2/P6 provenance defect requiring source change was demonstrated. This is a bounded non-finding, not full physical acceptance or final-owner approval.
- Focused Linux Python 3.12.3 `tests.test_v3_telemetry_source`: **3 PASS**. Combined invocation with `test_rd6018_telemetry` was blocked at import by missing `aiogram`; Native transport cohort was not executable here because `aioesphomeapi` is absent. Prior independent Windows Native tests remain the cited source/fake evidence; no fresh Native subscription was made.

## 2026-11-18 — P2 Native/HA provenance review (batch 03)

- No new telemetry owner or evidence contract is approved. `runtime.telemetry.source.normalize_live()` remains without a production caller.
- Keep Native callback receipt/type/generation, HA source timestamps/fetch age, action receipt, and post-command physical Native readback separate. No merge or adapter wiring was justified by current callers.
- Linux `tests/test_v3_telemetry_source.py`: **3 PASS**; Native adapter integration could not run in this environment because project dependencies are absent. Full evidence: `.recipe-studio-local/REPORT_RD6018_P8_P2_INTEGRATION_BATCH_20261118_03.md`.

## 2026-11-19 — D123 guarded restore failure-injection evidence

Batch 07 exercised the production caller of the existing Native read boundary with a fake backend read exception. `HassClient` returns unavailable evidence, and guarded restore remains blocked with candidate and canonical document unchanged. Cancellation at that same caller boundary is quarantined by the existing deferred-restore wrapper. This documents source/fake behavior only; no Native subscription or physical PASS is claimed. Independent Windows `.venv` execution is pending; see `.recipe-studio-local/REPORT_RD6018_P3P4_RECOVERY_BATCH07_20261119.md`.


## 2026-11-19 — Independent P3/P4 D123 batch-07 acceptance

- HOME-PC Luna run `rd6018-mod-p3p4-main-guard-recovery-luna-20261119-07` exit=0; R7.2 completion event `a0f9c4194cca441f8e4c7e3caa495b12` delivered from launcher (acknowledgement not yet independently observed in this acceptance record).
- Fake-only registered `StartupRecovery.replay_deferred_startup_restore` scenarios added: Native backend read fails with `OSError`, retaining guarded candidate/inactive controller/canonical bytes; Native pre-ON read cancelled, existing `SessionRecoveryGuard` quarantines with `deferred_restore_cancelled`, re-raises, and leaves the same candidate and bytes unmodified.
- Independently ran native Windows project-venv 10-module pytest suite: **83 PASS + 47 subtests PASS, 1 skipped**, exit 0. No production source changed. Python compilation/diff-check pass. **P4 D123 failure-injection subgate ACCEPTED**; physical Native pre-ON acceptance, broader P3 emergency OFF preemption, P8 full platform/release regression remain HOLD. No equipment/node104 access, no change to firmware, lease or charge outputs.


## 2026-11-19 — P2 Native callback provenance batch 11

- `runtime/physical/transports/esp128.py` previously stamped delayed old-client callbacks with the current transport generation, allowing a stale R18 callback to satisfy the reconnect baseline. The subscription callback now retains its actual client/generation provenance; mismatched callbacks do not enter cache/timestamps/receipt state. Unknown physical output readback keeps `source=esp_native_api`, the current generation, and no subscription timestamp.
- Fake-only `tests.test_esp_home_transport` and `tests.test_esp_output_command_receipt`: 42 PASS under the Linux test-only import stubs documented in the batch report. This is a source/fake provenance subgate, not Native physical acceptance, HA/Native freshness policy closure, nor final-owner approval.


## 2026-11-19 — independent P2 ESP Native reconnect provenance acceptance, batch 11

- HOME-PC Codex Luna run `rd6018-mod-p2-contract-provenance-luna-20261119-11` exit=0; completion event `814ce29513a9435cbe799e40f2b19936` was emitted on this chat's R7.2 route. ACK was not yet verified at the time of this independent review; do not infer it from a different event.
- Reproduced RED for a late callback from the replaced ESP Native client: after reconnect it could refill current-generation R18 evidence cache. Existing `ESPHomeTransport` now binds subscription callback to source client+generation and ignores obsolete callbacks. Regression crosses `ESPHomeTransport → ESPDirectConnector → HassClient.get_native_physical_output_report` and confirms unknown R18 without fresh new-generation callback.
- Independently ran native Windows project venv eight-module transport/receipt/physical connector/source suite: **88 PASS, 17 subtests PASS, one Linux-only D106 test deselected** due to Unix-only `fcntl`. D106 was separately attempted in bare Linux Python but blocked on missing `aioesphomeapi`; its PASS must not be inferred. Executor ran 42 fake tests GREEN with temporary import stubs, which is not replacement for full platform test. Python compile and Git diff check PASS.
- **P2 Native callback provenance/reconnect source/fake subgate ACCEPTED.** P2/P6 full integrated contracts, P3 physical OFF/Native receipt, P8 full Windows/Linux and production release remain OPEN/HOLD. No node104, live HA/ESP, battery, Output, setpoint, lease, firmware, deploy or push.


## 2026-11-19 — P7 HA REST read/freshness boundary, batch 23

`HassClient` remains the compatibility owner for the independent HA REST sidecar and its legacy entity map, session seam, bulk-to-concurrent-GET fallback, source timestamp metadata (`_ha_last_reported`, `_ha_last_updated`, `_ha_last_changed`, `age_s`) and status diagnostics. `HA102Transport` remains a distinct typed-config transport owner; its config/entity map/session and output shape do not match this legacy facade contract. The selected backend bypass in `HassClient.get_all_live()` and `canonicalize_live()` call are preserved. `runtime.telemetry.source.normalize_live()` remains dormant without a production caller. No existing compatible owner/API was identified for this entire bounded cluster, so batch 23 makes no source move and approves no new owner. Native output/Guard evidence remains ESP Native-only, independent from HA timestamps. See `.recipe-studio-local/REPORT_RD6018_P7_HASS_API_READ_BATCH23_20261119.md`; test collection limitations and remaining acceptance are recorded there. P7 remains open, P8 physical/release remains HOLD, AD148 final-owner remains HOLD.


## 2026-11-19 — independent HA sidecar batch-23 review and Windows evidence

- HOME-PC Codex Luna batch 23 completed exit 0 and emitted an R7.2 event. Source inspection confirmed ownership-blocked HA REST reader extraction; production code/tests unchanged. No merge of native read authority with HA REST sidecar.
- Independent Windows project .venv: 48 PASS + 5 subtests, 1 FAIL during import, due to node104_d106_readonly_projection importing Unix-only fcntl transitively from node104_d090_transaction. This is a D106 portability boundary, not evidence of ESP transport failure. No full Windows PASS claimed; D090 release/actuator contract untouched.
- P7 HA transport split remains BLOCKED by existing owner contracts, P7 PARTIAL; P8 full/physical release HOLD; AD148 whole-file HOLD; node104 HANDS_OFF. No live device or deployment actions.

## 2026-11-19 — P7 ESP Native reconnect/lifecycle provenance, batch 27

Existing transport owner captures connection-close client+generation and ignores late events from replaced clients. Explicit close requires a complete callback baseline on the next connection; incomplete reconnect keeps Native reads unknown and ON admission blocked. Fake coverage is pending independent Windows execution; Linux import is blocked by missing `aioesphomeapi`. No physical/live acceptance. See `.recipe-studio-local/REPORT_RD6018_P7_NATIVE_RECONNECT_BATCH27_20261119.md`.


## 2026-11-19 — independent P7 Native reconnect batch-27 acceptance

- HOME-PC Codex Luna `rd6018-mod-p7-native-reconnect-luna-20261119-27` completed exit 0; R7.2 event emitted. Existing `runtime/physical/transports/esp128.py` fixes stale old-client/old-generation close callback invalidating the current subscription, and invalidates Native readback after close until current-generation callback baseline is complete. No HA fallback or actuator authority change.
- Independent native Windows project .venv targeted ESP Native/HA/physical connector cohort **51 PASS + 5 subtests**, 1 known D106 test deselected due to pre-existing Unix-only `fcntl` import. Expanded Native+HA+production lifecycle/entrypoint/D061 registered callbacks cohort **81 PASS + 22 subtests**, same 1 D106 deselected, exit 0. Compile and `git diff --check` PASS. Do not count excluded D106 as PASS or whole-suite acceptance.
- P7 reconnect source/fake subgate ACCEPTED; P7 overall remains PARTIAL, P8 full physical/release HOLD, AD083/AD148 final-owner HOLD. No node104/live HA/ESP, Output, setpoints, charging, lease, firmware, deployment or remote push.


### 2026-11-19 — P7 data_logger batch 29 boundary evidence

The 656-line production `data_logger()` cycle was reviewed for a safe telemetry/recovery extraction. No owner was assigned: AD082's `runtime/safety/telemetry_recovery.py` scope is the existing pure unsafe-observation/callback-recovery classifier, and telemetry normalization does not own Native reconnect lifecycle or whole-cycle admission. The fake recovery-barrier regression is recorded in `.recipe-studio-local/REPORT_RD6018_P7_DATA_LOGGER_BATCH29_20261119.md`; this note does not extend the approved API or alter the mixed-scope classification.


## 2026-11-19 — independent P7 data_logger boundary batch-29 acceptance

- HOME-PC Codex Luna `rd6018-mod-p7-data-logger-split-luna-20261119-29` exited 0 and emitted R7.2 event `c0a608b50baa49f9ac5c2cc54eff2ca3`. Existing `data_logger()` 656-line single-cycle loop and all production source unchanged: existing owner contracts do not authorize splitting Native reconnect admission across Safety/Telemetry/Application. No invented secondary control loop or manager. Added source/fake regression evidence for physical read routing, Native outage/unknown/pending marker deferral, no tick/sample or Output/V/I writes and one lifecycle loop.
- Independent Windows project `.venv` original six-module source/recovery cohort before change **44 PASS + 32 subtests**. Expanded tests initially exposed shared `_run_one_cycle()` helper tuple mismatch in AD155 tests after appending an `add_record` spy; corrected AD155 fixture unpacking, with unchanged assertions. Final six-module Windows cohort **46 PASS + 35 subtests PASS**, exit 0; targeted recovery module **4 PASS + 3 subtests**. `py_compile` and `git diff --check` PASS. Linux collection missing `python-dotenv`, not behavior FAIL or PASS.
- P7 single-loop recovery and provenance source/fake subgate ACCEPTED, but no production extraction approved. Original P0–P9 checkbox/status unchanged: P7 PARTIAL, P8 physical/full release HOLD, AD083/AD148 whole-file HOLD. No node104/live HA/ESP, Output, setpoints, lease, firmware, service, deployment or remote push.
