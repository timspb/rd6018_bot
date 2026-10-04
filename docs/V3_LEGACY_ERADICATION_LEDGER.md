# V3 Legacy Eradication Ledger

Baseline: `main@6eb6980d1e4a4aeeb804ae25a59af8e292a3d324`.

This ledger is a shrinking debt list. Entries may be removed after migration;
new entries require explicit architecture review.

| ID | Reachable legacy boundary | Current evidence | Replacement target | Removal gate | Status |
|---|---|---|---|---|---|
| L-001 | `bot.py -> ProductionComposition -> runtime.v2_runtime substrate` | production root is explicit; historical runtime is encapsulated as a compatibility substrate and is no longer the module identity/lifecycle owner | modular composition + lifecycle | remove the production `runtime.v2_runtime` substrate edge in ERADICATION-09 | IN_PROGRESS |
| L-002 | compatibility installer stack inside `ProductionComposition.compose()` | installer order is centralized under one explicit composition owner; no installer call executes independently at module top level | explicit dependency graph | retire remaining compatibility installers with the historical runtime graph | IN_PROGRESS |
| L-003 | `ChargeControllerV2(ChargeController)` | automatic MAIN, DESULFATION, recovery SAFE_WAIT, MIX and final SAFE_WAIT use modular decision/runtime owners; production Custom/Manual no longer enters the historical controller; superclass remains only for residual compatibility stages/helpers | modular stage engine | migrate residual compatibility stages/helpers until superclass execution is unreachable | IN_PROGRESS |
| L-004 | `_run_legacy_scaffold_tick -> super().tick()` | authoritative automatic MAIN, DESULFATION, recovery SAFE_WAIT, MIX/final SAFE_WAIT bypass historical tick; historical Custom is rejected/fail-closed and Manual uses its own runtime owner; `super().tick()` remains only for residual compatibility stages/helpers | explicit modular stage runtime services | remove the remaining historical scaffold reachability during residual convergence | IN_PROGRESS |
| L-007 | `ProductionStartRunner -> V2StartRunnerAdapter -> v2_startup` | new route hands execution to preserved owner | modular start/application/execution service | new START transaction parity | OPEN |
| L-008 | legacy UI read adapter | OperatorSnapshot reads old HMI/runtime globals | canonical read model | migrated screens do not use old app | OPEN |
| L-009 | direct actuator writers outside execution port | live production writers now converge through the application execution port; only approved physical implementation plus quarantined unreachable history contains direct calls | single execution service | static inventory reaches zero outside allowed physical implementation | CLOSED |
| L-010 | `legacy_recipe_adapter` | preflight/controller/recovery use compatibility naming | modular recipe/config owner | consumers moved and adapter removed | OPEN |
| L-011 | `legacy_safety` | compatibility module remains, but live voltage ceilings/MIX windows are derived from modular safety/strategy VariableSpec owners | modular safety/strategy variables | values have one canonical owner | CLOSED |
| L-012 | `legacy_transition_audit` | controller audits movements produced by legacy fallback | canonical decision journal | no legacy transition source | OPEN |
| L-014 | UI buttons/callbacks scattered across installers/handlers | all production Telegram UI routes are owned by canonical `runtime/ui` modules; historical `runtime/v2_runtime.py` declares no UI routes | modular ScreenSpec/ButtonSpec/action routing | screen-by-screen parity and removal | CLOSED |

## Current migration boundary

**ERADICATION-08: runtime/composition cutover - LOCALLY COMPLETE; REMOTE CI PENDING.**

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