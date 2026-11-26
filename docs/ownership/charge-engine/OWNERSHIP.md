# Charge Engine — ownership contract

**Status: operating boundary documented; department functional-owner approval OPEN.** Primary ADRs remain the decision authority. This file records accepted decisions and conservative inventory classifications; placement under this department does not assign ownership.


### B902 current P1 scope reconciliation (2026-11-25)
AD083 D061 function scopes are accepted with the boundaries recorded in `docs/RD6018_AD083_CONTROL_ADOPTION_OWNER_DECISIONS_2026-11-15.md`. The file has no whole-file owner. D062 MIX authority remains separate in `rd_managed_mix.py`. The current 517-row source registry and historical 82-path subset were reconciled from B900 evidence; no registry-wide reanalysis was repeated.

## Responsibility and boundaries

- Planned responsibility: Charge Engine as defined in `docs/RD6018_MODULARIZATION_EXECUTION_PLAN_P0-P9_2026-11-17.md` (department table, lines 12–24).
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
| BOUNDED AD014 — whole-file owner remains blank | `runtime/charge/evidence/adopted_mix_finish_hold_decision.py` | AD014, lines 3, 9 — pure monotonic elapsed-hold predicate only; whole-file owner remains blank. | Pure monotonic elapsed-hold predicate; called by rd_managed_mix.py:667–673. Tests: `tests/test_modularization_adopted_mix_finish_hold_decision.py` |
| APPROVED (whole-file final owner) | `runtime/charge/strategy/desulfation_variables.py` | AD008 lines 3, 5, 10 — Config/default ownership only; consumers retain their stage behavior. High confidence. | Typed VariableSpec declarations and duration accessor; consumed by desulfation, support, diagnostics and recipe parameter code. Tests: No path-specific test identified in this bounded matrix; focused test evidence remains OPEN. |
| APPROVED (whole-file final owner) | `runtime/charge/decisions.py` | AD010 line 8 — Narrow charge decision responsibility; no physical execution authority. | Charge decision logic used by existing charge runtime. Tests: `tests/test_architecture_owner_decisions_ad006.py`, `tests/test_architecture_owner_decisions_ad008.py`, `tests/test_architecture_owner_decisions_ad010.py` |
| ACCEPTED FUNCTION SCOPE — whole-file owner blank | `runtime/charge/evidence/manual_delta.py` | AD145 — Manual Delta Evidence owns only the pure `evaluate_manual_delta_evidence` transform over explicit prior state, policy and normalized sample. ManualSessionManager owns the four fields; profile/stop request owns thresholds; Application observer owns normalization. No timer, persistence or actuation authority. | Called through `manual_mode.py::_delta_reason` / Application observer. Tests: `tests/test_modularization_manual_delta_contract.py`, `tests/test_modularization_manual_delta_extraction.py` |
| APPROVED (whole-file final owner) | `runtime/charge/strategy/main_authority.py` | AD065 lines 7–17, 19–23 — Whole-file decision authority; scaffold owns integration/effects and Safety retains veto. | Pure MAIN transition decision called by main_scaffold.py and delegated to by native recipe policy. Tests: `tests/test_d123_p3_main_authority_dispatch.py`, `tests/test_v3_main_authority_migration.py` |
| APPROVED (whole-file final owner) | `signal_analyzer.py` | AD078 lines 11, 33–41, 55–57 — Analyzer does not acquire telemetry, prove freshness, select transitions or actuate. AD062 plateau and AD065 MAIN authority remain distinct. | Signal analysis over supplied samples; called from charge session, recovery trace and D062 delta test-control flows. Tests: `tests/test_signal_analyzer.py`, `tests/test_signal_analyzer_diagnostic_snapshot.py` |

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

## 2026-11-18 — P7 controller host function/caller crosswalk (documentation-only)

- `charge_controller.py` remains **AD080 NO FILE-LEVEL APPROVAL**: the single mutable `ManagedChargeController` is a compatibility host, not a stateless façade or second stage loop. Existing functions delegate lifecycle to `runtime.charge.lifecycle`, session persistence/restore to `runtime.charge.persistence` and `session_continuation_restore`, stage decisions to accepted Application/scaffold/strategy owners, physical execution to ExecutionPort/connector, and diagnostics to existing projections. Runtime direct host-field access exists, but a duplicate state owner was not demonstrated.
- Controller audit: `.recipe-studio-local/REPORT_RD6018_P7_CHARGE_CONTROLLER_RESPONSIBILITY_AUDIT_20261118.md`; full map: `.recipe-studio-local/REPORT_RD6018_P7_CHARGE_CONTROLLER_FUNCTION_OWNER_CROSSWALK_20261118.md`. Independent Windows project venv Python 3.14.5, five named charge-controller/target/dispatch/diagnostics modules, **26 PASS**, exit 0.
- **P7 controller owner/caller review scoped evidence ACCEPTED; P7 overall remains OPEN.** No approved source extraction, no file-level owner promotion, no code/physical/hardware operations; P8 release/physical HOLD.

