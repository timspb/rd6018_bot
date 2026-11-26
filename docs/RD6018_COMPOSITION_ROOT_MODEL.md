# RD6018 composition root model

Status: **current modular production composition**.

## Current production root

`bot.py` is the only production entrypoint. It composes the canonical
`runtime.production_runtime` substrate through `ProductionComposition`.
The retired compatibility facades are absent: there is no `bot_legacy.py`,
no `runtime.v2_runtime`, no top-level `v2_startup.py`, no
`application.v2_start_runner_adapter`, and no legacy actuator inventory facade.

`production_bootstrap.py` is a production composition installer module. It is not
a second production root and contains no charge-state machine or direct physical
writes.

## ApplicationComposition contract

There is one authoritative `ApplicationComposition` shape:

```text
ApplicationComposition
├── domain
├── application
├── infrastructure
├── ui
└── persistence
```

The composition root creates/connects owners and adapters. It must not own
charge decisions, safety policy, Telegram callback semantics, physical I/O,
persistence policy, or a second bootstrap.

## Single-root invariant

A running process has one startup handoff: `bot.main() -> ProductionComposition.run()`.
The runtime lifecycle is delegated to the composed canonical runtime only.
Any second bootstrap, module-alias facade, or compatibility entrypoint is a
regression.

## Naming and external compatibility boundaries

Production-reachable module filenames and internal owner types use neutral current
names. Historical-looking names may remain only in persisted state, Telegram
callback-data, deployed ESPHome/entity schemas or explicit historical evidence;
those are protocol/state boundaries and require explicit migration rather than
textual renaming. New production modules must not reintroduce `v2_*`, legacy,
shadow or compatibility ownership surfaces.

## Guardrail

Static architecture tests require retired facades to remain absent and prevent
reintroduction of direct physical calls into the bootstrap/composition layer.

## Physical owner visibility

`ExecutionPort` keeps the composed `ManagedRuntimeSafetyGuard` private. Application services must use `read_live()` / `read_native_physical_output_report()` for evidence and the existing typed execution methods for actuator operations. No application service may reach through the port to `execution_owner`, `HassClient`, or ESP transport. This keeps the composition root's owner wiring separate from application use cases.
## Safety owner over raw transport

The composition root injects the selected `HassClient` transport adapter into `ManagedRuntimeSafetyGuard`. The guard captures raw adapter methods and remains an explicit owner; production must not install wrappers on the adapter. `ExecutionPort` receives that guard as its private execution owner. `HassClient` performs raw transport dispatch only; it must not instantiate or own a Safety supervisor/coordinator.

## 2026-11-19 — P7 reassembly review: D061 HMI closure risk (not yet repaired)

`install_managed_live_adoption()` currently installs process-global `operator_hmi`
wrappers once. Those wrappers close over the first app's adoption coordinator;
later app composition leaves the wrappers bound to that coordinator. A second
app in the same process can consequently render adoption state from the first
app. The bounded candidate repair is to resolve
`rd_managed_live_adoption` from the wrapper's `app_arg` on each render and add
a two-app fake regression. No change has been implemented or accepted; AD083
whole-file ownership remains HOLD. The review also found no lifecycle test
proving repeated assembly/run plus transport reconnect keeps one poll worker.
See `.recipe-studio-local/REPORT_RD6018_P7_REASSEMBLY_BATCH25_20261119.md`.


## 2026-11-19 — independently accepted P7 D061 HMI reassembly batch-25 repair

- HOME-PC Luna batch 25 completed exit=0; its report documented the D061 wrapper closure/cross-app stale coordinator risk and left production source unchanged. Independent host review reproduced the structural problem and applied a bounded fix in the original coordinator installer: global operator_hmi wrappers now resolve the per-app `rd_managed_live_adoption` from the actual app argument, not the first-installed closure. No additional state, wrapper registration, manager or actuator action.
- New real aiogram decorator-registration test constructs two fake apps/coordinators, verifies five callbacks per app, idempotent same-app installation, independent HANDS_OFF adopt button and MANUAL adopted title/progress under active/off_pending transitions. Native Windows project .venv cohort across D061/D062, entrypoint, lifecycle, app namespace and physical connector: **77 PASS + 22 subtests PASS**, exit=0. `py_compile` and `git diff --check` PASS.
- This is a scoped source/fake repair, not whole-file ownership approval. AD083 and AD148 whole-file HOLD remain, P7 composition overall PARTIAL, P8 full regression/physical release HOLD. No node104/live HA/ESP, Output, setpoints, lease, firmware, deployment or remote push.


## 2026-11-19 — independent P7 production lifecycle batch-26 acceptance

