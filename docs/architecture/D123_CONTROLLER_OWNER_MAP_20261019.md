# D123 controller owner map — 2026-10-19

Source baseline: `58321a866dd68195bf8264d1d9ebe7c18a60748f` on the existing
`codex/d118-start-lease-repair-20261019` branch. The baseline checkout had only
the two supplied D123 planning documents untracked. No production host or physical
device was accessed or modified.

## Production route and authority boundaries

```text
bot.py
  -> runtime.production_runtime (one module composition/lifecycle)
       constructs charge_controller = ManagedChargeController(...)
       runtime loop invokes charge_controller.tick(...)
         -> controller invokes its one session ShadowRecoveryRuntime.observe(...)
         -> runtime.charge.evidence.MainSampleEvidenceEvaluator.assess(...)
         -> runtime.charge.strategy.decide_main_transition(...)
         -> returns action mapping to existing runtime execution-port caller
       persistence delegates to runtime.charge.persistence and production session
       extensions; main-guard checkpoint uses runtime.charge.session_atomic

application.start_transaction_service
  -> configures the same app-owned controller before verified START execution
application.execution_port
  -> sole application-to-physical transaction owner / verified commit boundary
runtime.safety
  -> independent safety decisions and containment; no charge-stage authority
runtime.physical.connectors.esp_direct / Native adapter stack
  -> direct ESP Native physical truth; not queried during this source-only sprint
```

The exact production construction is `runtime/production_runtime.py:342`; the
periodic call is `runtime/production_runtime.py:2939`. The runner gates the call
on `session_recovery_guard.may_run_automatic_control()`. `bot.py` remains the
entrypoint. `ManagedChargeController.tick` is still a transitional session
orchestrator and stage/effect owner; moving one evidence boundary does not retire
that architecture debt.

There is one production charging FSM and one instance, but it is not yet the
target application-owned tick orchestration described by
`docs/V3_MODULAR_ARCHITECTURE.md`. `runtime.charge.strategy.main_authority` owns
the pure MAIN transition decision; `charge_controller.py` applies stage/effect
mutations. Durable session save/restore is delegated to
`runtime.charge.persistence`, with production extension fields supplied by
`production_controller.py`. The main-guard journal uses
`runtime.charge.session_atomic`. The application execution port is the only
actuation transaction boundary. `runtime.safety` remains independent.
Direct ESP physical observation is owned by the existing
`runtime.physical.connectors.esp_direct`/Native transport path; source-only D123
does not connect to it. Existing relevant contracts include
`tests/test_physical_connector_composition.py`,
`tests/test_d109_main_guard_runtime.py`, and MAIN Guard admission/runtime tests.
No physical measurements or acceptance are asserted here.

## ManagedChargeController methods

The table inventories every current method/property declared on
`ManagedChargeController` (84 AST declarations, 83 unique names because
`current_stage` has a getter and setter). “Internal tick” means the active
production call path from the single runtime invocation above. Test references
are regression contracts, not production callers. The proposed target is the
current canonical owner; this is an inventory, not a claim that all rows are
already migrated.

