# Application — ownership contract

**Status: operating boundary documented; department functional-owner approval OPEN.** Primary ADRs remain the decision authority. This file records accepted decisions and conservative inventory classifications; placement under this department does not assign ownership.


### B902 current P1 scope reconciliation (2026-11-25)
AD083 D061 function scopes are accepted with the boundaries recorded in `docs/RD6018_AD083_CONTROL_ADOPTION_OWNER_DECISIONS_2026-11-15.md`. The file has no whole-file owner. D062 MIX authority remains separate in `rd_managed_mix.py`. The current 517-row source registry and historical 82-path subset were reconciled from B900 evidence; no registry-wide reanalysis was repeated.

## Responsibility and boundaries

- Planned responsibility: Application as defined in `docs/RD6018_MODULARIZATION_EXECUTION_PLAN_P0-P9_2026-11-17.md` (department table, lines 12–24).
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
| ADAPTER/COORDINATOR | `application/controller_action_execution.py` | AD056, master plan lines 977–978 — Adapter/coordinator role; does not become the physical execution owner. | Application action dispatch/coordination across existing action owners. Tests: No path-specific test identified in this bounded matrix; focused test evidence remains OPEN. |
| ADAPTER/COORDINATOR | `diagnostic_probe.py` | AD057, master plan line 1014 — Coordinator role; does not own telemetry acquisition or physical authority. | Probe coordinates diagnostic collection and existing application-facing operations. Tests: `tests/test_diagnostic_probe.py` |
| APPROVED (whole-file final owner) | `application/manual_cooling_use_case.py` | AD069, with AD023 reaffirmation — Application transaction only; thermal thresholds are separately owned under AD143. | Cooling transaction/use-case sequencing called through Manual workflow. Tests: `tests/test_modularization_manual_cooling_use_case.py` |
| APPROVED (whole-file final owner) | `application/manual_mix_transition_use_case.py` | AD069; earlier AD016/AD019 context — No independent chemistry or physical command owner. | Manual MIX transition orchestration delegates policy and execution. Tests: `tests/test_modularization_manual_mix_transition_use_case.py` |
| ADAPTER/COORDINATOR | `application/manual_observer_use_case.py` | AD069; AD143 lines 22–33 — Threshold owner is Safety; Application owns sequencing, so no single final owner candidate for the adapter. | Coordinates normalized observation and Safety thermal checks. Tests: `tests/test_modularization_manual_observer_use_case.py` |
| ADAPTER/COORDINATOR | `application/manual_phase_evidence.py` | AD069; AD144 — Adapter role, not the evidence transition owner. | Adapts Manual phase evidence and delegates calculation/manager state. Tests: `tests/test_modularization_manual_phase_evidence.py` |
| APPROVED (whole-file final owner) | `application/manual_start_use_case.py` | AD069 — Sequencing only; Safety and Physical Execution remain distinct. | Manual start transaction/use case through existing Application path. Tests: `tests/test_modularization_manual_start_use_case.py` |
| APPROVED (whole-file final owner) | `application/manual_stop_use_case.py` | AD069 — Sequencing only; does not replace verified-off execution. | Manual stop transaction/use case through existing Application path. Tests: `tests/test_modularization_manual_stop_use_case.py` |
| APPROVED (whole-file final owner) | `application/manual_supervisor_use_case.py` | AD069; AD142 — AD142 bounds supervisor responsibility; observer/evidence subowners remain separate. | Coordinates Manual supervisor lifecycle; called from existing Manual flow. Tests: `tests/test_modularization_manual_supervisor_use_case.py` |
| ADAPTER/COORDINATOR | `application/operator_pause_use_case.py` | AD069; AD146–147 — AD146/147 clarify it is orchestration, not state/persistence or physical executor. | Orders pause transaction and delegates pause state and execution. Tests: `tests/test_modularization_operator_pause_use_case.py` |
| MIXED-SCOPE | `manual_mode.py` | AD080; AD142–143; AD069 history — Multiple delegated Manual responsibilities; AD080 and later decisions do not make this entire file a single owner. | Manual manager/runtime adapter retains several workflow calls and manager-owned session fields. Tests: `tests/test_manual_mode.py`, `tests/test_workstream113b_manual_mode_boundary.py` |
| APPROVED (whole-file final owner) | `application/charge_session_tick.py` | AD071 — Application orchestration only; policy/evidence owners stay separate. | Production tick orchestrates observation/dispatch and calls MAIN authority and evidence observers. Tests: No path-specific test identified in this bounded matrix; focused test evidence remains OPEN. |
| ADAPTER/COORDINATOR | `application/main_guard_runtime.py` | AD063 — AD063 runtime integration approval; four AJ table candidate values are discarded under the conservative rule. | Runtime integration wraps guard admission, session context and existing transaction calls. Tests: `tests/test_d109_main_guard_runtime.py` |
| ADAPTER/COORDINATOR | `application/operator_recovery_clearance.py` | AD073 — AD073 does not make the coordinator the quarantine-state owner. | Clearance workflow coordinates evidence and quarantine/recovery owner calls. Tests: No path-specific test identified in this bounded matrix; focused test evidence remains OPEN. |
| ADAPTER/COORDINATOR | `application/start_transaction_adapter.py` | AD071 — AD071 bounded adapter scope; candidate blank. | Adapter maps start transaction to existing owners. Tests: `tests/test_start_transaction_adapter.py` |
| ADAPTER/COORDINATOR | `application/start_transaction_runner.py` | AD071 — AD071 bounded orchestration; candidate blank. | Runner sequences start flow and delegates adapter/transaction operations. Tests: No path-specific test identified in this bounded matrix; focused test evidence remains OPEN. |
| ADAPTER/COORDINATOR | `runtime/charge/diagnostics.py` | AD078 lines 9, 20–28 — AD078 retains battery-fault classification and HV block in existing owners; Application adapter only. | Context/assessment adaptation, stored SG refresh and diagnostic HV-veto adapter; called from charge session tick. It also contains the existing read-only charge-controller compatibility/diagnostic projections; these projections do not promote whole-file ownership or decision authority. Tests: `tests/test_battery_diagnostics.py`, `tests/test_battery_diagnostics_store.py`, `tests/test_d123_p4_diagnostic_snapshot_ownership.py` |
| ADAPTER/COORDINATOR | `runtime/charge/restore_finalization.py` | AD067 lines 3, 5–14 — Application sequence only; load/acceptance, schema and durable storage remain existing owners. `restore_projection.py` remains HOLD. | Finalization choreography called by persistence restore path. Tests: `tests/test_modularization_restore_finalization_contract.py`, `tests/test_modularization_restore_finalization_use_case.py` |

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


