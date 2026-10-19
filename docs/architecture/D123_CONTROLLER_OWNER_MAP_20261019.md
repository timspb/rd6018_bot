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
| `_stop_and_diagnose`, `_advance_agm_step`, `_enter_mix`, `_apply_authoritative_decision` (current source); `_enter_safe_wait_done` removed in Sprint 09 | Mutable stage/effect owner; tick only. `_enter_desulfation` was removed in Sprint 06. | MAIN/MIX -> final SAFE_WAIT now uses `runtime.charge.runtime.final_safe_wait_entry`; other stage methods remain controller-owned. Existing application action consumer and execution port remain unchanged | authority/recovery/AGM/MIX/final SAFE_WAIT tests. **Critical:** stage commit and OFF/ON transaction ordering |
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

### Sprint 22 MIX completion dispatch

`runtime.charge.runtime.final_safe_wait_entry.apply_mix_completion_to_safe_wait`
now owns the MIX finish-hold completion evidence log and constructs/dispatches
the existing typed final SAFE_WAIT entry input. The MIX branch in
`ManagedChargeController._apply_authoritative_decision` retains its strategy
decision, storage target resolution, one owner call, and the established
fail-closed STOP_AND_DIAGNOSE response for invalid session identity. The shared
MAIN completion path is unchanged. The owner uses the same
`apply_final_safe_wait_entry` validation, stage/history commit, continuation,
reset and action payload; no execution port or RD setters were added. See
`D123_SPRINT22_EVIDENCE_20261019.md` for source and test evidence.

This is one bounded P3 cut. P2 MAIN Guard restore admission remains
fail-closed/deferred, and controller tick/session ownership, remaining MIX and
Storage/DONE/Manual paths, P4/P5, and physical acceptance remain open.

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

### Sprint 09 P3-4 MAIN/MIX -> final SAFE_WAIT entry

The existing MAIN and MIX decisions are unchanged. On their existing
`COMPLETE_TO_SAFE_WAIT` result, target selection still uses `_storage_target`,
and the existing event-end payload is captured before the stage mutation. Both
the controller path and the existing AUTO decision adapter build the frozen
`FinalSafeWaitEntryEffect` through `runtime.charge.runtime.final_safe_wait_entry`
and use its single mutation applicator. The effect retains source stage, session
ID/generation, canonical Storage targets, completion reason, sample values,
timestamp and exact `log_event_end`, notification, `START | V2_AUTHORITATIVE`
and `turn_off=True` action values.

Before mutation, the applicator requires a MAIN or MIX source stage matching the
current host, matching non-empty session ID and finite positive matching
generation, plus valid positive targets and start timestamp. Rejection leaves
stage, history, continuation and actions untouched; the caller enters the
existing STOP_AND_DIAGNOSE path, which cannot request Output ON. On acceptance,
the effect makes one canonical stage-history edge, records the same SAFE_WAIT
sample, clears restored targets, sets the existing continuation and target
mirrors, resets the completed sticky hold and MAIN plateau evidence, and emits
the existing verified-OFF intent. No physical writer, execution port, recipe,
threshold, persisted schema, downstream final SAFE_WAIT decision, verified
Storage ON commit, rollback, lease or Guard behavior moved.

Parity and static ownership checks are in
`tests/test_d123_p3_final_safe_wait_entry_effect.py`; prior direct-mutator test
setup now calls the typed effect owner. Focused final SAFE_WAIT/recovery/MIX,
readback, lease, rollback-related transaction and restoration coverage passed
469 tests. Exact full discovery and source-only scope are recorded in
`D123_SPRINT09_EVIDENCE_20261019.md`. Final SAFE_WAIT decision/commit,
cooling/storage/done and Manual integration remain P3 work; P2 remains partial.

### Sprint 10 P3-5 verified final SAFE_WAIT -> DONE commit

The existing `application.execution_port` transaction remains the sole physical
applicator and must return a session-bound verified-enable receipt before this
cut is reached. `ManagedChargeController.commit_verified_enable_transition`
still routes that receipt by transition kind and retains the independent
recovery SAFE_WAIT -> MAIN path. Its final `final_safe_wait_to_done` mutation
branch now constructs a frozen `FinalSafeWaitCompletionEffect` through
`runtime/charge/runtime/final_safe_wait_completion` and invokes that module's
single applicator.