| Current methods | Current owner and active callers | Current / target path | Tests and mutation/safety risk |
|---|---|---|---|
| `__init__`, `current_stage` getter/setter, `is_active` (`charge_controller.py:175–227`) | Controller state; production composition constructs one instance; lifecycle/tick and readers use it | Controller state fields / stage-history setter now; target `runtime.charge.controller_state` + session state owner | `test_charge_controller`, `test_production_controller`, state/persistence suites. **High:** stage mutation and active-state gates |
| `_mark_stage_sample`, `_reset_stage_metrics`, `_reset_bank_fault_state`, `_reset_link_loss_state`, `_clear_restored_targets`, `_reset_delta_and_blanking`, `reset_session_data`, `_init_session`, `stop`, `full_reset` (`229–269`, `257–269`, `458–459`) | State/lifecycle helpers called by controller lifecycle, tick and restore paths | `runtime.charge.controller_state`, `runtime.charge.lifecycle`, then controller call sites | lifecycle/controller/persistence tests. **High:** reset/restart semantics; evidence loss or stale state |
| `_add_phase_limits`, `_add_desulf_limits`, `_temperature_compensation_coeff`, `_temperature_compensation_delta`, `_apply_temperature_compensation` (`271–322`) | Target/safety adapters; `_get_target_v_i` and stage target methods | Strategy and safety variable owners; retain thin adapter removal for later | strategy, target and safety tests. **High:** protection envelope and thermal compensation |
| `_prep_target`, `_main_target`, `_get_profile_target_v_i`, `_get_target_v_i`, `_desulf_target`, `_mix_target`, `_storage_target` (`324–396`, `477–498`) | Recipe/strategy adapters; tick, START and transitions call target selection | Existing `runtime.charge.strategy.*` selectors and recipe policy | target/recipe/envelope tests. **High:** any target or current change |
| `_post_charge_profile_params`, `_get_current_targets`, `_get_target_finish_time`, `_get_stage_max_hours`, `_mix_current_delta_threshold`, `_exit_cc_condition`, `_exit_cv_condition`, `_session_rules_summary`, `_mix_limit_seconds` (`398–399`, `434–456`, `1643–1645`) | Strategy/reporting adapters used by transitions, tick, UI and diagnostics | Existing post, support, MIX and strategy owners | strategy, finish, timeout tests. **High:** charge finish/timeout authority |
| `_record_safe_wait_sample`, `_make_log_event_end`, `_bank_fault_risk_snapshot`, `get_timers`, `get_ai_stage_snapshot`, `ui_support_snapshot`, `signal_analyzer_diagnostic_snapshot`, `recovery_shadow_summary` (`401–432`, `461–475`, `2362–2529`) | Diagnostics/read surfaces; UI and telemetry callers read snapshots; tick calls sample/log helpers | `runtime.charge.diagnostics`, reporting/read-model owners; no physical authority | diagnostic/UI/replay tests. **Medium:** evidence provenance and operator visibility |
| `configure_recovery_context`, `_new_runtime`, `_begin_trace_identity`, `_initialize_shadow_session`, `recovery_trace_context`, `_persist_shadow_trace_if_ready`, `_log_shadow_disagreement`, `_log_stage_transition`, `_first_stage_metadata`, `_trace_point_metadata`, `_shadow_metadata`, `_finite_or_nan`, `_finite_or_none`, `_normalize_output_on` (`500–552`, `842–887`, `890–997`, `999–1051`) | Session/evidence/trace glue; tick, START, persistence and trace logger | Existing evidence/session/trace modules; remaining P2 ownership debt | trace/recovery/session tests. **High:** session identity, evidence timestamps and restore continuity |
| `_enum_or_default`, `_read_legacy_session_document`, `_write_trace_identity_to_session_file`, `_restore_trace_identity`, `_restore_recovery_safe_wait`, `_restore_final_safe_wait`, `start`, `_clear_session_file`, `_save_session`, `_restore_desulfation_stage_clock`, `try_restore_session` (`555–839`) | Lifecycle and persistence façade; runtime startup/restore and controller lifecycle | `runtime.charge.persistence`, session continuation owners, and production lifecycle; no second writer | persistence/restore/recovery tests. **High:** restart can affect authority; no implicit Output ON |
| **`MainSampleEvidenceEvaluator` is now external; removed:** `_update_main_plateau_clock`, `_assess_main_sample`; former field `_v2_main_plateau_since` removed (`charge_controller.py:195`, `2209–2237` call; pure decision at `1908`; evaluator/API at `runtime/charge/evidence/first_stage.py:46–144`; removed methods were baseline `1000–1082`) | Before D123: controller tick and START/pause/cooling/reset callers. After D123: typed evidence owner; tick supplies current analysis; START and pause use owner reset/shift API | `runtime.charge.evidence.first_stage.MainSampleEvidenceEvaluator`; typed `MainSampleEvidenceInput` -> `MainSampleEvidence`; then existing pure MAIN decision | `test_main_sample_evidence_clock`, first-stage, controller authority, production-controller and main strategy tests. **High:** transition evidence/timing; exact accepted 15-minute backdating retained |
| `_apply_continuous_tail_hold`, `_log_stage_transition` (`1022–1051`) | Base identity extension point plus production subclass tail policy; called after evidence result during tick | Production continuity hold remains in `production_controller.py`; later P2/P3 decision required before further movement | `test_production_controller`. **High:** continuous tail hold is separate from plateau clock and preserved |
| `_complete_desulfation_to_safe_wait`, `_apply_recovery_safe_wait_authority`, `_apply_final_safe_wait_authority`, `_handle_safe_wait_stage_override`, `commit_verified_enable_transition`, `_handle_mix_stage_override`, `_is_authoritative_stage`, `_run_stage_scaffold_tick` (`1053–1641`) | Stage orchestration and transactional transition code; tick only | Existing stage decision modules plus application use case/execution port; substantial P3 debt | stage, safe-wait, execution and restart suites. **Critical:** verified OFF/ON and continuation safety |
| `_enter_safe_wait_done`, `_stop_and_diagnose`, `_advance_agm_step`, `_enter_desulfation`, `_enter_mix`, `_apply_authoritative_decision` (`1647–2066`) | Mutable stage/effect owner; tick only | Existing strategy decisions produce typed result; existing application orchestrates transaction; no new controller | authority/recovery/AGM/MIX tests. **Critical:** actuator setpoints, Output state, retry budget, stage commit |
| `tick` (`2068–2360`) | Transitional session orchestration and FSM adapter; only active call is production loop at `runtime/production_runtime.py:2939`; tests call directly | Intended to move to existing application use case at P2–P4, with current strategy, evidence, safety and execution owners | controller/production/recovery/safety tests. **Critical:** whole charge state machine and action batches |