## 2026-11-19 — P2/P6 Telegram fallback live-read handoff

- **Confirmed active cross-department boundary:** `runtime/ui/telegram/panel_lifecycle.py::TerminalPanelManager.ensure_text_last` used direct `self.app.hass.get_all_live()` only when the normal `/start` dashboard failed. That bypassed existing Application read-only `application.operator_read_source.OperatorReadSource.read_live()` although Telegram owns publication, not connector access.
- Changed exactly the live fetch to `OperatorReadSource(self.app).read_live()` via a recovery-time import, preserving the canonical dynamic HMI builder/wrapper calls, established app connector, HA warning, empty-value degraded fallback, panel serialization, delete ordering and old public interfaces. No extra manager, port implementation, timeout, clock, state, storage, authorization or I/O was added. `OperatorReadSource` remains the existing single read boundary; no new physical OFF/ON evidence authority.
- Added two fake-only tests in `tests/test_terminal_panel.py`: successful recovery consumes the read-only port with no `app.hass` on fake Telegram app, and a read failure renders the existing degraded text panel with `{}` instead of fabricated live readings. Both preserve chat/user panel IDs, keyboard and old-message retirement.
- Independent native Windows `.venv` regression of six modules (terminal panel, notification isolation, operator dashboard, production entrypoint/lifecycle shutdown, operator snapshot provider): **98 PASS + 73 subtests PASS**, exit=0. `py_compile` and `git diff --check` PASS. This closes one **P2/P6 fallback read-boundary subgate**, not overall P2/P6/P7. Existing P1 ADR/HOLD state and P8 full-release HOLD remain unchanged.
- Recovery Codex run `rd6018-mod-p6p7-production-seams-luna-20261118-04-recovery` exited 0 but produced a four-line report with no code or test modifications; independent owner review found the actual Telegram direct-read seam and corrected it above. No node104, HA/ESP production, Output, setpoints, lease, firmware, deployment or remote Git push.

