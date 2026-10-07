# V3 Legacy Eradication Ledger

Baseline: `main@6eb6980d1e4a4aeeb804ae25a59af8e292a3d324`.

This ledger is a shrinking debt list. Entries may be removed after migration;
new entries require explicit architecture review.

| ID | Reachable legacy boundary | Current evidence | Replacement target | Removal gate | Status |
|---|---|---|---|---|---|
| L-001 | `bot.py -> ProductionComposition -> runtime.v2_runtime substrate` | production imports `runtime.production_runtime`; the retired `runtime.v2_runtime` facade has been deleted | modular composition + lifecycle | production `runtime.v2_runtime` substrate edge removed and exact-head CI verified | CLOSED |
| L-002 | compatibility installer stack inside `ProductionComposition.compose()` | six patch-only compatibility installers retired; residual `install_*` graph is explicitly classified as canonical domain/runtime/ownership/physical/UI composition and guarded against regression | explicit dependency graph | zero production reachability for retired shims + canonical residual installer inventory + full regression | CLOSED |
| L-003 | historical `ChargeController` superclass | `ChargeControllerV2` has no `charge_logic` import or historical superclass; transitive historical support closure and external inherited production surface are both zero | modular stage engine | zero historical superclass/import reachability + parity regression | CLOSED |
| L-004 | `_run_legacy_scaffold_tick -> super().tick()` | production fallback was retired; migrated stages use modular runtime services and unknown/residual historical stages fail closed instead of calling `super().tick()` | explicit modular stage runtime services | exact-head CI proves no production `super().tick()` fallback | CLOSED |
| L-007 | `ProductionStartRunner -> V2StartRunnerAdapter -> v2_startup` | legacy START runner is retired from production; START execution is owned by `application.start_transaction_service` / `StartTransactionRunner` behind the production execution port | modular start/application/execution service | full parity plus exact-head CI | CLOSED |
| L-008 | legacy UI read adapter | retired: OperatorSnapshotProvider consumes explicit OperatorReadSource and a pre-built intent dispatcher; canonical screens receive the detached provider | canonical read model | migrated screens do not use old app | CLOSED |
| L-009 | direct actuator writers outside execution port | live production writers now converge through the application execution port; only approved physical implementation plus quarantined unreachable history contains direct calls | single execution service | static inventory reaches zero outside allowed physical implementation | CLOSED |
| L-010 | `legacy_recipe_adapter` | adapter removed; production consumers use `application.recipe_policy` and the existing recipe engine/envelope | modular recipe/config owner | consumers moved, adapter removed and exact-head CI verified | CLOSED |
| L-011 | `legacy_safety` | compatibility module remains, but live voltage ceilings/MIX windows are derived from modular safety/strategy VariableSpec owners | modular safety/strategy variables | values have one canonical owner | CLOSED |
| L-012 | `legacy_transition_audit` | dead decision source removed; historical trace audit columns remain readable for archived evidence only | canonical decision journal | no legacy transition source | CLOSED |
| L-014 | UI buttons/callbacks scattered across installers/handlers | all production Telegram UI routes are owned by canonical `runtime/ui` modules; historical `runtime/v2_runtime.py` declares no UI routes | modular ScreenSpec/ButtonSpec/action routing | screen-by-screen parity and removal | CLOSED |

## Current migration boundary

**ERADICATION-09: remove historical production graph - LOCAL COMPLETE; REMOTE EXACT-HEAD CI PENDING.**

Pre-boundary remote authority:
ERADICATION-08 functional/documentation HEAD
`cbb5d157f82202a9db15e6c64a6ea62037d2f088`,
GitHub Actions run `#1566` / `37235184475`, Python 3.10/3.11/3.12 PASS.
Documentation handoff HEAD:
`2ef86987ac1d37ececbb2c6e30ba919d0053562f`.

First ERADICATION-09 structural increment:
`eff53c5d359afeb58584be9b5a17ae41ba446457`.

- canonical production runtime identity is now `runtime.production_runtime`;
- `bot.py` has zero production import edge to `runtime.v2_runtime`;
- `runtime.v2_runtime` has been deleted;
- `bot_legacy.py` has been deleted and cannot alias
  `sys.modules`;
- production-oriented characterization tests now inspect/import the canonical
  runtime identity while dedicated compatibility coverage keeps the old import
  name observable;
- exact-head GitHub Actions run `#1568` / `37237082292` PASS on Python
  3.10/3.11/3.12.

ERADICATION-09 checkpoint through `309ea7ea9fcefea624291293b09d215df2b52bae` is remote-verified by GitHub Actions run `#1578` / `37285010255` (Python 3.10/3.11/3.12 PASS). L-001, L-004, L-007, L-008, L-010 and L-012 are closed. ERADICATION-09 remains open only for L-002/L-003: compatibility installers and historical controller superclass reachability.

