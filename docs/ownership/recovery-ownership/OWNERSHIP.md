# Recovery / Ownership — ownership contract

**Status: operating boundary documented; department functional-owner approval OPEN.** Primary ADRs remain the decision authority. This file records accepted decisions and conservative inventory classifications; placement under this department does not assign ownership.


### B902 current P1 scope reconciliation (2026-11-25)
AD083 D061 function scopes are accepted with the boundaries recorded in `docs/RD6018_AD083_CONTROL_ADOPTION_OWNER_DECISIONS_2026-11-15.md`. The file has no whole-file owner. D062 MIX authority remains separate in `rd_managed_mix.py`. The current 517-row source registry and historical 82-path subset were reconciled from B900 evidence; no registry-wide reanalysis was repeated.

## Responsibility and boundaries

- Planned responsibility: Recovery / Ownership as defined in `docs/RD6018_MODULARIZATION_EXECUTION_PLAN_P0-P9_2026-11-17.md` (department table, lines 12–24).
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
| MIXED-SCOPE | `application/controller_session_retirement.py` | AD056, master plan lines 977–978 — Multiple lifecycle effects and delegated owners; no single whole-file owner candidate. | Session retirement and related controller lifecycle orchestration. Tests: No path-specific test identified in this bounded matrix; focused test evidence remains OPEN. |
| ADAPTER/COORDINATOR | `application/session_recovery_service.py` | AD056, master plan lines 977–978 — Orchestration façade; underlying recovery and ownership policies remain elsewhere. | Service sequences recovery operations and delegates guard/retirement work. Tests: `tests/test_session_recovery_service.py` |
| MIXED-SCOPE | `rd_managed_mix.py` | AD057, master plan line 1014; AD083 line 11 — AD057 approves Recovery / Ownership as primary department only; AD083 keeps D062 authority in this coordinator. Neither assigns whole-file ownership. | Managed MIX lifecycle combines admission, evidence orchestration, hold lifecycle and verified containment. Tests: `tests/test_rd_managed_mix_adoption.py`, `tests/test_rd_managed_mix_hardening.py` |

