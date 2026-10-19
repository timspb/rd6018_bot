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
| `configure_recovery_context`, `_new_runtime`, `_initialize_shadow_session`, `recovery_trace_context`, `_log_stage_transition`, `_trace_point_metadata`, `_shadow_metadata`, `_finite_or_nan`, `_finite_or_none`, `_normalize_output_on` (current source locations) | Session/evidence/trace glue; tick, START, persistence and trace logger | Pure trace/signal payload assembly, typed context construction and disagreement throttling are owned by `runtime.charge.evidence.trace_context`; typed trace identity creation/restore is owned by `runtime.charge.session`; capture admission and DB write routing are owned by `recovery_trace_store`; controller retains the required `recovery_trace_context` read interface and calls lifecycle/persistence at its existing tick points | `test_d123_p2_trace_context`, trace/recovery/session tests. **High:** trace schema and restore continuity |
| `_restore_recovery_safe_wait`, `_restore_final_safe_wait`, `start`, `_clear_session_file`, `_save_session`, `_restore_desulfation_stage_clock`, `try_restore_session` | Lifecycle and persistence façade; runtime startup/restore and controller lifecycle | Canonical session read/restore/enrichment/write belongs to `runtime.charge.persistence` + `runtime.charge.session_atomic`; continuation validation and state application still have controller code. Guarded restore stays rejected before mutation until owner admission/readback reconciliation is installed | `test_recovery_trace_identity`, `test_session_atomic_guard_binding`, recovery/final SAFE_WAIT restart tests. **High:** restart can affect authority; no implicit Output ON |
| **`MainSampleEvidenceEvaluator` is now external; removed:** `_update_main_plateau_clock`, `_assess_main_sample`; former field `_v2_main_plateau_since` removed (`charge_controller.py:195`, `2209–2237` call; pure decision at `1908`; evaluator/API at `runtime/charge/evidence/first_stage.py:46–144`; removed methods were baseline `1000–1082`) | Before D123: controller tick and START/pause/cooling/reset callers. After D123: typed evidence owner; tick supplies current analysis; START and pause use owner reset/shift API | `runtime.charge.evidence.first_stage.MainSampleEvidenceEvaluator`; typed `MainSampleEvidenceInput` -> `MainSampleEvidence`; then existing pure MAIN decision | `test_main_sample_evidence_clock`, first-stage, controller authority, production-controller and main strategy tests. **High:** transition evidence/timing; exact accepted 15-minute backdating retained |
| `_apply_continuous_tail_hold`, `_log_stage_transition` (`1022–1051`) | Base identity extension point plus production subclass tail policy; called after evidence result during tick | Production continuity hold remains in `production_controller.py`; later P2/P3 decision required before further movement | `test_production_controller`. **High:** continuous tail hold is separate from plateau clock and preserved |
| `_complete_desulfation_to_safe_wait`, `_apply_recovery_safe_wait_authority`, `_apply_final_safe_wait_authority`, `_handle_safe_wait_stage_override`, `commit_verified_enable_transition`, `_handle_mix_stage_override`, `_is_authoritative_stage`, `_run_stage_scaffold_tick` (`1053–1641`) | Stage orchestration and transactional transition code; tick only | Existing stage decision modules plus application use case/execution port; substantial P3 debt | stage, safe-wait, execution and restart suites. **Critical:** verified OFF/ON and continuation safety |
| `_enter_safe_wait_done`, `_stop_and_diagnose`, `_advance_agm_step`, `_enter_mix`, `_apply_authoritative_decision` (current source) | Mutable stage/effect owner; tick only. `_enter_desulfation` was removed in Sprint 06. | Other stage methods remain controller-owned; MAIN->DESULFATION now uses `runtime.charge.runtime.desulfation_entry` typed effect; existing application action consumer and execution port remain unchanged | authority/recovery/AGM/MIX tests. **Critical:** actuator setpoints, Output state, retry budget, stage commit |
| `tick` (`2068–2360`) | Transitional session orchestration and FSM adapter; only active call is production loop at `runtime/production_runtime.py:2939`; tests call directly | Intended to move to existing application use case at P2–P4, with current strategy, evidence, safety and execution owners | controller/production/recovery/safety tests. **Critical:** whole charge state machine and action batches |