Production VM104 was not touched. No hardware commands were sent.

## Previous migration boundary - ERADICATION-08

**ERADICATION-08: runtime/composition cutover - REMOTE-VERIFIED COMPLETE.**

Pre-boundary remote authority:
ERADICATION-07 functional HEAD b5e5bff8328d187cd1ddb9c012f2be69e783a4fe,
GitHub Actions run #1564 / 37228622855, Python 3.10/3.11/3.12 PASS.
Documentation handoff HEAD: 80881a978b4b7bf9286477f075493885102af909.

Exact local ERADICATION-08 code HEAD:
517521d30b3708ab6d8366a200bdb587623b5164.

Composition cutover now provides one explicit ProductionComposition owner:

- bot.py is a distinct production module and is no longer replaced through sys.modules;
- production no longer writes bot.main into the historical runtime;
- all compatibility installer calls are owned by ProductionComposition.compose();
- module top level executes one composition call instead of a distributed installer stack;
- startup authority reconciliation, physical-control lifecycle and runtime execution are
  owned by ProductionComposition.run();
- module-level _rd_*, _legacy_main and startup-recovery aliases are retired;
- runtime.production_runtime is the production composition substrate; production startup recovery now imports `runtime.startup_recovery.StartupRecovery` directly, with no production inbound edge to the retired `runtime.v2_startup_recovery` name;
- the temporary __getattr__ compatibility bridge is read-only and delegates through
  composition.runtime. Removing that substrate/bridge belongs to ERADICATION-09.

Local validation on exact code HEAD 517521d30b3708ab6d8366a200bdb587623b5164:

- composition/entrypoint focused suites: PASS;
- startup-authority integration: 2/2 PASS;
- restart/restore HA composition: 1/1 PASS;
- Phase 6 composition root: 5/5 PASS;
- Phase 6 architecture guardrails: 6/6 PASS;
- legacy inventory: 4/4 PASS;
- production physical isolation: 2/2 PASS;
- autonomous install-order contract: 4/4 PASS;
- V1 UI compatibility: 9/9 PASS;
- python -m compileall -q .: PASS;
- git diff --check: PASS;
- CI-equivalent local discovery: 1915 PASS, 2 skipped;
- test_manual_context_v2: 4/4 PASS separately. Local Python 3.14 leaves a
  post-test background/teardown process alive after reporting OK, so these four
  tests were isolated from the main discovery run. Total logical coverage:
  1919 tests, 2 skipped, 0 failures.

Production VM104 was not touched. No hardware commands were sent.

Remaining gate: commit this documentation checkpoint, push PR #29 and require
exact-head GitHub CI PASS on Python 3.10/3.11/3.12. Only then close
ERADICATION-08 as remote-verified and begin ERADICATION-09.
## Previous migration boundary — ERADICATION-06

**ERADICATION-06: safety and execution convergence — REMOTE-VERIFIED COMPLETE.**

Exact code HEAD:
`c63f75659d1809c34ba753b7045eb119ec0106c0`.

The live physical-write graph now converges through the application-scoped
`ExecutionPort`:

- START, Mix-only START and Manual use the same execution owner;
- controller action batches execute through the same port, preserving the
  existing two-phase verified-enable commit contract;
- operator pause/power-toggle, restart restore, lifecycle restore and link
  recovery no longer call HA setters/output methods directly;
- diagnostic persistence/probe and managed adoption/MIX OFF paths route through
  the same application execution owner;
- direct physical calls in the production scan are confined to the approved
  physical implementation stack:
  `application/execution_port.py`, `hass_api.py`, `runtime_safety_strict.py`,
  `managed_runtime_safety.py`, and `safe_output.py`;
- `recipe_output.py` and `recovery_orchestrator.py` remain quarantined historical
  compatibility modules with no production inbound import edge.

Safety value ownership also converged:

- PB automatic voltage ceiling is owned by
  `runtime/safety/voltage_variables.py`;
- MIX voltage/current targets, authority windows and finish hold are owned by
  `runtime/charge/strategy/mix_variables.py`;
- `legacy_safety.py`, `config.py` and reporting surfaces derive compatibility
  values from those canonical owners instead of defining competing values;
- typed safety decisions remain owned by `runtime/safety/engine.py`;
- verified OFF/ON ordering, readback verification, containment and edge-lease
  semantics are unchanged.

Validation on exact code HEAD `c63f75659d1809c34ba753b7045eb119ec0106c0`:

- execution convergence suite: 12/12 PASS;
- safety/execution convergence suite: 6/6 PASS;
- legacy actuator inventory: 2/2 PASS;
- runtime safety V2: 26/26 PASS;
- runtime safety audit: 2/2 PASS;
- safe-output: 30/30 PASS;
- physical execution gate: 4/4 PASS;
- verified-OFF execution: 2/2 PASS;
- autonomous startup authority contract: 8/8 PASS;
- `python -m compileall -q .`: PASS;
- `git diff --check`: PASS;
- full local CI-equivalent suite: **1830 tests PASS, 2 skipped**.

ERADICATION-06 is remote-verified. GitHub Actions exact-head run
`#1524` / `37177596599` passed on Python 3.10, 3.11 and 3.12.

Next exact boundary: `ERADICATION-07: UI cutover`.

Previous boundary ERADICATION-05 is remote-verified by GitHub Actions run
`#1522` / `37172231948` on Python 3.10, 3.11 and 3.12.

Production changed: NO.

Hardware commands sent: NO.

## ERADICATION-02 progress

The canonical MAIN transition decision, MAIN strategy variables, base MAIN target
selection and the 12 A stage-current ceiling have been moved to modular owners.
`charge_authority.py` now re-exports the canonical MAIN decision for compatibility.

The first-stage evidence owner has also moved to
`runtime/charge/evidence/first_stage.py` with all evidence thresholds declared in
`runtime/charge/evidence/first_stage_variables.py`. The root-level
`first_stage_evidence.py` is now import compatibility only.

Authoritative MAIN no longer calls historical `ChargeController.tick()` and no
longer uses blanking or stage-clock masking. Its accepted link-loss, thermal,
history/reporting and stage bookkeeping mechanics are now provided by
`runtime/charge/runtime/main_scaffold.py`, with runtime/safety timing values in
module-owned variable files.

ERADICATION-02 is complete for MAIN. Exact-head CI run `#1510`
(`37141127400`) passed on Python 3.10, 3.11 and 3.12 before ERADICATION-03
started.

## ERADICATION-03 progress

The entire intermediate recovery chain is now owned by modular V3 code:

`MAIN -> DESULFATION -> recovery SAFE_WAIT -> verified MAIN`.

DESULFATION target selection, duration and stage-owned protection margin have
single variable owners. Recovery SAFE_WAIT owns typed continuation validation,
fresh physical OFF gating, relaxation/timeout decisions and the request for a
verified re-enable transaction.

Restart restores the exact persisted DESULFATION active-stage clock rather than
allowing historical Ah-based reconstruction to rewrite the two-hour recovery
budget. The continuation persists recovery attempt, AGM step, session identity
and session generation. Stale generations fail closed.

The historical superclass is still present, but its mutating stage path is
unreachable for authoritative MAIN, DESULFATION and recovery SAFE_WAIT. MIX and
final SAFE_WAIT were the next debt and are now cut over in ERADICATION-04.

## 2026-10-05 handoff checkpoint — ERADICATION-09 final convergence

Remote-verified functional authority:

- PR #29 branch: `refactor/v3-modular-legacy-eradication`;
- exact remote functional HEAD: `309ea7ea9fcefea624291293b09d215df2b52bae`;
- GitHub Actions run `#1578` / `37285010255`: PASS on Python 3.10, 3.11 and 3.12;
- local documentation checkpoint above that functional state:
  `ea6200b1194b20232baeeea9d0adeb2052a33ee3`.

Closed ERADICATION-09 debt at the remote-verified functional checkpoint:

- L-001 canonical production runtime identity;
- L-004 historical `super().tick()` production fallback;
- L-007 legacy START runner/adapter;
- L-008 legacy UI read adapter / runtime-object read-model coupling;
- L-009 direct actuator writers outside the approved execution implementation;
- L-010 legacy recipe adapter;
- L-011 duplicate legacy safety-value ownership;
- L-012 legacy transition-audit decision source;
- L-014 scattered historical UI route ownership.

Remaining ledger debt is now only:

- **L-002** — compatibility installer stack still composes residual historical helpers;
- **L-003** — `ChargeControllerV2(ChargeController)` still inherits the historical controller for residual compatibility helpers/state.

Current uncommitted local worktree is the next ERADICATION-09 contraction increment.
It is intentionally **not** part of the remote-verified authority above. The work
extracts residual `charge_logic.py` value/persistence ownership into modular
owners before attempting superclass retirement:

- new `runtime/charge/persistence.py` for session-file and restore-age ownership;
- new `runtime/charge/strategy/exit_variables.py` for MIX exit thresholds;
- expanded `runtime/safety/variables.py` ownership for OVP/OCP margins,
  watchdog timeout and high-voltage watchdog threshold/timeout;
- consumers are being moved away from `charge_logic.py` constants while keeping
  accepted values and semantics unchanged.

Dirty worktree files at handoff:

`charge_controller.py`,
`done_storage_restore.py`,
`manual_mode.py`,
`manual_runtime.py`,
`manual_text.py`,
`mix_active_authority.py`,
`mix_current_containment.py`,
`production_controller.py`,
`production_guardrails_v2.py`,
`runtime/charge/profiles/manual.py`,
`runtime/production_runtime.py`,
`runtime/safety/variables.py`,
`runtime_safety.py`,
`managed_runtime_safety.py`,
plus untracked `runtime/charge/persistence.py` and
`runtime/charge/strategy/exit_variables.py`.

Do not mark this dirty increment PASS until focused parity, `compileall`,
`git diff --check`, full suite, commit/push and exact-head GitHub CI all pass.

Next exact boundary after that contraction:

1. prove residual historical controller helpers/state have modular owners;
2. remove `ChargeControllerV2(ChargeController)` superclass reachability (L-003);
3. retire the remaining compatibility installer stack that exists only to compose
   historical helpers (L-002);
4. run a production import/reachability scan proving no historical FSM production
   edge remains;
5. archive/reference-capture compatibility files before deletion;
6. exact-head CI PASS, then close ERADICATION-09 and the full 01–09 migration.

Production VM104 changed: **NO**.
Hardware commands sent: **NO**.


## 2026-10-05 ERADICATION-09 dependency-contraction checkpoint

Status: local PASS, awaiting exact-head remote CI before beginning L-003 mutation.

No ledger item is closed by this increment. Remaining debt is still:

- **L-002** — compatibility installer stack in `ProductionComposition.compose()`;
- **L-003** — historical `ChargeController` superclass reachability.

Pre-L-003 ownership contraction completed:

- session filename and session-start maximum age -> `runtime/charge/persistence.py`;
- MIX ΔV/ΔI exit references -> `runtime/charge/strategy/exit_variables.py`;
- stage-current ceiling, OVP/OCP margins and watchdog/high-voltage watchdog values -> `runtime/safety/variables.py`.

Accepted values are preserved 1:1. Contract tests reject reintroduction of these historical value imports into the migrated consumers and assert that the sole remaining `charge_logic` import in `charge_controller.py` is `ChargeController`.

Observed residual L-003 dependency: inherited historical `_save_session()` still resolves `charge_logic.SESSION_FILE`; the V3 persistence reader no longer does. This is retained only until superclass retirement and is explicitly covered by transitional regression fixtures.

Validation: focused PASS; compileall PASS; diff-check PASS; full CI-equivalent discovery 1925 PASS / 2 skipped.

Production VM104 changed: NO. Hardware commands sent: NO.


## 2026-10-05 L-003 inherited dependency inventory

L-003 remains **OPEN**, but its residual reachability is now bounded.

At starting HEAD `0d9dc707469f689e35e0ccbdd2aac932a2e51e22`:
- historical `ChargeController.tick()` is absent from the transitive support closure;
- `charge_controller.py` has exactly one `charge_logic` import edge:
  `ChargeController`;
- the exact remaining inherited support closure is 29 methods covering controller
  initialization/state, lifecycle, persistence/restore, target/temperature helpers,
  protection-limit helpers and bookkeeping;
- `tests/test_v3_l003_inherited_dependency_inventory.py` fails on closure expansion
  or historical tick re-entry.

Validation: focused 2 PASS; compileall PASS; diff-check PASS; full CI-equivalent
discovery 1927 PASS / 2 skipped.

This checkpoint does not move historical behavior to a renamed compatibility
monolith and does not close L-003. The next mutation must assign each remaining
support dependency to an existing or minimal modular owner and then remove
`ChargeControllerV2(ChargeController)` plus the historical import edge.

L-002 remains OPEN and must not be changed until L-003 retirement proves which
compatibility installers are genuinely unreachable.

Production VM104 changed: NO. Hardware commands sent: NO.


## 2026-10-06 L-003 state ownership contraction

L-003 remains **OPEN**, but the historical superclass now owns materially less of
the live controller surface.

Removed from inherited dependency:
- historical constructor / initial state bootstrap;
- `current_stage` descriptor;
- `is_active` descriptor;
- stage/profile identifiers used by production.

New canonical owner:
- `runtime/charge/controller_state.py`.

Parity guard compares the compatibility-shaped initialized state against the
historical constructor, including deque capacities and default values.

Validation: inventory/state 5 PASS; ChargeControllerV2 7 PASS; production controller
26 PASS; runtime safety 43 PASS; persistence 17 PASS; full CI-equivalent discovery
1930 PASS / 2 skipped; compileall PASS; diff-check PASS.

No historical transition authority was restored or copied. Historical `tick()`
remains outside the dependency closure. L-003 is not closed until import and
inheritance from `charge_logic.ChargeController` are both absent.