## 2026-11-19 — Existing read-source boundary consumer evidence

`production_bot_ui.py`'s registered legacy `v2_status` callback now obtains live values through the existing `OperatorReadSource.read_live()` boundary. This records a consumer correction only; it does not approve `production_bot_ui.py` or assign Application ownership of the Telegram callback. The source/fake regression is authored in `tests/test_production_entrypoint.py`; execution is currently blocked in Linux by missing `aiogram`, and native Windows execution remains pending.


## 2026-11-19 — independent P2/P6 status callback acceptance

- R7.2 HOME-PC Codex run `rd6018-p2p6p7-port-lifecycle-luna-20261119-05` exit 0; event `c38550b2283b4a11b30a155ab46f3709` acknowledged attempt=1 by own-chat inspector.
- Confirmed active `production_bot_ui.py::status_handler` previously fetched `app.hass.get_all_live()` directly, bypassing established Application `OperatorReadSource.read_live()`. The callback now delegates only the read; behavior, callback registration, acknowledgement ordering, HMI formatting and physical execution remain unchanged.
- Independent native Windows project `.venv` test `test_status_callback_reads_live_values_through_application_source`: PASS. Full related Windows seven-module cohort: **111 PASS + 73 subtests PASS**, exit 0; fake test denies direct HA and proves Application read-port invocation. Python compile and `git diff --check` pass. First test fixture returned `object()` (formatter expects mapping); fixed by mocking the formatter in the test before acceptance, never weakened read-port denial.
- P2/P6 active callback-read subgate ACCEPTED; P2/P6 overall OPEN, P7 lifecycle review source-only and OPEN, P8 full Linux/Windows/physical acceptance HOLD. No node104, HA/ESP live, Output, firmware, firmware, deploy or remote push.


## 2026-11-19 — P2/P6/P7 batch 06 scoped caller audit

- Audit ledger: `.recipe-studio-local/REPORT_RD6018_P2P6P7_BATCH06_20261119.md`. Production review covered the registered UI callback, `OperatorReadSource`, Telegram middleware/panel publisher, graph retirement, composition installer sequence, notifications, and lifecycle shutdown. No additional reproducible source defect was established; no source/test change or stage promotion was made. The accepted batch-04/05 read-boundary changes remain in force.
- The Codex sandbox could not invoke its own R7.2 inspector because approval=never. Independently, HOME-PC launcher DID run Codex Luna with run ID `rd6018-mod-p2p6p7-batch06-luna-20261119-06` and delivered completion event `4dd72f845508403c9aa7bb0bdc28c279` with `exit_code=0`; this does not certify source acceptance. Linux focused test collection failed because `aiogram` is missing. Native Windows host independently ran architecture/entrypoint/panel/runtime-namespace tests: **57 PASS + 88 subtests**, exit=0. Full P8 regression remains HOLD.
- P1 candidate/blank/HOLD counts, verified-OFF, Native physical-proof separation, 900-second lease, 72-hour failsafe, and no-restart-auto-rearm remain unchanged. No hardware/deployment/push action.


## 2026-11-19 — P7 runtime composition batch 19 (ownership-blocked extraction)

Run `rd6018-mod-p7-runtime-composition-luna-20261119-19`; start HEAD `17ade43b` on `feature/main-mix-countdown-display`, clean, 30 commits ahead of origin. Production trace: `bot.py` → one `ProductionComposition` → `production_bootstrap` / `runtime.production_runtime` → existing application/session and feature owners → `production_lifecycle` start/stop tasks. In `production_runtime.py`, `_DeferredHassClient` is the import-safe runtime binding/compatibility seam; `initialize_runtime()` binds once and rebinds the existing RuntimeSafetyGuard adapter methods. `charge_controller` receives `_charge_notify`; safety guard and lifecycle also call it. Long-running `charge_monitor` / `data_logger` remain existing lifecycle task owners. No supported new root, second executor, worker or lifecycle owner found.