- HOME-PC Codex Luna batch `rd6018-mod-p7-composition-lifecycle-luna-20261119-26` completed exit=0 and emitted R7.2 event `bbd87ada406e454da9889d8c69f2bf5e`. Existing `ProductionRuntimeLifecycle._stop_background_tasks` now performs cancel/join/clear from both shutdown hook and polling finally; physical connector close follows worker cleanup. No new scheduler, lock, output authority or owner.
- Independent Windows project venv lifecycle+composition+D061/D062/physical connector cohort **79 PASS + 22 subtests PASS**, exit=0. Initially 77 PASS with one failure in new polling-failure test because fake polling raised before scheduled workers could enter coroutines. Corrected fake polling to yield one event-loop cycle before throwing, preserving strict cancel/join assertions; no production code altered in that fix. Python compile/diff --check PASS.
- P7 lifecycle cancellation source/fake subgate ACCEPTED; P7 overall PARTIAL because reconnect and full composition/system tests remain, P8 full/physical release HOLD, AD083/AD148 whole-file HOLD. No node104/live HA/ESP, physical Output, setpoints, lease, charge, firmware, deployment or remote push.


## 2026-11-19 — P7 ownership recovery HMI projection, batch 35

Removed `rd_ownership_recovery.install_rd_ownership_recovery`'s process-global assignment to `operator_hmi.build_operator_keyboard`. The existing `runtime/ui/components/hmi_action_keyboard.py` now projects ownership controls from the current app's `rd_control_mode_manager`, managed-session flags, D061 adoption coordinator and HMI state; `operator_hmi.build_operator_keyboard` invokes it before the existing final Output-truth/Autonomous filters. Existing callback labels remain in `runtime/ui/labels/operator_actions.py`; row construction uses `runtime/ui/telegram/renderer.py`. Callback registration, idempotent per-app install marker, recovery/release/adoption handlers and ExecutionPort routing are unchanged. `operator_managed_stop.py` remains untouched. Dependency-free `tests.test_p7_ownership_hmi_contract`: **3 PASS**; Python compilation and `git diff --check` pass. Linux `tests.test_rd_ownership_recovery` collection is blocked by missing `aiogram`. Windows project `.venv` cohort is pending; no Windows PASS is claimed. Owner: existing UI component; bounded source implementation for R7.2 run `rd6018-mod-p7-ownership-hmi-owner-luna-20261119-35`, which the controlling ChatGPT had already launched. This local review did not invoke/inspect the route and does not claim completion or ACK. Code HEAD remains `50ea5f92`, branch `feature/main-mix-countdown-display`, 45 commits ahead of tracking origin; no remote query, commit or push. WIP remains uncommitted for independent host acceptance. Next executable step: run the exact Windows project `.venv` cohort in the batch report and inspect actual markup, composition order, stale callback handling and Output/Autonomous filters. Linux runtime unittest is blocked before assertions by missing `aiogram`; this and Windows acceptance are HOLD. Starting node104 HANDS_OFF/deployment state was not refreshed and is not asserted as current. P7 remains PARTIAL; P8 full Linux/Windows/physical release HOLD; AD083/AD148 whole-file HOLD; no checklist promotions. No node104, live HA/ESP, Output/V/I, charge, lease, firmware, service, deployment, remote push, BW600 or XH-CDC-MK action. Report: `.recipe-studio-local/REPORT_RD6018_P7_OWNERSHIP_HMI_BATCH35_20261119.md`.


## 2026-11-19 — independent P7 ownership-recovery keyboard batch-35 acceptance

- HOME-PC Codex Luna `rd6018-mod-p7-ownership-hmi-owner-luna-20261119-35` exit=0, R7.2 completion event from shared launcher. Removed `rd_ownership_recovery.py`'s process-global `operator_hmi.build_operator_keyboard` assignment and first-app closure. Existing `runtime/ui/components/hmi_action_keyboard.py::_ownership_recovery_keyboard` now uses each app's installed recovery marker, control-mode manager, D061 owner and active managed state. No new app field/authority/manager. Existing Telegram callback registration and physical ExecutionPort transactions are retained. Original operator managed-stop wrapper is still separate and unchanged.
- Independent Windows project `.venv`: focused ownership/stop/D061/Output-truth/autonomous/production cohort **110 PASS + 31 subtests PASS** after fixing one real cross-app pre-install button leak and one fake callback registry missing its routes list. Expanded 21-module ownership/D062/graph/START/production/lifecycle/physical wiring suite **235 PASS + 102 subtests PASS**, two preexisting UTC deprecation warnings, exit 0. New fake/AST test checks installed per-app owner and source-only no global builder assignment. `py_compile` and `git diff --check` PASS.
- Scoped P7 ownership recovery HMI projection ACCEPTED. Original P0–P9 status/checklist remains unchanged: P7 PARTIAL, P8 full Linux/Windows/physical/release HOLD, AD083/AD148 whole-file HOLD. No live node104/HA/ESP, Output, V/I, charging, lease, firmware, service, deployment or remote push.
## 2026-11-19 — P7 graph/HMI app-bound composition, batch 37