Production VM104 changed: NO. Hardware commands sent: NO.


## 2026-10-06 L-003 bookkeeping/lifecycle contraction

L-003 remains **OPEN**.

Additional historical inherited support retired:
- stage/bookkeeping reset helpers;
- restored-target and Delta/blanking reset helpers;
- start/start_custom;
- session initialization/reset;
- stop.

Canonical owners:
- `runtime/charge/controller_state.py`;
- `runtime/charge/runtime/variables.py` for the accepted 120 s Delta monitor delay;
- `runtime/charge/lifecycle.py`.

Full CI-equivalent regression remains green: 1930 PASS / 2 skipped.
Historical `tick()` remains unreachable from the inherited support closure.

Next residual authority to retire is session persistence/restore, then target,
temperature/protection and diagnostic/operator helpers. L-003 remains open until
the superclass/import edge is absent.

Production VM104 changed: NO. Hardware commands sent: NO.


## 2026-10-06 L-003 persistence/restore extraction

L-003 remains **OPEN**. Persistence ownership moved to `runtime.charge.persistence` with explicit session-path injection preserving the existing runtime/test contract. Historical `_clear_session_file`, `_save_session` and `try_restore_session` are no longer required by the V2 superclass closure.

Full CI-equivalent regression: 1930 PASS / 2 skipped. Historical `tick()` remains outside the dependency closure.

Residual work: target/temperature/protection and bounded diagnostic/operator helpers, then zero-reachability removal of the superclass/import edge.

Production VM104 changed: NO. Hardware commands sent: NO.


## 2026-10-06 L-003 target/temperature/protection extraction

Status: **L-003 OPEN, materially contracted**.

Accepted semantics now have modular ownership for automatic target selection,
temperature compensation, and phase protection margins. Historical inheritance
no longer supplies:
- PREP/MAIN/profile/restored target selection;
- temperature compensation coefficient/delta/application;
- normal and DESULFATION phase protection-limit adapters.

Regression inventory now reports only three methods in the inherited transitive
support closure: `_make_log_event_end`, `_post_charge_profile_params`, and
`_record_safe_wait_sample`.

Validation: 6 L-003 inventory/parity PASS; 7 controller PASS; 26 production
controller PASS; compileall PASS; diff-check PASS; full CI-equivalent local
discovery 1931 PASS / 2 skipped.

No historical transition authority was restored. L-002 is unchanged and remains
OPEN until L-003 reaches zero historical superclass/import reachability.

Production VM104 changed: NO. Hardware commands sent: NO.


## 2026-10-06 L-003 zero transitive historical support closure

Status: **L-003 OPEN, internal historical dependency = ZERO**.

`ChargeControllerV2` no longer has any transitive method dependency on inherited
historical `ChargeController` helpers. Post-charge thresholds, SAFE_WAIT sampling,
and stage-end log payload construction were extracted with parity tests.

Validation: 7 L-003 inventory/parity PASS; full CI-equivalent local discovery
1932 PASS / 2 skipped.

Residual L-003 dependency is now exclusively external compatibility API inherited
through the superclass. That bounded surface must be migrated before the superclass
and `charge_logic` import can be removed.

L-002 remains OPEN and unchanged.

Production VM104 changed: NO. Hardware commands sent: NO.


## 2026-10-06 L-003 CLOSED - historical ChargeController superclass retired

Status: **CLOSED**.

Closure criteria satisfied:
- `ChargeControllerV2` has no `charge_logic` import;
- `ChargeControllerV2` has no historical superclass;
- inherited transitive method closure = empty;
- externally referenced inherited production API = empty;
- accepted canonical values remain owned by modular V3 modules;
- no legacy FSM/tick authority was reintroduced.

Final modular ownership added/confirmed:
- controller state: `runtime.charge.controller_state`;
- lifecycle/reset: `runtime.charge.lifecycle`;
- persistence/restore: `runtime.charge.persistence`;
- target and temperature policy: strategy modules;
- protection limits: `runtime.safety.variables` and desulfation variables;
- post-charge thresholds: `runtime.charge.post`;
- stage/exit/timer compatibility: `runtime.charge.runtime.support`;
- read-only compatibility diagnostics: `runtime.charge.diagnostics`.

Accepted EFB active-Mix authority remains 24 h. Historical 20 h text/value is
treated as the already-recorded legacy conflict, not as production authority.

Validation after inheritance removal: 1934 PASS / 2 skipped locally under the
CI-equivalent environment; focused guards and compile/diff gates PASS.

Production VM104 changed: NO.
Hardware commands sent: NO.

ERADICATION-09 remaining ledger item: **L-002 OPEN**.


## 2026-10-06 L-002 increment - Manual-OFF compatibility wrapper retired