Methods are grouped by responsibility above and current source line ranges are
included; no declaration is omitted. Baseline `charge_controller.py` was 2,594
LOC with 85 AST method declarations/84 unique names. After the D123 cut it is
2,529 LOC (-65), with 84 AST declarations/83 unique names; no overall LOC cap is
imposed. Do not infer
that unused-looking helpers are dead: runtime, application, subclass and tests
have direct references, while many others are called internally.

## ProductionChargeController transitional surface

`runtime.production_runtime` currently instantiates `ManagedChargeController`
directly; `ProductionChargeController` is retained in diagnostic/standalone/test
paths. Its unique active responsibilities are recipe-envelope target clamping,
continuous tail-hold policy, cooling pause snapshot/restore, finish-evidence and
runtime-signal session extensions, production tick wrapper, and fail-closed
restore/notification adaptation. These remain transitional production behavior
and are not a second production FSM. `diagnostic_controller.py` subclasses the
production controller for the distinct Diagnostic intent. Tests include
`test_production_controller.py`, `test_diagnostic_controller.py`, and cooling,
restore, and finish-evidence suites.

## State field inventory and lifecycle

| State | Owner now | Lifecycle/active readers | Risk and intended owner |
|---|---|---|---|
| `_v2_main_plateau_since` | Removed in D123; clock now `ManagedChargeController._main_sample_evidence.plateau_since_s` | Reset on START/session initialization/configuration, stage/transition and cooling; shifted during operator pause; evaluator is new per process and not serialized, matching prior restart behavior | **High.** Canonical owner is evidence module. Historical `v2` field name has no source references after extraction |
| `_v2_runtime`, `_v2_target_voltage_v`, `_v2_last_stage`, disagreement fields, trace ID/start | Controller | Session init/restore, tick, tracing and diagnostics | **High.** P2 evidence/session/trace owner; preserve trace IDs, monotonic/Native evidence |
| `_v2_session_signal_context`, recovery/final SAFE_WAIT continuation | Controller plus persistence module contracts | Captured in tick and serialized/restored by production controller and runtime | **Critical.** P2 existing session/persistence owner; keep fail-closed restore |
| `current_stage`, stage times, transition history, target/Ah counters, timers | Controller initialized through controller_state/lifecycle; direct production readers and tick mutations | Session lifecycle, tick, UI, guard and restore | **Critical.** P2/P3 canonical session state and application-owned transition commit |
| `_v2_continuous_tail_since`, `_v2_continuous_tail_stage_start`, finish/cooling evidence fields | Production controller | MAIN samples, cooling pause and session extensions | **High.** Keep distinct from plateau clock; later evidence/session convergence |
| `MainGuardShadow` / checkpoint identity | Existing runtime and `session_atomic` | Production telemetry/admission/guard loop; atomic journal path | **Critical.** No migration in P1; preserve source SHA, revision, monotonic 1800s ratchet and transaction semantics |

The plateau clock is deliberately not restored from disk: before D123 its field
was initialized to `None` in every new controller and was absent from session
serialization. Restart therefore still cannot manufacture plateau time. Operator
pause previously shifted this timestamp along with other clocks; the evidence
owner now does so via `shift_clock`.

Separate deferred algorithm defect: `SignalAnalyzerConfig` allows
`plateau_min_samples=5` in a 15-minute window. Five 3-minute-spaced samples can
emit `CURRENT_PLATEAU` after only 12 minutes; the accepted consumer then
backdates by the full 15 minutes. `test_analyzer_five_sample_minimum_and_existing_backdating_are_preserved`
characterizes this exact behavior. D123 intentionally retains it; a later
approved algorithm change must decide the minimum elapsed-evidence rule.

## Legitimate eradication versus remaining transitional ownership

The V3 legacy ledger records eradication of the historical V1 `ChargeController`
FSM, its `charge_logic.py` import/inheritance, historical `super().tick()` path,
retired V2 runtime/shadow islands, duplicate UI/action/actuator routes and
compatibility installers. These closures concern genuinely removed historical
owners and must remain closed.

They did **not** remove today's `ManagedChargeController`. It is current
production-reachable orchestration with mutable stage transitions, action
application, trace/session glue, and (before D123) first-stage clock mechanics.
Calling this class “legacy” does not make it historical V1; it is the transitional
current owner identified by D123. This sprint extracts only MAIN sample/plateau
evidence and does not claim controller convergence, application tick ownership,
physical acceptance, deployment, or closure of P2–P5.