`install_operator_graph_dashboard(app)` now publishes the final panel renderer
and graph workspace callback on that app. `operator_hmi` resolves those callbacks
at render time, while its existing canonical builder retains semantic,
managed-adoption and Output-truth behavior. Dashboard composition no longer
replaces process-global HMI builder/renderer/graph functions. The existing
`TerminalPanelManager` remains the sole graph/panel message lifecycle owner.
This source/fake subgate awaits native Windows cohort and independent acceptance;
P7 remains PARTIAL and P8 remains HOLD. See
`.recipe-studio-local/REPORT_RD6018_P7_GRAPH_HMI_BATCH37_20261119.md`.


## 2026-11-19 — independent P7 graph HMI global-patch removal batch-37 acceptance

- HOME-PC Codex Luna run `rd6018-mod-p7-graph-hmi-global-patch-luna-20261119-37` exited 0, completion delivered through existing R7.2. `operator_dashboard.install_operator_graph_dashboard` no longer replaces process-global `operator_hmi.build_operator_hmi_state`, `render_operator_panel`, `render_operator_details`, or `_render_graph_workspace`. The same existing HMI and TerminalPanelManager owners resolve `app._render_operator_panel` / `app._render_graph_workspace` on the current app. One graph refresh/panel lifecycle and bottom-panel semantics remain.
- Independent Windows `.venv` targeted graph/source/entrypoint/namespace cohort **120 PASS + 88 subtests PASS**. Expanded 24-module graph/START/STOP/AUTONOMOUS/D061/D062/physical UI/lifecycle cohort **271 PASS + 107 subtests PASS**, five unrelated UTC deprecation warnings, exit 0. Per-app graph rendering, unchanged global HMI symbols, async graph callback dispatch, fallback, stale graph message IDs and production entrypoint were covered. `py_compile`, `git diff --check` PASS.
- P7 graph HMI global patch elimination subgate ACCEPTED. Original approved P0–P9 checklist/status unchanged: P7 PARTIAL, P8 full Linux/Windows/physical release HOLD; AD083/AD148 whole-file ownership HOLD. No node104, live HA/ESP, Output/V/I, charge, lease, firmware, service/deployment or remote Git push.


## 2026-11-19 — P7 production runtime façade/wiring/lifecycle owner audit, batch 40

`runtime/production_runtime.py` remains the import-safe runtime substrate and compatibility surface. No substantial extraction to an existing owner is justified: `bot.py::ProductionComposition` owns composition, `production_bootstrap.install_production()` owns safety/ExecutionPort/feature wiring, and `ProductionRuntimeLifecycle` owns restore ordering, background task lifecycle, polling and shutdown. `data_logger()` remains one ordered observation/recovery/tick cycle over app state, Native reconnect evidence, existing quarantine, pause, protection, sample persistence and existing application tick/action owners; moving a subset to the lifecycle scheduler would duplicate responsibility rather than consolidate it. The sole physical chain continues through the app-scoped ExecutionPort, Safety guard, HassClient and configured connector.

Existing tests cover repeated-compose identity, reconnect baseline gating, UNKNOWN Output, `V2_UI=false` safety installation, restore exception/cancellation quarantine, failed-poll cleanup, worker shutdown, app namespace and composition ordering; see `.recipe-studio-local/REPORT_RD6018_P7_PRODUCTION_RUNTIME_BATCH40_20261119.md` for exact test names and Linux results. The Linux cohort reached 16 PASS with 6 dependency collection errors; the independent Windows project `.venv` cohort passed **78 tests + 36 subtests**. This accepts only the source/fake runtime audit subgate. P7 remains PARTIAL, P8 HOLD, AD083/AD148 HOLD; no checklist item is promoted and no physical/release acceptance is implied.


## 2026-11-19 — P7 managed MIX/adoption ownership audit, batch 41

- No source extraction justified: the existing graph is coherent. Pure MAIN policy is `runtime/charge/strategy/main_authority.py`; MAIN/MIX typed stage effects and their application remain under `runtime/charge/runtime/`; `ExecutionPort` owns physical V/I/Output dispatch. D061 `rd_managed_adoption.py` owns Manual-only live adoption; D062 `rd_managed_mix.py` owns adopted-MIX state/authority and delegates chemistry/budget/sample/hold to existing evidence/strategy owners; `rd_managed_mix_adoption.py` owns Telegram workflow composition. One `ProductionComposition`, one ChargeEngine, no duplicate eligibility predicate or transport patch.
- Independent Windows project `.venv` exact 10-module cohort **121 PASS + 19 subtests PASS**. Linux Python 3.12.3 `py_compile` and `git diff --check` PASS; Linux collection 21 tests PASS but 10 collection errors due missing `aiogram`, `aiosqlite`, and `python-dotenv`. The integrated single-chain strategy→typed effect→ExecutionPort plus app-specific HMI test remains outstanding and is explicitly not claimed complete.
- Bounded MIX/adoption ownership audit accepted; original P7 remains PARTIAL, P8 HOLD; AD083/AD148 whole-file ownership HOLD. No node104/live HA/ESP, Output/V/I, battery/charge, lease, firmware, service/deploy, remote push or BW600 physical action.