Status: **L-002 OPEN, first installer retired**.

Production composition no longer installs `auto_manual_off_v2`. Its sole runtime
contract (Manual-OFF armed state is inert to AUTO chemistry until the external
terminal condition fires) is now explicit inside `ChargeControllerV2`.

Proof:
- direct source guard: production `bot.py` contains no
  `install_auto_manual_off_contract` / `auto_manual_off_v2` edge;
- focused contract tests: 6 PASS;
- full CI-equivalent local discovery: 1936 PASS / 2 skipped;
- compileall/diff-check: PASS.

The compatibility file is intentionally retained pending the final
archive/reference-capture step. L-002 closes only after every remaining installer
is either proven canonical/required or retired, followed by a zero-reachability
production graph proof.

Production VM104 changed: NO. Hardware commands sent: NO.


## 2026-10-06 L-002 increment - production guardrail wrapper retired

Status: **L-002 OPEN, two compatibility installers retired**.

`production_guardrails_v2` is no longer installed by production composition.

Semantic ownership after retirement:
- Vin is permanently PSU-health-only in `runtime.production_runtime`;
- Cooling continuation authority is direct controller behavior;
- `runtime.charge.runtime.cooling_guard` owns pure durable-token validation.

Structural proof:
- `bot.py` contains no `install_production_guardrails` call/import;
- no installed-marker is required by production;
- fail-closed Cooling restore/resume behavior is covered directly.

Validation: focused 5 + 13 + 4 + 3 PASS; compileall/diff-check PASS; full
CI-equivalent local discovery 1936 PASS / 2 skipped.

Reference file deletion is deferred to the final archive/reference-capture gate.
L-002 remains open for the remaining composition-time compatibility wrappers.

Production VM104 changed: NO. Hardware commands sent: NO.


## 2026-10-06 L-002 increment - Output readback wrapper retired

Status: **L-002 OPEN, three compatibility installers retired**.

Production no longer installs `live_output_readback_v2`.
The force-updated register-18 Output heartbeat is promoted by
`rd6018_telemetry.canonicalize_live()`, which is already on the authoritative
`HassClient.get_all_live()` path before runtime-safety captures raw telemetry.

Therefore no late reader monkey-patch is required for HANDS_OFF or managed safety
semantics.

Validation: telemetry 8 PASS; install-order 4 PASS; runtime-safety 43 PASS;
Hass-focused exit 0; compileall/diff-check PASS; full CI-equivalent discovery
1936 PASS / 2 skipped.

Reference file deletion remains deferred to the final archive/reference-capture
gate. L-002 remains open for the residual installer graph.

Production VM104 changed: NO. Hardware commands sent: NO.


## 2026-10-06 L-002 increment - Telegram bootstrap wrapper retired

Status: **L-002 OPEN, four compatibility installers retired**.

Production composition no longer patches the aiogram bot with
`telegram_startup_resilience`. The transport owner
`telegram.runtime.ResilientBootstrapBot` now implements the same bounded bootstrap
retry contract directly.

Validation:
- resilience 4 PASS;
- transport adapter 5 PASS;
- entrypoint 13 PASS;
- legacy inventory 4 PASS;
- compileall/diff-check PASS;
- full CI-equivalent discovery 1936 PASS / 2 skipped.

The reference file is retained until final archive/reference capture.
Next L-002 work must classify the remaining `install_*` calls by semantic role:
only compatibility patches are retirement candidates; canonical composition wiring
must remain.

Production VM104 changed: NO. Hardware commands sent: NO.


## 2026-10-06 L-002 increment - soft watchdog compatibility wrapper retired

Status: **L-002 OPEN, five compatibility installers retired**.

Production composition no longer replaces `soft_watchdog_loop` through
`soft_watchdog_containment`. The runtime task is canonical again and delegates
each decision cycle to `runtime.safety.soft_watchdog.soft_watchdog_poll_once()`.

The migration preserves the accepted authority model: Pb containment is suspended
outside reconciled managed authority, proven-OFF idle outages remain passive, and
managed/energized outages use bounded hard-stop attempts without a 10-second
command storm.

Validation: watchdog 11 PASS; autonomous composition 2 PASS; entrypoint 13 PASS;
namespace 3 PASS; compileall/diff-check PASS; full CI-equivalent discovery
1937 PASS / 2 skipped.

The root compatibility file remains reference-only until the final
archive/reference-capture gate.

Next L-002 candidate: `done_storage_restore`, which still monkey-patches
controller persistence/restore/tick and operator pause behavior and therefore
requires a separate parity-preserving extraction.

Production VM104 changed: NO. Hardware commands sent: NO.


## 2026-10-06 L-002 increment - Done/Storage restore wrapper retired