Methods are grouped by responsibility above and current source line ranges are
included; no declaration is omitted. Baseline `charge_controller.py` was 2,594
LOC with 85 AST method declarations/84 unique names. After the D123 cut it is
2,529 LOC (-65), with 84 AST declarations/83 unique names at Sprint 01. Sprint
03 removes trace identity/writer helpers and unused production session patch
writers; see `D123_SPRINT03_EVIDENCE_20261019.md` for exact current metrics.
No overall LOC cap is imposed. Do not infer
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

Sprint 03 removes its unused independent cooling, finish-state, and runtime
signal JSON patch writers. Its remaining restore reader uses the canonical
read function in `runtime.charge.persistence`; serialized extension keys remain
emitted by `_session_document_extensions` during the canonical complete save.

## State field inventory and lifecycle

| State | Owner now | Lifecycle/active readers | Risk and intended owner |
|---|---|---|---|
| `_v2_main_plateau_since` | Removed in D123; clock now `ManagedChargeController._main_sample_evidence.plateau_since_s` | Reset on START/session initialization/configuration, stage/transition and cooling; shifted during operator pause; evaluator is new per process and not serialized, matching prior restart behavior | **High.** Canonical owner is evidence module. Historical `v2` field name has no source references after extraction |
| `_v2_runtime`, `_v2_target_voltage_v`, `_v2_last_stage` | Controller | Session init/restore, tick, tracing and diagnostics | **High.** Remaining P2/P3 evidence/session lifecycle work |
| `_v2_trace_session_id`, `_v2_trace_started_at`, identity inputs | Runtime charge session owner for new/restore snapshot; controller stores active snapshot | `runtime.charge.session.TraceIdentitySnapshot`; canonical persistence enriches accepted restore | **High.** Preserve deterministic migration identity; guarded documents remain unmodified and restore-held |
| `_v2_session_signal_context`, recovery/final SAFE_WAIT continuation | Controller plus persistence module contracts | Captured in tick and serialized/restored by production controller and runtime | **Critical.** P2 existing session/persistence owner; keep fail-closed restore |
| `current_stage`, stage times, transition history, target/Ah counters, timers | Controller initialized through controller_state/lifecycle; direct production readers and tick mutations | Session lifecycle, tick, UI, guard and restore | **Critical.** P2/P3 canonical session state and application-owned transition commit |
| `_v2_continuous_tail_since`, `_v2_continuous_tail_stage_start`, finish/cooling evidence fields | Production controller | MAIN samples, cooling pause and session extensions | **High.** Keep distinct from plateau clock; later evidence/session convergence |
| `MainGuardShadow` / checkpoint identity | Existing runtime and `session_atomic` | Production telemetry/admission/guard loop; atomic journal path | **Critical.** No migration in P1; preserve source SHA, revision, monotonic 1800s ratchet and transaction semantics |

The plateau clock is deliberately not restored from disk: before D123 its field
was initialized to `None` in every new controller and was absent from session
serialization. Restart therefore still cannot manufacture plateau time. Operator
pause previously shifted this timestamp along with other clocks; the evidence
owner now does so via `shift_clock`.

### Sprint 04 stage-history convergence

At committed Sprint 04 source, `runtime.charge.session` owns stage
mutation (`set_current_stage`), history clearing, history restore normalization,
and stage metric reset on transitions. `ManagedChargeController.current_stage`
remains the stable public property used by application/runtime consumers and
delegates its setter to that owner. `runtime.charge.persistence` retains the
session document boundary but delegates history reconstruction to the same
session owner. Lifecycle reset paths also use its history clear operation. This
keeps one append for each actual transition, preserves no-op assignments, and
retains the persisted keys and entry shape (`from`, `to`, `reason`, `ts`).

### Sprint 05 trace lifecycle convergence

`runtime.charge.evidence.trace_context` now owns the frozen typed
`RecoveryTraceContext`, volatile identity fallback construction, and
disagreement repeat throttling/logging. The existing `recovery_trace_store`
owns readiness/stage/start-time admission and routes eligible captures to the
existing database writer. `ManagedChargeController` retains
the migration-required `recovery_trace_context` dict read property and makes
one integration call for disagreement and one capture call at the existing
tick points. `_persist_shadow_trace_if_ready`, `_log_shadow_disagreement`, and
their counter fields are removed. `recovery_trace_store.record_shadow_trace`
remains the only DB insert owner; the persisted table and shadow content are
unchanged. Capture failure remains diagnostic and cannot invalidate the already
formed action mapping. See `D123_SPRINT05_EVIDENCE_20261019.md`.

P2 remains partial because MAIN Guard restore admission and remaining audit /
session lifecycle ownership are still pending. P3 is partial: Sprint 06 moved
only the MAIN -> DESULFATION effect construction/application seam; the other
stage owners remain transitional.

