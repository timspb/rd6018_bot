# V3 Legacy Eradication Ledger

Baseline: `main@6eb6980d1e4a4aeeb804ae25a59af8e292a3d324`.

This ledger is a shrinking debt list. Entries may be removed after migration;
new entries require explicit architecture review.

| ID | Reachable legacy boundary | Current evidence | Replacement target | Removal gate | Status |
|---|---|---|---|---|---|
| L-001 | `bot.py -> ProductionComposition -> runtime.v2_runtime substrate` | production now imports `runtime.production_runtime`; `runtime.v2_runtime` is a read-only compatibility facade with no production inbound import edge | modular composition + lifecycle | production `runtime.v2_runtime` substrate edge removed and exact-head CI verified | CLOSED |
| L-002 | compatibility installer stack inside `ProductionComposition.compose()` | installer order is centralized under one explicit composition owner; no installer call executes independently at module top level | explicit dependency graph | retire remaining compatibility installers with the historical runtime graph | IN_PROGRESS |
| L-003 | `ChargeControllerV2(ChargeController)` | automatic MAIN, DESULFATION, recovery SAFE_WAIT, MIX and final SAFE_WAIT use modular decision/runtime owners; production Custom/Manual no longer enters the historical controller; superclass remains only for residual compatibility stages/helpers | modular stage engine | migrate residual compatibility stages/helpers until superclass execution is unreachable | IN_PROGRESS |
| L-004 | `_run_legacy_scaffold_tick -> super().tick()` | production fallback was retired; migrated stages use modular runtime services and unknown/residual historical stages fail closed instead of calling `super().tick()` | explicit modular stage runtime services | exact-head CI proves no production `super().tick()` fallback | CLOSED |
| L-007 | `ProductionStartRunner -> V2StartRunnerAdapter -> v2_startup` | legacy START runner is retired from production; START execution is owned by `application.start_transaction_service` / `StartTransactionRunner` behind the production execution port | modular start/application/execution service | full parity plus exact-head CI | CLOSED |
| L-008 | legacy UI read adapter | retired: OperatorSnapshotProvider consumes explicit OperatorReadSource and a pre-built intent dispatcher; canonical screens receive the detached provider | canonical read model | migrated screens do not use old app | CLOSED |
| L-009 | direct actuator writers outside execution port | live production writers now converge through the application execution port; only approved physical implementation plus quarantined unreachable history contains direct calls | single execution service | static inventory reaches zero outside allowed physical implementation | CLOSED |
| L-010 | `legacy_recipe_adapter` | adapter removed; production consumers use `application.recipe_policy` and the existing recipe engine/envelope | modular recipe/config owner | consumers moved, adapter removed and exact-head CI verified | CLOSED |
| L-011 | `legacy_safety` | compatibility module remains, but live voltage ceilings/MIX windows are derived from modular safety/strategy VariableSpec owners | modular safety/strategy variables | values have one canonical owner | CLOSED |
| L-012 | `legacy_transition_audit` | dead decision source removed; historical trace audit columns remain readable for archived evidence only | canonical decision journal | no legacy transition source | CLOSED |
| L-014 | UI buttons/callbacks scattered across installers/handlers | all production Telegram UI routes are owned by canonical `runtime/ui` modules; historical `runtime/v2_runtime.py` declares no UI routes | modular ScreenSpec/ButtonSpec/action routing | screen-by-screen parity and removal | CLOSED |

## Current migration boundary

**ERADICATION-09: remove historical production graph - IN PROGRESS.**

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
- `runtime.v2_runtime` is a read-only historical import facade;
- `bot_legacy.py` is a non-executable read-only facade and no longer aliases
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
- runtime.v2_runtime remains encapsulated only as the production composition substrate;
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
  `runtime_safety_v2.py`, and `safe_output.py`;
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
`v2_authority.py` now re-exports the canonical MAIN decision for compatibility.

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

`charge_controller_v2.py`,
`done_storage_restore.py`,
`manual_mode.py`,
`manual_runtime_v2.py`,
`manual_text_v2.py`,
`mix_active_authority.py`,
`mix_current_containment.py`,
`production_controller.py`,
`production_guardrails_v2.py`,
`runtime/charge/profiles/manual.py`,
`runtime/production_runtime.py`,
`runtime/safety/variables.py`,
`runtime_safety.py`,
`runtime_safety_v2.py`,
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