Status: **L-002 OPEN, Done/Storage installer retired**.

Production no longer installs `done_storage_restore`.

Canonical ownership:
- durable Done/Storage classification and persistence:
  `runtime.charge.persistence`;
- Done state initialization: `runtime.charge.controller_state`;
- restore/auto-enable/operator-pause gates: `runtime.production_runtime`.

Safety/semantic proof:
- only explicitly versioned Storage + Output ON records may re-energize;
- ambiguous/legacy Done remains terminal/OFF fail-closed;
- Storage records persist canonical Storage targets rather than stale prior HV
  device setpoints;
- terminal normalization preserves original terminal V/I/Ah evidence and changes
  only Done intent/version metadata.

Validation: focused 9 + 4 + 5 + 26 PASS; compileall/diff-check PASS; full
CI-equivalent discovery 1937 PASS / 2 skipped.

The compatibility source file remains reference-only pending the final archive gate.
No VM104 mutation. No hardware command.


## 2026-10-06 ERADICATION-09 local closure candidate

Status: **LOCAL COMPLETE; REMOTE EXACT-HEAD CI PENDING**.

L-002 closure proof:
- retired patch-only compatibility modules:
  `auto_manual_off_v2.py`,
  `done_storage_restore.py`,
  `live_output_readback_v2.py`,
  `production_guardrails_v2.py`,
  `soft_watchdog_containment.py`,
  `telegram_startup_resilience.py`;
- all six had zero production import reachability before deletion;
- exact final blob IDs / source commits are preserved in
  `docs/ERADICATION_09_COMPATIBILITY_REFERENCE.md`;
- the remaining `ProductionComposition.compose()` install graph is explicitly
  classified and regression-locked as canonical domain, runtime/ownership,
  physical-validation, and operator-UI composition;
- namespace characterization no longer counts attributes owned only by deleted shims.

L-003 remains CLOSED:
- no historical `ChargeController` superclass;
- no `charge_logic` import edge in `ChargeControllerV2`;
- historical transitive support closure = zero;
- external inherited production surface = zero.

Final local proof after physical compatibility-source deletion:
- L-002 composition inventory: 3 PASS;
- runtime namespace contract: 3 PASS;
- canonical Manual-OFF contract: 2 PASS;
- diagnostic controller: 6 PASS;
- charge-logic contraction guard: 3 PASS;
- compileall: PASS;
- diff-check: PASS;
- full CI-equivalent discovery: **1936 PASS / 2 skipped**.

The repository-local migration is therefore complete. The current GitHub PR head is
still the earlier remote checkpoint `c8ca6010a5af11e4128e20eb2aa1a8f20a3ba2c9`;
the local final tree must be synchronized and pass exact-head GitHub Actions on
Python 3.10 / 3.11 / 3.12 before ERADICATION-09 may be declared remote-verified.

Production VM104 changed: NO.
Hardware commands sent: NO.


## 2026-10-07 post-ERADICATION production namespace pass

Status: **implementation complete locally; exact-head CI pending**.

The compatibility runtime is already deleted. This follow-on pass removes the
historical version namespace from production-reachable Python module filenames
and imports. No compatibility aliases are introduced. The old startup-recovery
duplicate is deleted and the comparison module is renamed to a neutral name.

Guard: `tests/test_production_module_namespace.py` requires zero production
Python filenames in the historical `v2` namespace and rejects imports of the
retired module names.

This pass intentionally does not rewrite persisted/session keys, external
telemetry entity IDs, or callback-data tokens merely by textual substitution;
those are compatibility/state boundaries and require separate fail-closed
migration if changed.


## 2026-10-07 production type normalization

The post-ERADICATION namespace cleanup now extends to current production types and
composition API. Historical type names such as `ChargeControllerV2`,
`ProductionChargeControllerV2`, `V2RuntimeSafetyGuard`, `V2RuntimeLifecycle` and
V2 START transaction DTO/adapter names are removed from production sources.
Current owners use neutral names (`ManagedChargeController`,
`ProductionChargeController`, `ManagedRuntimeSafetyGuard`,
`ProductionRuntimeLifecycle`, `StartTransaction*`, `StartEventContext`).

This pass does not rename persisted session keys, telemetry entity IDs or Telegram
callback-data tokens. Those values cross restart/UI protocol boundaries and require
explicit fail-closed migration rather than textual substitution.


## 2026-10-07 shadow/migration island eradication

Static import-graph analysis from `bot.py` plus an external-inbound scan proved a
closed shadow/migration cluster had zero callers outside the cluster. The cluster
included obsolete dual-runtime, decision-authority shadow/parity, telemetry and
configuration ownership rehearsal, staged-ownership, transition, shadow observer,
evidence/acceptance and legacy-domain adapter modules.