## 2026-11-18 — P1 next review recommendation (batch 03)

- B900 accepts AD145 function scope for `runtime/charge/evidence/manual_delta.py`; whole-file owner remains intentionally blank because the module contains the bounded pure transform only.
- Exact candidate for the next architect decision: whether that module alone receives whole-file final-owner status within the AD145 pure-transform boundary. `manual_mode.py::_delta_reason` is the production adapter/caller. Focused evidence: `tests/test_modularization_manual_delta_contract.py` and `tests/test_modularization_manual_delta_extraction.py` (**19 PASS** in this batch).
- The suggestion does not include ManualSessionManager state, profile/stop thresholds, Application sample normalization, HMI, timer, persistence, or physical execution. No approval/assignment or AD148T `resolved_final_owner` update is made. Preserve 37 candidate-only, five bounded AD014 blanks, 39 other unassigned, and AD083 HOLD. Evidence: `.recipe-studio-local/REPORT_RD6018_P8_P2_INTEGRATION_BATCH_20261118_03.md`.

## 2026-11-19 — P7 controller diagnostics projection (batch 22; bounded function scope)

- `runtime/charge/evidence/signal_diagnostic_snapshot.py` owns both read-only UI support and non-authoritative SignalAnalyzer diagnostic projections. `diagnostics.py` directly re-exports both concrete functions for API compatibility. `ManagedChargeController` retains API-compatible delegates; `charge_controller.py` remains AD080 NO FILE-LEVEL APPROVAL.
- Consumers: `production_bot_ui.py`, `ui_polish.py`, `application/operator_snapshot_provider.py`, `runtime/ui/components/hmi_service_details.py` and HMI progress use the UI projection; `physical_test_control.py` uses the analyzer diagnostic projection. No charge-decision consumer found. The analyzer projection obtains the same fail-closed runtime evidence flag from the UI projection.
- `recovery_shadow_summary` stays with the host because it combines recovery runtime summary and `TraceLifecycle` disagreement state. No new state/cache, decisions, actuator authority, output writes or telemetry acquisition moved. Snapshot shape and `SignalEvent` identity are preserved.
- Batch report: `.recipe-studio-local/REPORT_RD6018_P7_CONTROLLER_DIAGNOSTICS_BATCH22_20261119.md`; focused native Windows behavior cohort pending.


## 2026-11-19 — independent P7 controller diagnostic projections batch-22 acceptance

- HOME-PC Codex Luna run `rd6018-mod-p7-controller-diagnostics-owner-luna-20261119-22` exit=0, R7.2 completion event `8d84f92415fa4a93a2abd3bf089fc840` emitted. Exact ACK not separately verified.
- `runtime/charge/diagnostics.py` owns `ui_support_snapshot(host)`; `runtime/charge/evidence/signal_diagnostic_snapshot.py` owns `signal_analyzer_diagnostic_snapshot(host)`. `diagnostics.py` directly re-exports both concrete functions; public methods in `ManagedChargeController` remain simple compatibility delegates. Runtime evidence gate stays mode-match + explicit Output ON + telemetry valid + non-invalid last sample; the SignalAnalyzer projection remains non-authoritative and diagnostic-only. No actuator or authority changes. `recovery_shadow_summary` remains in original boundary.
- Independent Windows project venv seven-module controller/diagnostic/trace/HMI suite **49 PASS + 27 subtests PASS**, exit=0. Initial failure exposed missing historical compatibility method docstring; restored. Next source-only D123 assertion incorrectly forbade the deliberately delegated function name; updated that test to verify exact existing owner delegate, non-authoritative owner docstring and absence of physical action symbols in both method and owner. Final suite PASS; `py_compile` and `git diff --check` PASS. Linux controller collection blocked by missing deps, not counted as PASS.
- P7 read-only diagnostic owner subgate ACCEPTED. Original P0-P9 statuses unchanged: P7 partial, P8 physical/full release HOLD and AD148 whole-file owner HOLD. No node104, live HA/ESP, Output, setpoints, charging, lease, firmware, deployment or remote push.

## 2026-11-19 — P7 restore orchestration boundary, batch 39

`runtime/charge/session_continuation_restore.py::restore_controller_session` owns the existing post-persistence controller restore choreography: historical Custom rejection/cleanup, typed continuation finalization, and guarded-activation bookkeeping. `ManagedChargeController.try_restore_session` stays as the public compatibility delegate. `runtime/charge.persistence.restore_session` remains the persistence/admission owner and mutable state remains on the existing controller host. `restore_desulfation_stage_clock` is colocated with restore continuation handling and receives the existing persistence-owned session-age bound. The verified-enable dispatcher stays in `charge_controller.py`; final and recovery SAFE_WAIT effects retain their separate existing owners and applicators. No whole-file owner approval for `charge_controller.py` is implied; AD080 and AD083/AD148 HOLDs remain unchanged.