**P5 adopted-MIX responsibility boundary (function-level; no whole-file assignment):** `ManagedMixAdoptionCoordinator` in `rd_managed_mix.py` owns D062 session state, transition sequencing, sticky-hold/retry lifecycle, and the existing observation loop. Pure admission/evidence decisions are delegated to `runtime/charge/strategy/adopted_mix_admission.py` and the adopted-MIX evidence helpers in `runtime/charge/evidence/`. D061 supplies the existing edge-adoption primitive and `EdgeSafetyLease` remains the lease owner. `rd_managed_mix_adoption.py` owns HMI presentation, callback routing, and confirmation composition. Physical OFF remains with the existing ExecutionPort/physical execution owner (including the existing HANDS_OFF OFF route through `RdControlModeManager.operator_output_off`). Native AUTO MIX remains with `MixPolicy` and the existing stage dispatcher. This map documents existing responsibility boundaries only; it does not grant whole-file ownership to `rd_managed_mix.py` or change actuator, lease, timing, or stage authority. Evidence: `.recipe-studio-local/REPORT_RD6018_P5_ADOPTED_MIX_INTERNAL_BOUNDARY_CLOSEOUT_20261118.md`. The audit found no separate primary D061/D062 ADR assigning the helper-level boundaries; AD083/AD057 are cited only within their stated scope.
| APPROVED (whole-file final owner) | `application/session_recovery_guard.py` | AD073 — Guard responsibility only; Application sequencing remains separate. | Guard evaluates recovery clearance and is consumed by recovery service. Tests: `tests/test_session_recovery_guard.py` |
| APPROVED (whole-file final owner) | `edge_live_adoption.py` | AD083 line 12 — Does not add physical authority outside the existing ownership transfer contract. | EdgeLiveAdoption checks and delegates to existing lease/edge primitive. Tests: `tests/test_edge_live_adoption.py` |
| ADAPTER/COORDINATOR | `rd_control_mode.py` | AD083 line 9; AD087 context — Explicitly presentation/composition wrapper aspects; no candidate. | Durable mode operations plus UI/installer wrappers. Tests: `tests/test_rd_control_mode.py` |
| MIXED-SCOPE | `rd_live_adoption.py` | AD083 line 10; AD087 context — Multiple responsibility categories; do not infer a single whole-file owner from primary label. | Observer state, evidence epoch, durable record, analyzer and observer task in one module. Tests: `tests/test_rd_live_adoption.py`, `tests/test_rd_live_adoption_zero_protection.py` |
| APPROVED (whole-file final owner) | `recovery_session.py` | AD078 whole-file decisions, line 13; scope lines 38–41 — Trace evidence only; does not replace plateau or charge transition owners. | Recovery trace point/analyzer evidence; consumed by recovery trace paths. Tests: `tests/test_recovery_session.py` |
| APPROVED (whole-file final owner) | `recovery_trace_report.py` | AD078 whole-file decisions, line 12; scope lines 43–44 — Report/trace responsibility only. | Trace normalization and report rendering helpers. Tests: `tests/test_recovery_trace_report.py` |
| APPROVED (whole-file final owner) | `runtime/journal/recovery_quarantine.py` | AD073 line 11; scope lines 29–42 — AD073 scope/exclusions apply; physical/Safety execution remain separate. | Quarantine state/journal operations consumed by recovery clearance and guard paths. Tests: `tests/test_data_logger_recovery_quarantine.py`, `tests/test_recovery_quarantine_journal.py` |
| MIXED-SCOPE | `runtime/startup_recovery.py` | AD056 master plan line 986; AD066 lines 10, 17 — Canonical session read belongs to persistence; guarded resume remains with existing Safety/execution owners. | Startup settlement/deferred restore and uptime reconciliation; constructed and invoked from bot.py. Tests: `tests/test_startup_recovery.py` |

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

## 2026-11-18 — P7 D061/D062 delegated responsibility parity, no second MIX owner

- Existing P5 primary source/owner evidence `.recipe-studio-local/REPORT_RD6018_P5_ADOPTED_MIX_INTERNAL_BOUNDARY_CLOSEOUT_20261118.md` and `.recipe-studio-local/REPORT_RD6018_P5_SOFTWARE_ACCEPTANCE_CLOSEOUT_20261118.md` reused; do not build new D061/D062 coordinators. D062 `ManagedMixAdoptionCoordinator.observe_once` owns adopted MIX orchestration and OFF_PENDING retry, native MIX stage remains `MixPolicy` via existing `application.charge_stage_tick`; physical OFF delegates to existing ExecutionPort/owner. `rd_managed_mix.py` stays MIXED-SCOPE; `rd_managed_adoption.py` retains AD083 function-level D061 responsibilities and the distinct D062 owner in `rd_managed_mix.py`; no whole-file approval is given.
- Independent Windows project Python 3.14.5 four-module contract cohort: `test_rd_managed_mix_adoption.py`, `test_rd_managed_mix_hardening.py`, `test_modularization_adopted_mix_observe_off.py`, `test_rd6018_p5_stage_path_parity.py`: **40 PASS + 5 subtests PASS** (82.21 s), exit 0. No physical operation. This is the P7 remaining responsibility review as scoped source/fake evidence only; no code split/extraction justified.
- P7 overall OPEN; P6 broad items OPEN; P8 physical/release HOLD. Existing Git WIP preserved; no stage/commit/reset/checkout/clean/stash/push.

## 2026-11-18 — primary decision and P1 candidate boundary