### Sprint 06 P3-1 MAIN -> DESULFATION effect

`decide_main_transition` remains the decision owner and its controller call
site remains singular. On `ENTER_DESULFATION`, the controller resolves the
existing compensated target and event-end record, then calls the pure typed
builder `build_main_desulfation_effect` followed by the single
`apply_main_desulfation_effect` call in
`runtime/charge/runtime/desulfation_entry.py`. The former controller method
`_enter_desulfation` is deleted. The applicator records one stage edge through
`runtime.charge.session.set_current_stage`, invokes the already-existing target,
delta/blanking and evidence reset helpers, and updates the existing phase
current limit. It returns no physical execution path; action keys/values flow
through the same controller action dictionary and existing production
execution/verified-commit consumer. No other `_enter_*` method moved.

Focused typed-effect and static ownership gates are in
`tests/test_d123_p3_main_desulfation_effect.py`. Targeted bounded-recovery,
authority, output transaction, SAFE_WAIT and guarded restore suites plus the
full offline discovery were rerun in Sprint 06; exact counts and current
source-only status are in `D123_SPRINT06_EVIDENCE_20261019.md`.

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
current owner identified by D123. Sprint 06 additionally extracts the bounded
MAIN -> DESULFATION effect while retaining the existing controller dispatch.
This does not claim controller convergence, application tick ownership,
physical acceptance, deployment, or closure of P2–P5.

### Sprint 07 P3-2 DESULFATION -> recovery SAFE_WAIT

The active `decide_desulfation` call and its configured two-hour active-time
budget are unchanged. At `COMPLETE_TO_SAFE_WAIT`, the sole existing dispatch in
`ManagedChargeController._apply_authoritative_decision` resolves the canonical
`_main_target(temp)` and existing event-end record, then builds and applies the
frozen `DesulfationCompletionEffect` from
`runtime.charge.runtime.desulfation_completion`. The effect carries current
session ID/generation, source/next stages, targets, attempt, AGM step, timestamp,
Ah and sample values; it owns the immutable `log_event_end`, `turn_off=True`,
notification and `INTERMEDIATE_RECOVERY_COMPLETE` action values. Its applicator
validates non-empty matching session identity, finite matching positive
session generation and the DESULFATION source stage before any mutation.

After validation it makes one stage-history edge through the existing session
owner, commits the typed `RecoverySafeWaitContinuation`, keeps the existing
`_safe_wait_*` read mirrors, clears restored targets, updates stage clock/Ah,
records the existing SAFE_WAIT sample and resets MAIN plateau evidence. It has
no physical setter or execution-port dependency. Its action intents continue to
the same production execution-port OFF/readback/rollback route; the OFF
transaction ordering, restart snapshot schema, downstream recovery SAFE_WAIT
gate and all recipe targets remain unchanged. The removed
`_complete_desulfation_to_safe_wait` has no wrapper or remaining caller.

Focused gates are in `tests/test_d123_p3_desulfation_completion_effect.py`;
existing `test_desulfation_ownership_cutover.py` and
`test_voltage_relaxation_real_session_contract.py` exercise the production
decision path and persisted continuation snapshot. This is source-only P3-2,
not physical validation or P3 completion; remaining P3 and P4 are listed in the
Sprint 07 evidence and checklist.

### Sprint 08 P3-3 MAIN -> MIX

`decide_main_transition` remains the sole MAIN decision caller. On
`ENTER_MIX`, the controller still resolves the canonical `_mix_target(temp)`
and existing `_add_phase_limits` output, plus the existing event-end record;
it passes those values to the frozen typed `MainMixEffect` in
`runtime/charge/runtime/mix_entry.py` and calls its applicator once. The effect
owns the existing action mapping (`log_event_end`, V/I, OVP/OCP, notification,
and `START | V2_MIX`) and in-memory stage edge, restored-target clearing,
stage clock/Ah, delta/blanking and plateau resets, finish-evidence reset, and
phase-current-limit mirror. Target selection, MAIN/MIX decisions, current
clipping evidence, action execution, verified OFF/ON, rollback and physical
transaction ownership remain with their established owners. `_enter_mix` was
deleted without a proxy. Ca/Ca, EFB and AGM behavior is covered by
`tests/test_d123_p3_main_mix_effect.py` and existing downstream/transaction,
trace, checkpoint and restart regressions. This remains source-only and does
not establish physical acceptance.