Batch report: `.recipe-studio-local/REPORT_RD6018_P7_CONTROLLER_RESTORE_BATCH39_20261119.md`. Focused owner suite: 8 PASS; targeted compilation and diff check PASS. Broad Linux cohort collection is blocked before assertions by missing `aiosqlite`, `python-dotenv` and `aiogram`; Windows acceptance is pending. No change to physical, verified-ON, session-generation, terminal persistence or AUTO rearm authority.

## 2026-11-19 — P7 managed MIX/adoption owner graph audit, batch 41

The bounded source audit found no proven responsibility duplication to extract. `application/charge_session_tick.py` → `application/charge_stage_tick.py` → `runtime/charge/runtime/stage_authority.py` → `main_scaffold.apply_main_authority_tick` preserves the pure `runtime/charge/strategy/main_authority.py` decision and existing typed `runtime/charge/runtime/mix_entry.py` effect. The action map returns through the existing production tick and `ExecutionPort.execute_controller_actions` physical execution owner. MIX progression similarly dispatches through the existing `mix_scaffold.py`, pure `strategy/mix.py`, and typed runtime effects.

D061 remains in `rd_managed_adoption.py`; D062 authority/evidence remains in `rd_managed_mix.py` and its existing strategy/evidence helpers; `rd_managed_mix_adoption.py` remains the Telegram workflow installer delegating to the existing runtime composition hook. `bot.ProductionComposition` is the one production composition owner. HMI projection remains app-scoped and the existing `operator_output_truth` final filter preserves stale/unknown Output fail-closed behavior. No `runtime/charge/effects/` directory exists in this checkout; typed effects are under `runtime/charge/runtime/`. No duplicate strategy eligibility, transport patch, second engine, or physical adapter was identified. AD083 whole-file HOLD is unchanged.

Evidence/report: `.recipe-studio-local/REPORT_RD6018_P7_MANAGED_MIX_ADOPTION_BATCH41_20261119.md`. Existing source/fake coverage reviewed in MAIN dispatch/effect, managed adoption/D062, Output truth, charge-controller authority, and production entrypoint suites. Linux Python 3.12.3 invocation produced 21 passing tests and 10 collection errors caused by missing `aiogram`, `aiosqlite`, and `python-dotenv`; Windows acceptance remains pending. The specific combined strategy→typed effect→ExecutionPort plus app-specific HMI integration test is still an explicit next acceptance item; no integrated-test PASS is claimed. No production code, physical, hardware, or deployment change.


## 2026-11-19 — P7 managed MIX/adoption ownership audit, batch 41

- No source extraction justified: the existing graph is coherent. Pure MAIN policy is `runtime/charge/strategy/main_authority.py`; MAIN/MIX typed stage effects and their application remain under `runtime/charge/runtime/`; `ExecutionPort` owns physical V/I/Output dispatch. D061 `rd_managed_adoption.py` owns Manual-only live adoption; D062 `rd_managed_mix.py` owns adopted-MIX state/authority and delegates chemistry/budget/sample/hold to existing evidence/strategy owners; `rd_managed_mix_adoption.py` owns Telegram workflow composition. One `ProductionComposition`, one ChargeEngine, no duplicate eligibility predicate or transport patch.
- Independent Windows project `.venv` exact 10-module cohort **121 PASS + 19 subtests PASS**. Linux Python 3.12.3 `py_compile` and `git diff --check` PASS; Linux collection 21 tests PASS but 10 collection errors due missing `aiogram`, `aiosqlite`, and `python-dotenv`. The integrated single-chain strategy→typed effect→ExecutionPort plus app-specific HMI test remains outstanding and is explicitly not claimed complete.
- Bounded MIX/adoption ownership audit accepted; original P7 remains PARTIAL, P8 HOLD; AD083/AD148 whole-file ownership HOLD. No node104/live HA/ESP, Output/V/I, battery/charge, lease, firmware, service/deploy, remote push or BW600 physical action.

## B1017 — persisted-session restore owner

`runtime/charge/session_restore.py::restore_session` owns the complete persisted
snapshot restore use case, including decode/admission, guarded MAIN hold,
pre-mutation projection, ordered host application, session header and the call
into the existing finalizer. `runtime/charge/persistence.py` directly
re-exports that exact function object to preserve production and recovery
callers. The terminal Done normalizer has one implementation in the restore
owner and a persistence compatibility export. `restore_admission.py`,
`restore_projection.py`, `restore_finalization.py`,
`session_document_projection.py`, and `session_atomic.py` retain their existing
separate responsibilities; the latter remains the only canonical writer.
`charge_session.json` remains the sole session document. B1017 is source-only;
P0–P9 remains 97/103 with P3/P8/P9 HOLD. See `B1017_REPORT.md`.