- AD083 remains controlling: `rd_managed_adoption.py` has no file-level approval. B900 records its separate current function responsibilities and preserves the concrete D061 false-return verified-OFF containment issue as the sole path-level functional HOLD.
- The four separately approved AD083 paths keep their listed exclusions. In particular, lease renewal and physical lease deadline remain with existing owners; no new manager, route, or renewal owner is introduced.
- P1 review retains the historical 37-candidate / five AD014 / 39 unassigned categories as provenance. B900 reconciles them to current function scopes without replay or double counting; no artificial whole-file owner is assigned, and the AD148T diagnostic `resolved_final_owner` is unchanged.
- Evidence: `.recipe-studio-local/REPORT_RD6018_P0P9_BATCH_LUNA_20261118_01.md`; the primary decision remains `docs/RD6018_AD083_CONTROL_ADOPTION_OWNER_DECISIONS_2026-11-15.md`.

## 2026-11-19 — D123 guarded restore failure-injection evidence

`StartupRecovery.replay_deferred_startup_restore` remains the existing startup orchestration boundary. Batch 07 added fake-only registered-orchestration cases for direct Native backend read failure and cancellation: failed read keeps the candidate held; cancellation latches the existing `SessionRecoveryGuard` and re-raises. This is a test gap closure only, not a new recovery owner or physical resume approval. Independent Windows `.venv` execution is pending; see `.recipe-studio-local/REPORT_RD6018_P3P4_RECOVERY_BATCH07_20261119.md`.


## 2026-11-19 — Independent P3/P4 D123 batch-07 acceptance

- HOME-PC Luna run `rd6018-mod-p3p4-main-guard-recovery-luna-20261119-07` exit=0; R7.2 completion event `a0f9c4194cca441f8e4c7e3caa495b12` delivered from launcher (acknowledgement not yet independently observed in this acceptance record).
- Fake-only registered `StartupRecovery.replay_deferred_startup_restore` scenarios added: Native backend read fails with `OSError`, retaining guarded candidate/inactive controller/canonical bytes; Native pre-ON read cancelled, existing `SessionRecoveryGuard` quarantines with `deferred_restore_cancelled`, re-raises, and leaves the same candidate and bytes unmodified.
- Independently ran native Windows project-venv 10-module pytest suite: **83 PASS + 47 subtests PASS, 1 skipped**, exit 0. No production source changed. Python compilation/diff-check pass. **P4 D123 failure-injection subgate ACCEPTED**; physical Native pre-ON acceptance, broader P3 emergency OFF preemption, P8 full platform/release regression remain HOLD. No equipment/node104 access, no change to firmware, lease or charge outputs.


## 2026-11-19 — P4 restore containment batch 09 (independent acceptance pending)

`StartupRecovery.replay_deferred_startup_restore` keeps the existing candidate and lock owner. Its `_serialized_deferred_restore` wrapper previously quarantined cancellation but allowed ordinary exceptions to escape without latching the `SessionRecoveryGuard`. Batch 09 adds a fake-only regression for an unexpected Native callback exception after a guarded candidate is loaded, and quarantines ordinary exceptions as `deferred_restore_failed:<type>` before re-raising. Candidate bytes/state remain untouched and no restore/Output call occurs. Linux collection is blocked by missing `python-dotenv`; independent Windows acceptance is pending. The P4 checklist remains open until host acceptance. No physical/recovery, P3, or P8 gate is closed. See `.recipe-studio-local/REPORT_RD6018_P4_RESTORE_CONTAINMENT_BATCH09_20261119.md`.


Checkpoint fields: exact source HEAD `2ba04a90440ffad54ca4a9e00512c54288ca11b4`; node104 `hands_off`/deployment state was not re-read in this source-only batch and no deployment occurred; local branch is 20 commits ahead of origin at start and no remote operation occurred; blockers are missing Linux `python-dotenv` and pending independent Windows `.venv` acceptance. Next executable step is the exact nine-module Windows pytest command in the batch report.


## 2026-11-19 — P4 batch-09 independent software acceptance