The typed owner validates the same continuation/session identity, generation
and start timestamp before mutation. It then performs the same DONE stage edge,
restored-target and SAFE_WAIT mirror clearing, DONE-source marker and canonical
session save. Stage history still changes through the existing
`current_stage`/session owner before persistence; `_done_transition_source_stage`
is cleared in `finally`, including save failure. The effect contains only the
completion result metadata; it has no physical intents or setters. Receipt
rejection leaves the controller pending in SAFE_WAIT, and physical transaction
failure never invokes the commit route. Persisted Storage completion intent,
session keys, recovery behavior, Guard and execution ordering are unchanged.

`tests/test_d123_p3_final_safe_wait_completion_effect.py` guards frozen effect
data, stale/missing receipt rejection without mutation, one transition-history
edge, sole controller applicator call, and absence of physical writers in the
charge owner. Existing final SAFE_WAIT transaction/restore and recovery
transaction suites provide downstream persistence/readback/rollback coverage.
The final SAFE_WAIT strategy decision and enable request construction remain in
the controller and are still pending P3 work. This cut is software-only.

### Sprint 11 P3-6 PREP -> MAIN entry

`runtime.charge.runtime.residual_scaffold.run_authoritative_residual_scaffold`
continues to own the PREP voltage threshold, canonical PREP/MAIN target
selection, event-end capture and stage routing. Once PREP reaches its existing
threshold, it now builds a frozen `PrepCompletionEffect` in
`runtime/charge/runtime/prep_completion` and calls its single applicator. The
effect owns only the PREP -> MAIN state edge, restored-target clearing, stage
and Ah clock update, start-Ah capture, existing Delta/blanking reset, and the
same MAIN target/protection action values, notification and log event.

The action batch still flows to the existing downstream execution consumer;
the owner contains no setter calls, execution-port access, or Output intent.
Existing action keys are preserved, nested event-end data is frozen in the
effect and copied back to the ordinary action mapping at application. Cooling,
Manual, safety, threshold and target-selection ownership are unchanged.

`tests/test_d123_p3_prep_completion_effect.py` covers immutable typed effect
payload, target/protection parity, one stage-history edge, retained existing
action values, no Output ON intent, one residual-scaffold applicator call and
no physical writer. `tests/test_v3_residual_authority_migration.py` continues
to cover the production residual route, cooling resume and unsupported-stage
fail-closed behavior. Cooling resume, final SAFE_WAIT decision, DONE/IDLE and
remaining residual integrations remain pending.

### Sprint 12 P3-7 final SAFE_WAIT authority request

Both existing final SAFE_WAIT call paths still enter
`ManagedChargeController._apply_final_safe_wait_authority`. Its output freshness
normalization and SAFE_WAIT sample capture remain in the controller. Continuation
validation, pure relaxation decision, and exact Storage request action values now
come from `runtime.charge.runtime.final_safe_wait_authority` as a typed
`FinalSafeWaitAuthorityEffect`. The controller retains invalid-continuation
STOP_AND_DIAGNOSE containment, log reporting, and return mapping. Actions continue
through the same downstream `runtime.production_runtime` route and existing
`application.execution_port` verified transaction; the effect owner has no stage
mutation, persistence, or physical writer authority. The follow-up receipt still
commits through `commit_verified_enable_transition` and the Sprint 10 completion
effect.

`tests/test_d123_p3_final_safe_wait_authority_effect.py` verifies exact Storage
request keys/values, fresh-OFF wait behavior, stale identity rejection, and one
controller builder call. Existing mix authority, final SAFE_WAIT transaction,
and Storage restore tests exercise fail-closed and downstream transaction paths.
This is source-only. Remaining residual COOLING resume, DONE/IDLE and Manual
integration remain open.

### Sprint 13 P3-8 residual COOLING resume

