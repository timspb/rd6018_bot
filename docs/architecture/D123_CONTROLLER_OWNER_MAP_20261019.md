# D123 controller owner map — 2026-10-19

Source baseline: `58321a866dd68195bf8264d1d9ebe7c18a60748f` on the existing
`codex/d118-start-lease-repair-20261019` branch. The baseline checkout had only
the two supplied D123 planning documents untracked. No production host or physical
device was accessed or modified.

## Production route and authority boundaries

```text
bot.py
  -> runtime.production_runtime (one module composition/lifecycle)
       constructs charge_controller = create_production_charge_host(...)
         -> exactly ManagedChargeController with frozen production host configuration
       runtime loop invokes application.charge_session_tick.run_charge_session_tick(...)
         -> the one production session host supplies state and production extensions
         -> application routes through canonical stage/evidence owners
  -> runtime.charge.runtime.main_scaffold.apply_main_authority_tick(...)
  -> runtime.charge.runtime.recovery_scaffold.apply_desulfation_authority_tick(...)
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

The exact production construction is `runtime/production_runtime.py:344`; the
periodic call is `runtime/production_runtime.py:2894`. The runner gates the call
on `session_recovery_guard.may_run_automatic_control()`. `bot.py` remains the
entrypoint. `ManagedChargeController.tick` was removed in Sprint 48. Sprint 50
removed active runtime construction of the base facade; Sprint 55C then removed
the marker subclass. The one production host is now exactly `ManagedChargeController`,
configured by `create_production_charge_host`. Bootstrap configures an existing
canonical instance in place and preserves its identity.

There is one production charging FSM and one instance, but it is not yet the
target fully application-owned session/state lifecycle described by
`docs/V3_MODULAR_ARCHITECTURE.md`. `runtime.charge.strategy.main_authority` owns
the pure MAIN transition decision; `runtime.charge.runtime.main_scaffold`
assembles its inputs and dispatches existing typed effects. The controller
retains stage admission and one owner call. Durable session save/restore is delegated to
`runtime.charge.persistence`, with production extension fields supplied by
`production_controller.py`. `ProductionChargeController` still subclasses
`ManagedChargeController` for the existing state, lifecycle, and restore surface;
the base class is therefore a remaining source dependency, but production no
longer constructs that facade. Removing inheritance would require a separate
session/state/lifecycle migration. Ordinary-session restore remains a separate
P2 boundary and guarded restore remains fail-closed/deferred. The main-guard journal uses
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
| `_record_safe_wait_sample`, `_make_log_event_end`, `get_timers`, `get_ai_stage_snapshot`, `ui_support_snapshot`, `signal_analyzer_diagnostic_snapshot`, `recovery_shadow_summary` (`401–432`, `461–475`, `2362–2529`) | Diagnostics/read surfaces; UI and telemetry callers read snapshots; tick calls sample/log helpers | `runtime.charge.diagnostics`, reporting/read-model owners; no physical authority | diagnostic/UI/replay tests. **Medium:** evidence provenance and operator visibility |
| `configure_recovery_context`, `_new_runtime`, `_initialize_shadow_session`, `recovery_trace_context`, `_log_stage_transition`, `_trace_point_metadata`, `_shadow_metadata`, `_finite_or_nan`, `_finite_or_none`, `_normalize_output_on` (current source locations) | Session/evidence/trace glue; tick, START, persistence and trace logger | Pure trace/signal payload assembly, typed context construction and disagreement throttling are owned by `runtime.charge.evidence.trace_context`; typed trace identity creation/restore is owned by `runtime.charge.session`; capture admission and DB write routing are owned by `recovery_trace_store`; controller retains the required `recovery_trace_context` read interface and calls lifecycle/persistence at its existing tick points | `test_d123_p2_trace_context`, trace/recovery/session tests. **High:** trace schema and restore continuity |
| `_restore_recovery_safe_wait`, `_restore_final_safe_wait`, `start`, `_clear_session_file`, `_save_session`, `_restore_desulfation_stage_clock`, `try_restore_session` | Lifecycle and persistence façade; runtime startup/restore and controller lifecycle | Canonical session read/restore/enrichment/write belongs to `runtime.charge.persistence` + `runtime.charge.session_atomic`; continuation validation and state application still have controller code. Guarded restore stays rejected before mutation until owner admission/readback reconciliation is installed | `test_recovery_trace_identity`, `test_session_atomic_guard_binding`, recovery/final SAFE_WAIT restart tests. **High:** restart can affect authority; no implicit Output ON |
| **`MainSampleEvidenceEvaluator` is now external; removed:** `_update_main_plateau_clock`, `_assess_main_sample`; former field `_v2_main_plateau_since` removed (`charge_controller.py:195`, `2209–2237` call; pure decision at `1908`; evaluator/API at `runtime/charge/evidence/first_stage.py:46–144`; removed methods were baseline `1000–1082`) | Before D123: controller tick and START/pause/cooling/reset callers. After D123: typed evidence owner; tick supplies current analysis; START and pause use owner reset/shift API | `runtime.charge.evidence.first_stage.MainSampleEvidenceEvaluator`; typed `MainSampleEvidenceInput` -> `MainSampleEvidence`; then existing pure MAIN decision | `test_main_sample_evidence_clock`, first-stage, controller authority, production-controller and main strategy tests. **High:** transition evidence/timing; exact accepted 15-minute backdating retained |
| `_apply_continuous_tail_hold`, `_log_stage_transition` (`1022–1051`) | Base identity extension point plus production subclass tail policy; called after evidence result during tick | Production continuity hold remains in `production_controller.py`; later P2/P3 decision required before further movement | `test_production_controller`. **High:** continuous tail hold is separate from plateau clock and preserved |
| `_complete_desulfation_to_safe_wait`, `_apply_recovery_safe_wait_authority`, `_apply_final_safe_wait_authority`, `_handle_safe_wait_stage_override`, `commit_verified_enable_transition`, `_handle_mix_stage_override`, `_is_authoritative_stage`, `_run_stage_scaffold_tick` (`1053–1641`) | Stage orchestration and transactional transition code; tick only | Existing stage decision modules plus application use case/execution port; substantial P3 debt | stage, safe-wait, execution and restart suites. **Critical:** verified OFF/ON and continuation safety |
| `_stop_and_diagnose`, `_advance_agm_step`, `_enter_mix`, `_apply_authoritative_decision` (current source); `_enter_safe_wait_done` removed in Sprint 09 | Mutable stage/effect owner; tick only. `_enter_desulfation` was removed in Sprint 06. | MAIN dispatch goes through `runtime.charge.runtime.main_scaffold.apply_main_authority_tick`; DESULFATION completion and recovery SAFE_WAIT authority dispatch through `runtime.charge.runtime.recovery_scaffold`; MIX dispatch through `runtime.charge.runtime.mix_scaffold.apply_mix_authority_tick`. Controller retains stage admission; outer stage routing and final SAFE_WAIT authority remain controller-owned. Execution port unchanged | authority/recovery/AGM/MIX/final SAFE_WAIT tests. **Critical:** stage commit and OFF/ON transaction ordering |
| `tick` | **Removed in Sprint 48.** Production enters `application.charge_session_tick.run_charge_session_tick`; only intentional fake characterization methods remain in isolated tests. | No controller tick compatibility facade; HANDS_OFF/startup suspension is enforced at the application host boundary. | `test_d123_p3_application_tick_ownership`, application/controller and HANDS_OFF regressions. |

Sprint 49 also removed `_bank_fault_risk_snapshot`: Diagnostic AUTO now calls the canonical `runtime.charge.diagnostics.bank_fault_risk_snapshot` directly. This was a read-only diagnostic adapter; risk calculation and policy are unchanged.

Sprint 50 removes direct production construction of `ManagedChargeController`.
The single runtime host is now `ProductionChargeController`, with the existing
`application.charge_session_tick` automatic tick route. Static and behavioral
entrypoint gates cover its import/construction. The subclass still inherits
base state/lifecycle/session restore; this remaining dependency is explicitly
not a second FSM or instance. Moving that boundary is deferred because current
ordinary restore and MAIN Guard restore admission are not yet owned by a
canonical application/session lifecycle. See
`D123_SPRINT50_EVIDENCE_20261020.md`.

### Sprint 51 recipe-envelope target policy

`application.production_target_policy` now owns production recipe-envelope
resolution from the current host profile/capacity/battery/intent/condition and
the pure voltage/current clamp. `ProductionChargeController` continues to own
the one FSM and supplies its existing state to that policy while adapting the
base target selectors; restored-target clamping uses the same policy functions.
The controller no longer declares `_recipe_envelope`, `_bound_target`, or
`_current_stage_is_hv`. No lifecycle, session, persistence, restore, or Guard
admission ownership moved. The single production host and canonical session
writer remain unchanged. Parity and no-second-host checks are in
`tests/test_d123_p4_recipe_target_policy.py`; exact sprint validation is in
`D123_SPRINT51_EVIDENCE_20261020.md`.

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

### D123 Guard restore boundary (2026-10-21)

`runtime.charge.persistence.restore_session` retains any Guard-bearing decoded
document as `GuardedRestoreCandidate` on the sole controller host, without
mutating active FSM, trace, or Guard state. `StartupRecovery.replay_deferred_startup_restore`
recognizes this quarantine and exits before reading HA aggregate data. Direct
Native pre-ON assessment is not yet integrated because the startup recovery
owner has no existing Native snapshot acquisition API; Guard candidates remain
inactive and cannot resume automatically. See
`D123_GUARD_PRE_ON_INTEGRATION_EVIDENCE_20261021.md`.

### Sprint 57 P2 read-only evidence continuation (2026-10-21)

The previous statement that startup had no Native snapshot API is superseded
for read-only assessment only. `HassClient.get_native_guard_pre_on_snapshot`
uses the already selected physical backend and returns evidence only when that
backend is an `ESPDirectConnector`. It consumes the connector's existing live
callback values and native `get_state` lease read; it creates no transport,
client, or execution owner. Required electrical fields must each report
`esp_native_api`, `SensorState`, and an actual callback monotonic timestamp no
older than ten seconds. Lease is separately required from a fresh native
`BinarySensorState`. HA aggregate/cache metadata and fetch time cannot satisfy
these checks.

`StartupRecovery.replay_deferred_startup_restore` still runs under the one
app-scoped `ExecutionPort._guard_owner_lock`. It snapshots the canonical
session, parses the candidate with existing `read_guard`, calls the existing
`assess_main_guard_before_output_on`, and rechecks canonical session/battery
identity plus Guard revision after assessment. Its result is retained only as
`StartupRecovery.last_guard_assessment`; a `RECONCILED` result does not restore
FSM/session state or clear the candidate. No Output operation is reachable from
this assessment branch. Missing Native acquisition, untrusted journal, stale
identity/revision, missing lock/lease, or evaluator failure leaves the
candidate quarantined. Persistence remains the sole writer and original
document bytes/schema are not modified.

`GuardedRestoreCandidate.capture` deep-copies the decoded document before
wrapping its top-level mapping, so subsequent source-object mutation cannot
change captured nested Guard data. START explicitly refuses a still-quarantined
candidate before aggregate telemetry or session creation. Manual behavior is
unchanged. Emergency verified OFF remains on its existing independent route.
P4 remains closed with exactly one canonical controller/session owner. Guarded
restore activation remains deferred: this source work proves neither target
ESP callback semantics under deployment nor physical acceptance. Synthetic
matrix and test results are in `D123_SPRINT57_EVIDENCE_20261021.md`.

`runtime.production_runtime` constructs one `ProductionChargeController`; it
does not directly instantiate `ManagedChargeController`. The production class
still inherits the base session host because its canonical state initialization,
runtime initialization, target adapter call graph, and restore lifecycle remain
in use. D123 Sprint 52 reduced the production class from 22 method declarations
and 10 base overrides at the starting SHA to 10 declarations and 8 overrides.
Continuous-tail hold, cooling tick snapshot/resume, runtime-signal snapshot and
restore, finish-evidence validation/restore, session extension serialization,
and notification projection now live in
`application.production_session_extensions`; those functions mutate or read the
same host and do not create a second FSM/session owner. The class retains only a
thin `_session_document_extensions` adapter because canonical
`runtime.charge.session_atomic` calls that host hook.

Remaining production override names are `__init__`, `_new_runtime`, `_prep_target`,
`_main_target`, `_desulf_target`, `_mix_target`, `_get_target_v_i`, and
`try_restore_session`. The first seven bind production cooling-runtime creation
and recipe-envelope target adaptation to the inherited state; `try_restore_session`
continues the inherited restore transaction and performs guarded session restore
in the established order. Removing these requires the deferred P2 canonical
session/state lifecycle seam, including MAIN Guard restore admission. See
`D123_SPRINT52_EVIDENCE_20261020.md` for the exact dependency inventory and tests.
`diagnostic_controller.py` subclasses the production host for its distinct
Diagnostic intent. Tests include `test_production_controller.py`,
`test_diagnostic_controller.py`, and the cooling, restore, and finish-evidence
suites.

Sprint 03 removed unused independent cooling, finish-state, and runtime-signal
JSON patch writers. The remaining restore reader uses the canonical read
function in `runtime.charge.persistence`; serialized extension keys are emitted
through the single `_session_document_extensions` host hook during the canonical
complete save. Sprint 52 moved that hook's implementation and extension restore
policy into the application extension owner without changing the session schema
or writer.

## State field inventory and lifecycle

| State | Owner now | Lifecycle/active readers | Risk and intended owner |
|---|---|---|---|
| `_v2_main_plateau_since` | Removed in D123; clock now `ManagedChargeController._main_sample_evidence.plateau_since_s` | Reset on START/session initialization/configuration, stage/transition and cooling; shifted during operator pause; evaluator is new per process and not serialized, matching prior restart behavior | **High.** Canonical owner is evidence module. Historical `v2` field name has no source references after extraction |
| `_v2_runtime`, `_v2_target_voltage_v`, `_v2_last_stage` | Controller | Session init/restore, tick, tracing and diagnostics | **High.** Remaining P2/P3 evidence/session lifecycle work |
| `_v2_trace_session_id`, `_v2_trace_started_at`, identity inputs | Runtime charge session owner for new/restore snapshot; controller stores active snapshot | `runtime.charge.session.TraceIdentitySnapshot`; canonical persistence enriches accepted restore | **High.** Preserve deterministic migration identity; guarded documents remain unmodified and restore-held |
| `_v2_session_signal_context`, recovery/final SAFE_WAIT continuation | Controller plus persistence module contracts | Captured in tick and serialized/restored by production controller and runtime | **Critical.** P2 existing session/persistence owner; keep fail-closed restore |
| `current_stage`, stage times, transition history, target/Ah counters, timers | Controller initialized through controller_state/lifecycle; direct production readers and tick mutations | Session lifecycle, tick, UI, guard and restore | **Critical.** P2/P3 canonical session state and application-owned transition commit |
| `_v2_continuous_tail_since`, `_v2_continuous_tail_stage_start`, `_v2_cooling_pause`, `_finish_evidence`, `_delta_reported`, `_delta_trigger_mode` | Single production host; behavior in `application.production_session_extensions` | MAIN application tick, cooling pause/resume, canonical extension serialization/restore | **High.** Fields remain on the one host; schema and validation unchanged |
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
fail-closed/deferred, and controller tick/session ownership, remaining stage and
Storage/DONE/Manual paths, P4/P5, and physical acceptance remain open.

### Sprint 31 MIX authority dispatch ownership

`ManagedChargeController._apply_authoritative_decision` now delegates its MIX
branch once to `runtime.charge.runtime.mix_scaffold.apply_mix_authority_tick`.
That existing owner applies the MIX evidence mirror, calls
`decide_mix_transition` once, and dispatches the existing finish-hold,
final-SAFE_WAIT, and STOP_AND_DIAGNOSE effects. The controller no longer
contains the MIX decision or those effect branches. This is a residual
orchestration dispatch cut; it does not move MAIN/SAFE_WAIT decisions,
`_run_stage_scaffold_tick`, verified enable commit, or the production `tick`.

The decision call inputs, branch order, effect action keys/values, hold logger,
storage target lookup, invalid-session containment, and action mapping returned
to the existing transaction path are preserved. The runtime owner has no
`execution_port` or RD setter calls; physical transactions and verified commits
remain in the existing application owner. No persistence schema, Guard,
900-second lease, recipes, setpoints, or restart authority changed. Exact
source and validation are in `D123_SPRINT31_EVIDENCE_20261020.md`.

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

At Sprint 10, the typed owner validated the same continuation/session identity,
generation and start timestamp before mutation. It then performed the same DONE
stage edge, restored-target and SAFE_WAIT mirror clearing, DONE-source marker
and canonical session save. Stage history changed through the existing
`current_stage`/session owner before persistence; the temporary
`_done_transition_source_stage` was cleared in `finally`, including save
failure. Sprint 26 below removes that transient marker in favor of explicit
verified Storage intent at the canonical save boundary. The effect contained
only completion result metadata and had no physical intents or setters. Receipt
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

### Sprint 25 DESULFATION completion dispatch convergence

`decide_desulfation` remains the decision owner and the controller keeps
`_main_target(temp)` selection. On `COMPLETE_TO_SAFE_WAIT`, the controller now
dispatches once to the existing
`runtime.charge.runtime.desulfation_completion.complete_desulfation_to_safe_wait`.
That owner captures the exact event-end payload, assembles
`DesulfationCompletionInput`, builds the existing frozen effect and applies it
once. Capture/build failure returns false before state/action mutation; invalid
session identity remains the caller's
`AuthorityDecision(CONTINUE, 'desulfation_completion_session_identity_invalid')`.
Session identity/generation, source/next stages, recovery attempt, AGM step,
targets, clocks, samples, action payload and commit ordering are preserved.
The owner has no RD setter or execution-port dependency. SAFE_WAIT recovery and
final, MAIN, MIX, tick, P2 and P4 were outside this cut. See
`D123_SPRINT25_EVIDENCE_20261019.md`.

### Sprint 26 verified Storage terminal persistence intent

The verified final SAFE_WAIT completion owner now passes explicit
`verified_storage_completion=True` through the controller's canonical save
boundary into `runtime.charge.persistence.save_session`. Persistence no longer
infers Storage authority from the transient `_done_transition_source_stage`
host marker; that field and its initialization/cleanup were removed. The
explicit intent is emitted only after the existing session-bound verified
enable receipt has built the frozen completion effect. Canonical persistence
still owns schema and atomic write; execution-port receipt validation,
transaction ordering, restore admission, terminal OFF fallback and all stored
keys are unchanged. Focused completion/Storage/restore/Guard coverage passed
**21 tests**; full offline discovery passed **2,416 tests / 3 skipped**;
compileall and diff-check PASS. Exact source-only record:
`D123_SPRINT26_EVIDENCE_20261019.md`.

Broader terminal session serialization ownership, Storage/DONE integration,
Manual integration and eventual application-owned tick remain open. P2 MAIN
Guard restore admission remains deferred/fail-closed; P3 is not complete and P4
has not started.

### Sprint 27–28 terminal persistence contract

At exact clean HEAD `7f5e334d2d657b1c22528026fd7f1dafece162c8`, the DONE
document has one canonical serializer/atomic writer in
`runtime.charge.persistence.save_session`, with DONE restore admission and
legacy terminal/OFF normalization in that same persistence owner. Sprint 28
characterized the shared transaction and introduced the frozen
`runtime.charge.terminal_intent.TerminalPersistenceRequest`. Verified Storage
completion creates a Storage/ON request only after its matching verified enable
receipt; STOP_AND_DIAGNOSE creates a terminal/OFF request. Each caller applies
its DONE state before exactly one `_save_session` call. Persistence consumes the
request to establish the in-memory outcome and still selects targets, assembles
the unchanged document schema, completes extensions/Guard state, and performs
the canonical atomic replacement. The typed request contains outcome plus
terminal measurements, not a document or serializer. Writer failure retains
the already-applied caller stage/actions; the canonical writer logs `OSError`
and does not claim rollback. Storage/DONE restore admission and legacy
terminal/OFF normalization remain in persistence. Broader ordinary-session
serialization, Guard restore admission, Manual integration, P4, and P5 remain
open. Exact evidence: `D123_SPRINT28_EVIDENCE_20261019.md`.

### Sprint 29 SAFE_WAIT continuation restore cut

The paired typed/legacy recovery and final SAFE_WAIT continuation
reconstruction implementations moved to
`runtime.charge.session_continuation_restore`; their controller method bodies
were deleted. Controller `try_restore_session` retains orchestration order
after core persistence restore and DESULFATION age restoration. Continuation
admission still binds to restored session identity/generation, stage, retry
count, AGM index and allowed source/next stages. Both implementations moved
together to preserve parity across current and one-way legacy representations.
Core restore admission, fail-closed Guard policy, persistence schema/extension
completion and atomic writer remain with current owners. Focused tests passed
**44 tests**; full Python 3.12 discovery passed **2,423 tests / 3 skipped**.
Exact evidence: `D123_SPRINT29_EVIDENCE_20261020.md`.


### Sprint 29 SAFE_WAIT continuation restore

Recovery and final persisted SAFE_WAIT continuation reconstruction now belongs to `runtime.charge.session_continuation_restore`. That owner parses typed snapshots, validates session ID/generation and stage/counter identity, and performs the existing one-way legacy reconstruction. `ManagedChargeController.try_restore_session` retains ordering, runtime initialization, enrichment, and fail-closed handling. The former `_restore_recovery_safe_wait` and `_restore_final_safe_wait` method bodies were deleted. Persistence schema, atomic writer, age handling, Guard admission, and output authority remain with existing owners. Exact evidence: `D123_SPRINT29_EVIDENCE_20261020.md`.

### Sprint 30 ordinary restore snapshot seam audit

`runtime.charge.persistence.restore_session` assigns the exact restored document to `host._session_restore_document` near line 714. `ManagedChargeController.try_restore_session` reads it in `charge_controller.py` for DESULFATION clock, recovery/final SAFE_WAIT continuations and durable enrichment. `ProductionChargeController.try_restore_session` reads it in `production_controller.py` for persisted MAIN Guard via `main_guard_session.read_guard`, plus MIX finish/runtime signal state. The shared raw snapshot bridges the canonical reader and current consumers. A narrow typed projection omits Guard/extensions; a complete typed wrapper duplicates the schema, while moving the consumer sequence into persistence crosses the explicitly deferred MAIN Guard restore admission boundary. No safe bounded implementation cut was identified. Exact evidence: `D123_SPRINT30_EVIDENCE_20261020.md`.

### Sprint 31 MIX authority orchestration cut

Manual remains an independent program family: production UI START/STOP routes
submit through `ProductionManualUIRoute` to `ProductionManualSessionManager`;
no active coupling to AUTO decision orchestration or controller recipe/state was
found. The next bounded P3 cut moved MIX evidence mirror projection, MIX
transition decision, finish-hold effect dispatch, completion dispatch, and
STOP_AND_DIAGNOSE dispatch from `ManagedChargeController._apply_authoritative_decision`
to `runtime.charge.runtime.mix_scaffold.apply_mix_authority_tick`. The controller
retains authoritative-stage/current-stage admission and delegates once. MIX
profile limit, evidence inputs, action/log payloads, storage target selection,
stale session containment, and downstream application execution are unchanged.
The new owner has no ExecutionPort or RD setter dependency. MAIN and SAFE_WAIT
orchestration, tick trace/evidence assembly, and P2 MAIN Guard restore admission
remain outside this cut. Exact validation and commit are recorded in
`D123_SPRINT31_EVIDENCE_20261020.md`.

### Sprint 32 MAIN authority orchestration cut

`ManagedChargeController._apply_authoritative_decision` delegates its MAIN
branch once to `runtime.charge.runtime.main_scaffold.apply_main_authority_tick`.
That existing owner assembles the unchanged `decide_main_transition` inputs and
dispatches the five existing outcomes (AGM step, DESULFATION entry, MIX entry,
final SAFE_WAIT entry, STOP_AND_DIAGNOSE) through their current typed effects.
The controller retains authoritative-stage/current-stage admission. Target
selection, effect applicators, session/persistence semantics, and the downstream
application execution/verified transaction path are unchanged. The owner has no
ExecutionPort or direct RD setter dependency.

Outer stage routing, DESULFATION/recovery/final SAFE_WAIT dispatch, tick
evidence/trace assembly, terminal persistence ownership, Manual integration,
P2 Guard restore admission and P4 remain outside this cut. Exact validation is
recorded in `D123_SPRINT32_EVIDENCE_20261020.md`.

### Sprint 33 DESULFATION completion authority cut

The DESULFATION branch of `ManagedChargeController._apply_authoritative_decision`
now delegates once to the existing
`runtime.charge.runtime.recovery_scaffold.apply_desulfation_authority_tick`.
That owner calls the unchanged `decide_desulfation`, preserves the elapsed-time
calculation and two-hour completion boundary, obtains the existing MAIN target,
and dispatches through `complete_desulfation_to_safe_wait`. Invalid session
identity still returns the exact `CONTINUE` reason without inventing a recovery
transition. Stage admission, recovery/final SAFE_WAIT decisions, persistence,
and physical execution ownership are unchanged. See
`D123_SPRINT33_EVIDENCE_20261020.md`.

### Sprint 34 recovery SAFE_WAIT authority cut

Both recovery SAFE_WAIT authority call paths now delegate to
`runtime.charge.runtime.recovery_scaffold.apply_recovery_safe_wait_authority`;
the controller-owned method is removed. Continuation identity and generation,
attempt/stage validation, fail-closed stop behavior, fresh Output-OFF sample
gate, strategy decision, requested action payload, and verified-enable token
are preserved. The execution/verified physical transaction remains unchanged.
Final SAFE_WAIT authority, outer routing, trace/evidence assembly, terminal
persistence, Manual integration, and P2 Guard restore admission remain outside
this cut. See `D123_SPRINT34_EVIDENCE_20261020.md`.

### Sprint 35 final SAFE_WAIT authority cut

Both final SAFE_WAIT authority call paths now delegate to
`runtime.charge.runtime.final_safe_wait_authority.apply_final_safe_wait_authority`;
the controller-owned method is removed. The existing immutable effect builder
remains the decision/request builder; fresh-OFF sampling, continuation
validation, fail-closed stop dispatch, and request-result mapping now live in
the same runtime owner. Verified DONE commit and physical output transaction
remain unchanged. See `D123_SPRINT35_EVIDENCE_20261020.md`.

### Sprint 36 SAFE_WAIT compatibility router retirement

Removed `_handle_safe_wait_stage_override`: repository search found no
production call sites, only direct characterization tests. Those tests now
invoke the canonical recovery/final SAFE_WAIT runtime owners, while production
`tick` continues through `_apply_authoritative_decision`. Request payload,
fail-closed unknown/stale continuation handling, verified receipt/token path,
and persistence intent remain covered. See
`D123_SPRINT36_EVIDENCE_20261020.md`.

### Sprint 37 MIX compatibility hook retirement

Removed `_handle_mix_stage_override` after repository search confirmed no
production or test callers; added a regression asserting the characterization
hook stays absent. MIX decisions and effects continue through the existing
modular `tick` / mix-scaffold path. No actuator or transaction ownership
changed. See `D123_SPRINT37_EVIDENCE_20261020.md`.

### Sprint 38 completion-evidence logging

Moved the four record-derived extrema/reversal log projections from
`ManagedChargeController.tick` to
`runtime.charge.evidence.trace_context.log_analysis_events`. Logger identity,
event gating, formatting, stage/session and timestamp values are preserved;
the `metrics` local remains for signal-context and MAIN-evidence assembly.
Decision, persistence and execution remain unchanged. See
`D123_SPRINT38_EVIDENCE_20261020.md`.

### Sprint 53 production host convergence

Starting from exact HEAD `54f26958d6c4eab332120723a2a84f7048383749`,
the production controller declaration count moved from **10 to 1**, and its
overrides of `ManagedChargeController` moved from **8 to 1**. The residual
method is only `try_restore_session`. Initialization and target/runtime
policy now use application/runtime owners on the existing host; session
extension projection is called directly by the canonical atomic writer; and
non-Guard restore adaptation is owned by
`application.production_session_extensions.restore_production_session_state`.

The remaining override calls canonical restore, reads the persisted MAIN Guard
journal, and delegates non-Guard extension restoration. The raw canonical
document handoff and fail-closed Guard ordering are unchanged. This is the
specific P2 boundary preventing inheritance removal; MAIN Guard admission
remains deferred, so P4 inheritance elimination stays open. Full exact-source
counts, verification, and sandbox socket errors are in
`D123_SPRINT53_EVIDENCE_20261020.md`.

### Sprint 54 canonical restore owner

`ManagedChargeController.try_restore_session` now owns the production restore
tail as well as ordinary session restore: after canonical persistence restore,
Custom rejection, DESULFATION clock and continuation reconstruction, shadow
initialization and enrichment, it performs the same Guard journal read and
production extension restoration in the established order. The production
class no longer declares or overrides a method. Runtime and recovery callers
remain unchanged and continue through this single gate. Persistence still holds
guarded documents before mutation/enrichment, so no admission is widened.

The production subclass remains an empty marker class that selects the
production extension fields and recipe target behavior on the single inherited
host. Thus P4 method convergence is complete, but inheritance elimination is
not: removing the marker relationship requires a separate composition-factory
cut. P2 remains partial at the canonical raw-document/Guard admission boundary;
P5 release and physical acceptance remain open. Exact order and tests are in
`D123_SPRINT54_EVIDENCE_20261020.md`.

### Sprint 55A AUTO presentation and diagnostic snapshot cuts

`auto_strategy.py` previously declared six presentation members: the
`_OPERATOR_REASON_TEXT` class mapping and five methods
`_get_stage_max_hours`, `_mix_display_elapsed_s`, `get_timers`,
`_session_rules_summary`, and `get_ai_stage_snapshot`. The five method bodies and
production-specific reason mapping now live as functions/constants in
`application.production_session_extensions`; the canonical inherited host calls
those functions, which operate on its existing fields and durable MIX authority.
`AutoStrategyProductionChargeController` retained only its compatibility class
name and declared no behavior at the Sprint 55A boundary; Sprint 55C removed
that class. The production host's old class-level reason map
was removed. The base host still uses its original limits, summary, timers and AI
snapshot when it lacks production extension state.

Callers are unchanged: stage-limit reads come through restore/lifecycle; timers
and AI snapshots are requested by existing UI/runtime consumers; notification
projection runs in `application.charge_session_tick`. Their application owners
now resolve the mapping from the same host rather than its class. The diagnostic
assessment snapshot mapping was moved from
`DiagnosticProductionChargeController.diagnostic_snapshot` to
`runtime.charge.diagnostics.diagnostic_assessment_snapshot`, called from
`application.charge_stage_tick` after authoritative stage processing. No
assessment state was copied.

Diagnostic stored-specific-gravity refresh (`application.charge_session_tick`
awaits `_refresh_stored_diagnostics`), live bank-fault evidence update
(`application.charge_stage_tick` calls `_update_live_diagnostic_evidence`), and
the pre-transition `_diagnostic_hv_veto` remain on the diagnostic subclass. Their
mutable assessment context and HV veto require a subsequent same-host migration
with explicit caller/order parity. The next P4 cut is to move that context and
refresh/evidence projection to existing runtime/application diagnostic owners,
then route veto through existing stage authority without relaxing the pre-apply
veto. Do not remove the diagnostic subclass until these callers are moved.

`MixActiveAuthorityMixin` remains the durable MIX active-time owner. Its
`_enter_mix` calls the existing MIX entry then begins the durable clock from the
trace session identity. Its `try_restore_session` first invokes the canonical
base restore (including Guard admission/hold and production extension
reconstruction), then detects restored MIX or COOLING sourced from MIX and loads
the durable authority; load failure sets DONE, clears finish/restored targets,
and rejects restore. Callers are production runtime restore and the existing
stage-entry dispatch through the diagnostic host MRO. This exact ordering
crosses the P2 Guard restore and MIX-entry authority boundary. The next specific
P4 cut is to put clock begin/load admission into existing session/runtime owners
on this same host while preserving that order and containment; it must be tested
against `tests/test_mix_active_timeout_integration.py`, restore, cooling and
Guard suites before removing the mix mixin/subclass inheritance. MAIN Guard
restore remains deferred and fail-closed.

Sprint 55A does not change persistence writer, physical execution owner, recipe,
safety, lease or Manual behavior. P2 remains partial; P4 remains open; P5 and
physical acceptance remain open.

### Sprint 55B diagnostic and durable MIX lifecycle update

The live `DiagnosticProductionChargeController` class is removed. The legacy
import name is a direct alias to `ProductionChargeController`; production
bootstrap constructs that canonical class directly. Diagnostic mutable state is
initialized on the production host by `ManagedChargeController`'s existing
production configuration path. `runtime.charge.diagnostics` owns context
assessment, stored SG refresh, live bank-fault update, and the pre-effect HV
veto. `application.charge_session_tick` and `application.charge_stage_tick`
sequence those operations. The veto still runs in the authoritative stage
scaffold before ENTER_DESULFATION/ENTER_MIX effect application.

The `MixActiveAuthorityMixin` class is removed. `MixActiveTimeAuthority` remains
the durable clock implementation, explicitly attached by
`initialize_production_session_state` on the same host. Application session
orchestration begins authority on MIX entry and tracks active/inactive time.
Canonical `ManagedChargeController.try_restore_session` still performs
ordinary restore, then MAIN Guard reconstruction, then production extension
reconstruction; that production extension restores durable MIX authority last.
MIX and COOLING with `source_stage=MIX` both require matching durable session
identity. Missing or invalid authority rejects restore and clears restored target
state. No second session host, persistence writer, or physical writer was added.

See `D123_SPRINT55B_EVIDENCE_20261020.md` for the exact before/after graph and
verification limits.


### Sprint 55C canonical full acceptance

- Canonical Python 3.12 full discovery: **2,462 tests, 3 skipped, PASS**.
- P4 class-shape objective: **CLOSED**; production constructs exactly one canonical `ManagedChargeController` with frozen explicit host configuration and no production controller subclass/mixin.
- Remaining work is P2 session/Guard lifecycle ownership and P5 release/physical gates; no deployment or physical validation occurred.

### Sprint 56 / P2 session restore ownership

`runtime.charge.persistence.restore_session` remains the sole canonical file
reader, persisted schema/migration validator, trace identity applicator, and
ordinary host restore owner. Accepted decoded data is handed to the existing
host as a `RestoredSessionDocument`; `_session_restore_document` no longer
exists. `ManagedChargeController.try_restore_session` is still the startup
decision gate but delegates accepted restore orchestration to
`runtime.charge.session_continuation_restore.finish_session_restore`.

That session owner checks `main_guard_restore_boundary` before continuation
reconstruction or enrichment, then restores DESULFATION age, recovery/final
SAFE_WAIT continuation identity, trace shadow, and durable identity enrichment.
Only after Guard handling does it restore production extensions, including
COOLING and durable MIX authority. It has no physical writer and does not
synthesize Output state. Failed enrichment rejects restore.

Guard-bearing documents are currently rejected inside persistence before any
host mutation, so no journal is ordinarily admitted on restart. This remains
the correct fail-closed boundary until an owner-wide execution lock and
fresh direct Native pre-ON receipt prove matching Output, Iset/OCP, session
generation, and Guard revision while resolving pending command state. Those
are live/native facts and cannot be established by a source-only edit.
See `D123_P2_SESSION_GUARD_CONVERGENCE_EVIDENCE_20261021.md`.


### P2 canonical full acceptance

- Raw `_session_restore_document` coupling removed; accepted ordinary restore uses typed `RestoredSessionDocument`.
- Guard-bearing restore is rejected exactly once by `runtime.charge.persistence.restore_session` before host mutation.
- Continuation owner is domain-layer clean and receives enrichment callback by injection; no persistence back-import.
- Canonical Python 3.12 full discovery: **2,463 tests, 3 skipped, PASS**.
- Remaining P2 boundary is live owner-wide execution + fresh direct ESP Native pre-ON reconciliation for guarded resume; source-only restore ownership is converged.

### Sprint 58 guarded activation ownership update (2026-10-21)

The quarantined candidate remains owned by the existing
`ManagedChargeController` lifecycle and canonical persistence reader. Under
the app-scoped `ExecutionPort._guard_owner_lock`, `StartupRecovery` now checks
the existing direct Native snapshot and MAIN Guard assessor, then rechecks the
same candidate object, full decoded canonical document, session/battery IDs,
Guard revision, non-retired state and freshness immediately before invoking
`ManagedChargeController.try_restore_session` with an immutable,
current-task/current-lock-bound `GuardedRestoreActivationPermit`.
Candidates captured by canonical persistence also retain the exact source
file-byte digest; it is checked during startup revalidation and again when
persistence consumes the permit.

The permit is an evidence value, not mutable session state. The one existing
`runtime.charge.persistence.restore_session` implementation consumes it and
reconstructs `_main_current_guard` plus revision only through the canonical
`read_guard` parser before the existing continuation and production-extension
restore order. Guarded activation skips ordinary identity enrichment to avoid
rewriting Guard authority. It does not issue an execution-port or hardware
writer call. Successful restore clears the candidate and marks the controller
`_guarded_restore_activated_off`; the app-scoped port latch is installed before
restore mutation and blocks both recipe-aware `enable()` and
`request_verified_on()`. Replaying startup after activation returns at this
barrier. `application.charge_session_tick` also exits before automatic
decision/setpoint/enable orchestration while the activated-off marker is
present. Emergency `request_verified_off()` stays independent.

No physical resume owner clears the latch in this sprint. The remaining source
and P5 work is an explicit later transaction that acquires the same lock,
obtains a new direct Native snapshot, reruns `assess_main_guard_before_output_on`
immediately before the ON action, preserves all ordinary safety checks, and
clears the latch only after its authorization/result is committed. That path
must be compiled/flashed/bench-validated against the exact ESPHome contract
before physical use. The source activation does not establish physical
acceptance.

Sprint 59 extends this boundary with `StartupRecovery.guarded_physical_resume`
under that same owner lock. The transaction takes a second direct ESP Native
snapshot immediately before assessment and reruns
`assess_main_guard_before_output_on`; it never reuses activation-time evidence.
Canonical bytes/identities, revision, controller stage/profile, restored Guard,
target, lease, latch and recovery permission are rechecked. The resulting
immutable `GuardedPhysicalResumePermit` carries the Native callback generation,
activation generation, owner task/lock and candidate identity. The existing
ExecutionPort consumes it once. Production has no endpoint installed, so the
only live source result is `READY_BUT_NOT_EXECUTED`. A synthetic endpoint may
return a verified-on receipt; only the receipt-gated block in
`ExecutionPort.execute_guarded_physical_resume` clears the two OFF latches.
Emergency OFF and ordinary START/Manual owners are unchanged.

### Sprint 60 P5 release boundary

Sprint 60 adds source-only release gates and an operator matrix in
`D123_SPRINT60_P5_SOURCE_RELEASE_EVIDENCE_20261021.md`. Existing release
preparation remains authoritative: `tools/node104_atomic_deploy.py` stages an
exact commit with `git archive` and a tracked-file hash manifest; the existing
deployment runbook defines preconditions and rollback. The guarded restore OFF
latch remains active and the production resume endpoint remains uninstalled.
The Sprint 60 source test asserts one runtime host, one canonical session
writer, tracked-only artifacts, the supported interpreter matrix and the
startup OFF/resume boundary. No second installer, owner, or release framework
was introduced.

The last stored deployed-source references are historical and conflict:
`c1298ea2df67bba1e4888de6e830b002b5db2fce` in the 2026-10-04 project-runbook
checkpoint and `8b75cca153f00847d84396aba392472bb7552ad` in the 2026-10-17
D090 observed marker. Neither proves the current installed accepted SHA or
rollback backup. Resolving that requires a later authorized read-only
deployment inventory. Current direct Native evidence, exact firmware/bench
validation, and deployed startup proof are absent. See Sprint 60 evidence for
the source-ready / deploy-ready / physical-ready distinction and matrix.

Sprint 61 extends only the existing offline source release verifier: extracted
tree verification now compares tracked file mode as well as path set, size,
and digest. Exact base archive hash/file count and local historical staging
manifest findings are in `D123_SPRINT61_P5_OFFLINE_MANIFEST_EVIDENCE_20261021.md`.
The installed accepted SHA and durable rollback backup remain unknown because
no current deployment-host evidence is available. Do not infer either from
the two local stage manifests or historical SHA references.

Sprint 62 records an independently reproduced exact-SHA archive and manifest
for clean base `a7cb80e438ca777b6425646a7efc21907c22f743` in
`D123_SPRINT62_P5_SHA_BOUND_RELEASE_EVIDENCE_20261021.md`. The existing
`node104_atomic_deploy.py` source manifest binds a Git archive to the SHA and
per-file path/mode/size/digest. Its transaction simulator validates a
journal-bound backup tree and fail-closed recovery, but it is not a production
rollback command or evidence of the node's current pre-image. The two local
stage directories remain historical source artifacts. Current installed SHA
and durable deployment backup stay **UNKNOWN / UNPROVEN** pending a fresh
read-only inventory from the actual deployment host. Guarded restore remains
OFF-latched and no production physical-resume endpoint is installed.