- Batch run `rd6018-mod-p4-restore-containment-luna-20261119-09` completed with executor exit=0. Independently inspected the actual source diff and tested the production `_serialized_deferred_restore` wrapper change: ordinary unexpected exceptions now quarantine existing `SessionRecoveryGuard` with `deferred_restore_failed:<type>` and re-raise, retaining the guarded candidate and original durable session bytes.
- Native Windows project `.venv` 10-module regression across D123 Native pre-ON, startup recovery, restore lifecycle, lost-link and quarantine: **70 PASS + 25 subtests PASS**, exit=0. `git diff --check` PASS. No new state owner, persistence writer, physical action, auto-rearm or modified charge decisions.
- **P4 unexpected deferred-restore exception containment source/fake subgate ACCEPTED.** Full P4 cold-restart/recovery, P3 physical OFF, live Native evidence, hardware, production release and P8 full-platform regression remain OPEN/HOLD. The pending host-test statements in the original Luna batch-09 notes are historical and superseded by this independent verification. No node104, HA/ESP live, Output, firmware, setpoint, lease, deployment, or remote push.

## 2026-11-19 — D062 coordinator/HMI ownership boundary, batch 34

`ManagedMixAdoptionCoordinator` remains the single D062 authority, exposed on each app as `rd_managed_mix_adoption`. The public installer retains its coordinator reuse and callback registration lifecycle; it does not capture one app's coordinator in process-global `operator_hmi` replacements. Existing UI projection owners read that app field. D062 lifecycle, ConfirmationStore, callback workflows, edge/lease/session and actuator behavior are unchanged. Batch 34 source/fake acceptance is pending the controlling host's Windows cohort; see `.recipe-studio-local/REPORT_RD6018_P7_D062_HMI_BATCH34_20261119.md`.


## 2026-11-19 — independent P7 D062 HMI global-patch removal batch-34 acceptance

- HOME-PC Codex Luna `rd6018-mod-p7-d062-hmi-owner-luna-20261119-34` exit=0; R7.2 completion event `b57e59b97ebc46fb875fc57f09df2a81` emitted. Deleted process-global D062 HMI replacements and `_d062_managed_mix_wrapped` flag from `rd_managed_mix_adoption.py`; installed coordinator remains sole per-app D062 authority (`app.rd_managed_mix_adoption`), no new state/owner/actuator path.
- Existing read-only HMI owners now project D062 active/off-pending state, keyboard, operator details, and More/status via app-aware `runtime/ui/components/hmi_state.py`, `hmi_action_keyboard.py`, `hmi_operator_details.py`, `hmi_navigation_keyboards.py`, and `operator_hmi.py`. Existing exact D062 stop/details/graph/battery buttons and high-voltage admission preserved. D062 details use existing safety projection instead of undefined `protections`; explicit UNKNOWN Output text preserved. No independent worker added.
- Independent Windows `.venv`: first D062/graph/Output-truth/architecture cohort found one test incorrectly expecting D062 button without a registered per-app coordinator. Updated fake cohort to attach D062 owner explicitly on each app, preserving both low-voltage refusal and high-voltage allowed callback assertions. Focused 12-module cohort **133 PASS + 24 subtests PASS**. Extended 20-module composition/D061/D062/START/AUTONOMOUS/UI/lifecycle cohort **223 PASS + 100 subtests PASS**, two existing UTC deprecation warnings, exit=0. Source compilation and `git diff --check` PASS; Linux behavior imports unavailable due to aiogram, not considered PASS.
- Bounded D062 HMI global-patch removal source/fake subgate ACCEPTED; original P0–P9 checklists unchanged (P7 PARTIAL, P8 physical/full release HOLD, AD083/AD148 whole-file HOLD). No node104, live HA/ESP, physical Output/V/I, charge, lease, firmware, service/deploy or remote push.