`run_authoritative_residual_scaffold` remains the single production caller and
continues to own the COOLING temperature threshold, event-end capture, phase
limit selection, and notification dispatch. When the existing `temp <= warning`
gate is met, it now builds and applies the frozen `CoolingResumeEffect` in
`runtime.charge.runtime.cooling_resume`. The effect owns the same return-stage
selection, COOLING -> prior-stage mutation, restored-target clearing, stage/Ah
clock reset, cooling source clearing, transition blanking deadline, and exact
setpoint/turn_on/notification/log action values. The resulting actions still
flow through the same production execution route and `application.execution_port`;
the effect has no physical writer or execution-port dependency. Session identity,
Guard, lease, recipe, safety, and verified transaction boundaries are unchanged.

`tests/test_d123_p3_cooling_resume_effect.py` checks frozen payload and action
parity, one stage-history edge, timing/target preservation, stale-stage rejection,
single residual applicator call, and absence of physical writer calls. Existing
residual route, cooling and desulfation clock regressions were included in the
focused run. This source-only cut does not validate the physical re-enable path.
DONE/IDLE ownership, Storage/DONE and Manual integration remain pending; P2
remains partial.

### Sprint 14 P3-9 residual IDLE/DONE terminal flow choice

The production caller remains `ManagedChargeController._run_stage_scaffold_tick`
through `run_authoritative_residual_scaffold`. Sprint 14 moves only the
terminal-flow choice to the frozen `ResidualTerminalDecision` in
`runtime.charge.runtime.residual_terminal`: IDLE returns immediately after the
existing shared observation and safety work; DONE continues through the
existing stage timing, pending-log, and reporting path before its existing
no-transition return. The residual scaffold calls the owner once for terminal
stages. Sample capture, temperature/link safety, analytics, log/report state,
DONE verified commit, persistence, session identity, Manual, execution routing,
and all recipes remain at their existing owners.

The owner makes no state mutation and has no actuator/execution-port access.
`tests/test_d123_p3_residual_terminal.py` covers IDLE/DONE parity, rejection of
nonterminal/unknown stages, one production call site, and the no-writer boundary.
The focused set including residual authority and COOLING resume regressions
passed 11 tests with Python 3.12 and a synthetic token. This is a narrow
source-only terminal-flow extraction; remaining IDLE/DONE observation and
persistence ownership, Storage/DONE, Manual integration, P2, P4, and P5 remain
open.

### Sprint 15 P3-10 residual observation mutation owner

The same production caller remains `ManagedChargeController._run_stage_scaffold_tick`
through `run_authoritative_residual_scaffold`. The scaffold now delegates sample
mirror and history mutation to `runtime.charge.runtime.residual_observation`.
That owner calls the canonical `mark_stage_sample` state helper, appends the
existing analytics tuple and throttled V/I history for non-IDLE residual stages,
and retains IDLE's existing exclusion from those histories. Thus DONE continues
to record analytics and V/I history while IDLE records only the latest sample
mirrors. The residual scaffold no longer calls `_mark_stage_sample` or appends
these histories directly.

The cut changes no stage timing, safety handling, pending-log/report state,
persistence, session schema, Guard, lease, recipes, or execution routing.
`application.execution_port` remains the sole physical writer. The new
`tests/test_d123_p3_residual_terminal.py` cases check IDLE/DONE field and history
parity and a single owner call, plus the existing terminal decision and
no-writer guards. Focused residual authority and COOLING regressions passed 13
tests with the Python 3.12 venv and synthetic token. This is source-only;
remaining IDLE/DONE report/persistence ownership, Storage/DONE, Manual, P2, P4,
and P5 remain open. Full discovery was not run or claimed.

### Sprint 16 P3-11 residual pending-log and operator-report effect

The production caller remains `ManagedChargeController._run_stage_scaffold_tick`
through `run_authoritative_residual_scaffold`. Sprint 16 moves pending-log
consumption and hourly operator-report scheduling/payload construction into the
frozen `ResidualReportingEffect` in `runtime.charge.runtime.residual_reporting`.
Its applicator owns clearing `_pending_log_event`, advancing
`_last_hourly_report`, adding the pending event/report to the action mapping,
and preserving the existing direct-notify behavior when an action already has a
nonempty notification. IDLE still exits before this owner; DONE still reaches
it after shared observation and stage-clock bookkeeping.