Candidate notification cluster traced: `_charge_notify` resolves recipient, enriches from current live context, owns existing duplicate-suppression state and schedules `_send_notify_safe`; `_send_notify_safe` owns Telegram HTML escaping/send and plaintext fallback after send failure. Existing `runtime/ui/telegram/panel_lifecycle.py` owns panel publication/edit lifecycle and explicitly does not own notification delivery/routing. No existing equivalent notification service/owner with a compatible contract was found in runtime, application or integrations. Creating a module would invent ownership; moving notification transport into panel lifecycle would conflate notification and panel owners. Therefore no source extraction or cosmetic helper move is accepted in this batch. AD148 final-owner remains HOLD; 11 department contracts remain open.

Existing runtime boundary tests: `tests/test_notification_isolation.py` exercises real `_charge_notify` scheduling, recipient capture before task execution, successful HTML send and plaintext fallback after simulated send rejection. Linux command `python3 -m unittest tests.test_notification_isolation -v` failed during import before assertions because system Python lacks `aiogram`; not a behavior result. Exact native Windows candidate: `& .venv\Scripts\python.exe -m unittest tests.test_notification_isolation tests.test_production_entrypoint tests.test_production_lifecycle_shutdown tests.test_autonomous_install_order_contract tests.test_runtime_app_namespace_contract tests.test_notification_isolation tests.test_terminal_panel -v`, then `& .venv\Scripts\python.exe -m py_compile runtime/production_runtime.py runtime/production_lifecycle.py runtime/production_bootstrap.py tests/test_notification_isolation.py` and `git diff --check`. Windows was not available here; no Windows PASS claimed.

No source/test behavior changes. No node104/HA/ESP/live hardware, Output, V/I, battery, lease, firmware, deployment, service restart, remote push, BW600 or XH-CDC-MK action. No commit. HOME-PC R7.2 launcher/ACK is not observable in this session and is not claimed; no second executor was launched. P7 remains OPEN; P8 full release/physical acceptance HOLD. Next executable work: independently run the exact Windows cohort and review this ownership block; pursue extraction only when an existing canonical notification owner/API is identified or separately approved. Report: `.recipe-studio-local/REPORT_RD6018_P7_RUNTIME_COMPOSITION_BATCH19_20261119.md`.


## 2026-11-19 — independent P7 controller diagnostic projections batch-22 acceptance

- HOME-PC Codex Luna run `rd6018-mod-p7-controller-diagnostics-owner-luna-20261119-22` exit=0, R7.2 completion event `8d84f92415fa4a93a2abd3bf089fc840` emitted. Exact ACK not separately verified.
- Existing `runtime/charge/diagnostics.py` now owns `ui_support_snapshot(host)` and `signal_analyzer_diagnostic_snapshot(host)` read-only projections. Public methods in `ManagedChargeController` remain simple compatibility delegates. Runtime evidence gate stays mode-match + explicit Output ON + telemetry valid + non-invalid last sample; no actuator or authority changes. `recovery_shadow_summary` remains in original boundary.
- Independent Windows project venv seven-module controller/diagnostic/trace/HMI suite **49 PASS + 27 subtests PASS**, exit=0. Initial failure exposed missing historical compatibility method docstring; restored. Next source-only D123 assertion incorrectly forbade the deliberately delegated function name; updated that test to verify exact existing owner delegate, non-authoritative owner docstring and absence of physical action symbols in both method and owner. Final suite PASS; `py_compile` and `git diff --check` PASS. Linux controller collection blocked by missing deps, not counted as PASS.
- P7 read-only diagnostic owner subgate ACCEPTED. Original P0-P9 statuses unchanged: P7 partial, P8 physical/full release HOLD and AD148 whole-file owner HOLD. No node104, live HA/ESP, Output, setpoints, charging, lease, firmware, deployment or remote push.