## 2026-11-19 — P7 ownership recovery HMI projection, batch 35

Removed `rd_ownership_recovery.install_rd_ownership_recovery`'s process-global assignment to `operator_hmi.build_operator_keyboard`. The existing `runtime/ui/components/hmi_action_keyboard.py` now projects ownership controls from the current app's `rd_control_mode_manager`, managed-session flags, D061 adoption coordinator and HMI state; `operator_hmi.build_operator_keyboard` invokes it before the existing final Output-truth/Autonomous filters. Existing callback labels remain in `runtime/ui/labels/operator_actions.py`; row construction uses `runtime/ui/telegram/renderer.py`. Callback registration, idempotent per-app install marker, recovery/release/adoption handlers and ExecutionPort routing are unchanged. `operator_managed_stop.py` remains untouched. Dependency-free `tests.test_p7_ownership_hmi_contract`: **3 PASS**; Python compilation and `git diff --check` pass. Linux `tests.test_rd_ownership_recovery` collection is blocked by missing `aiogram`. Windows project `.venv` cohort is pending; no Windows PASS is claimed. Owner: existing UI component; bounded source implementation for R7.2 run `rd6018-mod-p7-ownership-hmi-owner-luna-20261119-35`, which the controlling ChatGPT had already launched. This local review did not invoke/inspect the route and does not claim completion or ACK. Code HEAD remains `50ea5f92`, branch `feature/main-mix-countdown-display`, 45 commits ahead of tracking origin; no remote query, commit or push. WIP remains uncommitted for independent host acceptance. Next executable step: run the exact Windows project `.venv` cohort in the batch report and inspect actual markup, composition order, stale callback handling and Output/Autonomous filters. Linux runtime unittest is blocked before assertions by missing `aiogram`; this and Windows acceptance are HOLD. Starting node104 HANDS_OFF/deployment state was not refreshed and is not asserted as current. P7 remains PARTIAL; P8 full Linux/Windows/physical release HOLD; AD083/AD148 whole-file HOLD; no checklist promotions. No node104, live HA/ESP, Output/V/I, charge, lease, firmware, service, deployment, remote push, BW600 or XH-CDC-MK action. Report: `.recipe-studio-local/REPORT_RD6018_P7_OWNERSHIP_HMI_BATCH35_20261119.md`.


## 2026-11-19 — independent P7 ownership-recovery keyboard batch-35 acceptance

- HOME-PC Codex Luna `rd6018-mod-p7-ownership-hmi-owner-luna-20261119-35` exit=0, R7.2 completion event from shared launcher. Removed `rd_ownership_recovery.py`'s process-global `operator_hmi.build_operator_keyboard` assignment and first-app closure. Existing `runtime/ui/components/hmi_action_keyboard.py::_ownership_recovery_keyboard` now uses each app's installed recovery marker, control-mode manager, D061 owner and active managed state. No new app field/authority/manager. Existing Telegram callback registration and physical ExecutionPort transactions are retained. Original operator managed-stop wrapper is still separate and unchanged.
- Independent Windows project `.venv`: focused ownership/stop/D061/Output-truth/autonomous/production cohort **110 PASS + 31 subtests PASS** after fixing one real cross-app pre-install button leak and one fake callback registry missing its routes list. Expanded 21-module ownership/D062/graph/START/production/lifecycle/physical wiring suite **235 PASS + 102 subtests PASS**, two preexisting UTC deprecation warnings, exit 0. New fake/AST test checks installed per-app owner and source-only no global builder assignment. `py_compile` and `git diff --check` PASS.
- Scoped P7 ownership recovery HMI projection ACCEPTED. Original P0–P9 status/checklist remains unchanged: P7 PARTIAL, P8 full Linux/Windows/physical/release HOLD, AD083/AD148 whole-file HOLD. No live node104/HA/ESP, Output, V/I, charging, lease, firmware, service, deployment or remote push.