The cut leaves phase-log timing, stage timing, persistence/session save,
Storage/DONE verified completion, Manual integration, safety, recipes, and
physical execution untouched. The charge owner has no RD setter or
`execution_port` route. `tests/test_d123_p3_residual_terminal.py` covers exact
report text, pending-log consumption, interval/manual-off behavior, notification
collision semantics, frozen effect, single applicator call, and static no-writer
gates. Focused residual/Storage failure regressions passed **30 tests** and the
full Python 3.12 offline discovery passed **2,387 tests / 3 skipped** with
synthetic token `123456789:d123-sprint16`; `compileall -q .` and
`git diff --check` passed. Exact source-only record:
`D123_SPRINT16_EVIDENCE_20261019.md`.

### Sprint 17 residual CV-clock mirror

The residual scaffold now delegates its existing `_cv_since` mirror update to
`runtime.charge.runtime.residual_observation.update_residual_cv_clock`. The
owner preserves the exact behavior: first CV observation sets the clock,
subsequent CV observations leave it unchanged, and CC clears it. The scaffold
remains the single caller and supplies the same sampled time. This moves one
residual observation mutation without changing stage decisions, history,
session persistence, Storage completion, Manual, safety, or physical execution.
The owner has no RD setters or `execution_port` access. Focused parity and
static guards plus Python 3.12 offline suite counts are recorded in
`D123_SPRINT17_EVIDENCE_20261019.md`.

Storage/DONE persistence remains coupled to the verified completion commit:
the ordinary tick save intentionally excludes IDLE/DONE, and DONE durability
is part of the receipt-gated completion path. Extracting it alone would alter
the commit/save order. Manual integration and central tick orchestration also
span broader boundaries without a comparably isolated effect. Those remain
future gates; P2, P3, P4, and P5 remain open.

### Sprint 18 STOP_AND_DIAGNOSE effect ownership

The former `ManagedChargeController._stop_and_diagnose` method is deleted.
All current controller callers invoke `runtime.charge.runtime.stop_diagnose.apply_stop_and_diagnose`.
That owner builds a frozen `StopDiagnoseEffect` and applies the exact existing
fail-closed transition to DONE: continuation clearing, one canonical stage-history
edge, terminal clocks, finish-timer and MAIN-evidence reset, exact OFF/notify/log
actions, and canonical session save ordering. Save failure preserves the prior
pre-save mutation semantics. The owner has no RD setter or `execution_port`
dependency. Focused related tests passed **58**, full Python 3.12 offline
discovery passed **2,395 tests / 3 skipped**, and compileall/diff checks passed.
Exact evidence: `D123_SPRINT18_EVIDENCE_20261019.md`.

P3 still retains Storage/DONE integration, Manual integration, other remaining
central-controller stage/orchestration seams, and the final application-owned
session tick cut. P2 restore admission, P4, P5 and physical acceptance remain open.

### Sprint 19 AGM MAIN step-advance ownership

The former `ManagedChargeController._advance_agm_step` method is deleted. The
sole `AuthorityAction.ADVANCE_AGM_STEP` branch now builds and applies
`runtime.charge.runtime.agm_step_advance.AgmStepAdvanceEffect`. The old
sequencing is unchanged: index first, then stage/Ah clocks and Delta/blanking +
MAIN evidence resets, then the existing `_main_target(temp)` using the advanced
index, then existing phase-limit action construction. No MAIN target,
temperature-compensation, protection-margin, recipe, Guard or execution logic
was copied.

The effect owner has no RD setter, Output intent or execution-port dependency.
Focused AGM/MAIN authority regression passed **34 tests**; full Python 3.12
offline discovery passed **2,399 tests / 3 skipped**, with compileall and
diff-check PASS. Exact source-only record:
`D123_SPRINT19_EVIDENCE_20261019.md`.

Remaining P3 central debt is now concentrated in
`_apply_authoritative_decision` orchestration itself, Storage/DONE and Manual
integration, and eventual application-owned session tick ownership.

### Sprint 20 MIX finish-hold start ownership