Because these modules were unreachable from production and tools, they were
deleted rather than renamed or wrapped. Phase/epic tests whose only purpose was
to characterize that retired island were deleted with it. The historical
Workstream-1 audit test was also removed because it asserted obsolete facts such
as `V2 remains execution owner` and `NOT READY FOR REAL OWNERSHIP TRANSITIONS`.
Historical audit documents remain evidence only and are not CI authority.

Current architecture guards now require the retired shadow/migration module set
to remain absent. No production behavior or physical safety semantics changed.


## 2026-10-07 historical charge FSM eradication

Operational-root reachability (production bot + tools + standalone CLIs) proved
`charge_logic.py` and its sole helper `legacy_safety.py` had no live inbound edge.
The historical FSM and safety compatibility source were deleted rather than kept
as dormant fallback code.

Tests that exercised only the historical controller were deleted. Current manual,
Mix, recovery, persistence, diagnostics and fail-closed tests were retained and
rewired to current owners; parity-with-legacy inventory was replaced by direct
absence/ownership guards. No current production source imports either historical
module.

External persisted/session keys are unchanged in this pass. Physical/electrical
safety semantics remain owned by current strategy/safety/execution modules.


## 2026-10-07 application contract island eradication

Operational-root reachability (production bot, standalone CLIs and tools) proved
a closed application/presentation compatibility island had zero inbound edges.
The retired island contained phase-era actuator/containment/configuration/domain
contracts, alternate application composition/lifecycle, old dry-run/start adapters,
old Telegram adapter/panel-store and old presentation panel modules.

The island was deleted rather than wrapped. Phase/epic tests whose only subject
was that island were removed. The live `application.execution_intent` contract and
`application.execution_port` were explicitly retained because the physical
execution owner imports and uses them. The remaining operator read-path and
implicit-runtime-start checks were rewritten as current runtime guardrails.

No production route, execution semantics, persisted session state or hardware
behavior changed in this boundary.


## 2026-10-07 root compatibility eradication

Operational-root reachability proved the remaining root compatibility set
(`first_stage_evidence.py`, `live_recovery_bridge.py`,
`mix_current_containment.py`, `rd_operation_mode.py`, `recipe_output.py`,
`recovery_orchestrator.py`, `recovery_runtime.py`) had zero live inbound edges.

The first-stage re-export was removed after tests were moved to the canonical
`runtime.charge.evidence.first_stage` owner. The other modules and their direct
characterization tests were removed rather than preserved as dormant fallback
paths. Architecture guards now require these root compatibility files to remain
absent.

No live production route, persisted session key or hardware behavior changed in
this boundary.


## 2026-10-07 final bot runtime bridge eradication

The production entrypoint `bot.py` is now composition-only. Its temporary module
`__getattr__` delegation to `runtime.production_runtime` is removed, composition
locals no longer use `_legacy`, and the lifecycle dependency is named
`runtime_main`. Runtime controller/router/HASS/UI state must be imported from the
canonical runtime owner directly rather than read through `bot`.

Regression coverage requires the bridge and `_legacy`/`legacy_main` terminology
to remain absent from `bot.py`. No actuator, safety, persisted-state or physical
behavior changes are part of this boundary.


## 2026-10-07 staged runtime skeleton eradication

The unused Phase-era runtime container was removed after proving zero production
and tool callers. Deleted surfaces include `runtime.app.RuntimeApp`,
`RuntimeDependencies`, the duplicate generic lifecycle manager, and the
`runtime.application` context/orchestrator/lifecycle package. The package root
`runtime.__init__` no longer provides lazy compatibility exports.

Live leaf components were retained and tested directly: `ChargeService`,
`ChargeStateProvider`, and replay models/runner/comparator. Replay tests now use
an injected minimal orchestrator contract instead of retaining the dead staged
application container. Production `ProductionRuntimeLifecycle` is unchanged.

No production execution, physical safety, persisted-state, Telegram protocol,
or hardware behavior changed in this boundary.


## 2026-10-07 legacy charge adapter retirement

`runtime.charge.adapters.legacy.LegacyChargeProgramAdapter` had zero production
or operational callers and was only exercised by its own characterization test.
The temporary adapter and its public package export were deleted. Historical
Phase 4D/4E documents remain evidence only and are not current runtime authority.


## 2026-10-07 residual legacy adapter retirement

Post-ERADICATION caller analysis showed the remaining UI/action/diagnostic/bank-fault/
hardware/execution-policy legacy adapters had zero production or operational callers.
Only characterization tests and package exports kept them alive. Those adapter surfaces
and parity-only tests were removed while live UI commands, diagnostics scoring, physical
bridge interfaces and execution policy remain unchanged.