The mutable `AuthorityAction.START_FINISH_HOLD` branch now delegates to
`runtime.charge.runtime.mix_finish_hold.MixFinishHoldEffect`. The frozen owner
captures the existing sticky hold timestamp/mode, optional finish-evidence
snapshot and exact CV/CC evidence strings plus notify/log actions. The controller
retains only strategy dispatch and the existing diagnostic logger line. Missing
metric evidence still starts the hold without creating the optional snapshot,
matching prior behavior.

The owner has no stage transition, target, RD setter, Output intent,
`execution_port`, persistence, Guard or lease responsibility. Focused MIX and
authority regressions passed **37 tests**; full Python 3.12 offline discovery
passed **2,403 tests / 3 skipped**; compileall and diff-check PASS. Exact
source-only record: `D123_SPRINT20_EVIDENCE_20261019.md`.

Remaining mutable MIX state inside `_apply_authoritative_decision` is now limited
primarily to read-model metric mirrors and completion-evidence logging; the
stage actions themselves route through typed owners.

### Sprint 21 MIX evidence/read-model mirror ownership

The controller no longer mutates MIX dashboard/evidence mirrors inline. The sole MIX authority path builds a frozen `MixEvidenceMirror` through `runtime.charge.evidence.mix_observation` and applies it once. CV updates `i_min_recorded` only when `current_min_a` is present; CC updates `v_max_recorded` only when `voltage_max_v` is present. Missing metrics preserve the prior mirror values exactly.

This is evidence/read-model state only. MIX strategy decisions, sticky finish hold, final SAFE_WAIT entry/completion, stage transitions, target/protection selection, persistence, recipes, Guard, lease, action execution and the physical writer remain with their existing owners. The evidence owner has no execution port or RD setter dependency. Focused MIX regressions passed **17 tests**; full Python 3.12 offline discovery passed **2,406 tests / 3 skipped**; compileall and diff-check PASS. Exact source-only record: `D123_SPRINT21_EVIDENCE_20261019.md`.

Remaining central P3 debt is now concentrated in completion-evidence logging, `_apply_authoritative_decision` dispatch/orchestration, Storage/DONE and Manual integration, and eventual application-owned session tick ownership.

### Sprint 23 MAIN completion dispatch

The MAIN `AuthorityAction.COMPLETE_TO_SAFE_WAIT` branch retains
`decide_main_transition` and `_storage_target()` selection in
`ManagedChargeController._apply_authoritative_decision`. It now delegates
construction of the existing `FinalSafeWaitEntryInput` (including the existing
event-end payload) and the single final SAFE_WAIT entry application to
`runtime.charge.runtime.final_safe_wait_entry.apply_main_completion_to_safe_wait`.
Rejected session identity still returns to the controller's existing
STOP_AND_DIAGNOSE path. No strategy, recipe, session schema, Guard, lease,
physical transaction or executor ownership moved. The owner contains no RD
setter or `execution_port` dependency. Exact implementation and verification
are recorded in `D123_SPRINT23_EVIDENCE_20261019.md`.

### Sprint 24 MAIN entry dispatch convergence

`decide_main_transition` remains the decision owner. For `ENTER_DESULFATION`,
the controller still selects `_desulf_target(temp)` and dispatches once to
`runtime.charge.runtime.desulfation_entry.apply_main_desulfation_entry`; that
owner assembles the unchanged typed input and event-end payload, then calls the
existing effect applicator once. For `ENTER_MIX`, `_mix_target(temp)` and
`_add_phase_limits` remain in the controller; it dispatches their selected
values once to `runtime.charge.runtime.mix_entry.apply_main_mix_entry`, which
assembles the typed input/event end and calls the existing effect applicator.
Action keys/values, stage history, attempts, clocks, resets, protection limits,
and targets retain their prior algorithms. Event-end assembly failure
precedes stage mutation and action updates, as before. Both owners remain free
of RD setters and execution-port dependencies. See
`D123_SPRINT24_EVIDENCE_20261019.md`.

Sprint 24 changes only these two `_apply_authoritative_decision` branches.
AGM step advancement, MAIN completion, STOP_AND_DIAGNOSE, and tick remain
untouched. P3, P2, P4/P5, deployment and physical acceptance remain open.
