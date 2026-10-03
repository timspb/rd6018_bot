# V3 Legacy Eradication Ledger

Baseline: `main@6eb6980d1e4a4aeeb804ae25a59af8e292a3d324`.

This ledger is a shrinking debt list. Entries may be removed after migration;
new entries require explicit architecture review.

| ID | Reachable legacy boundary | Current evidence | Replacement target | Removal gate | Status |
|---|---|---|---|---|---|
| L-001 | `bot.py -> runtime.v2_runtime as _legacy -> _legacy_main()` | production composition root aliases historical runtime | modular composition + lifecycle | all runtime owners extracted | OPEN |
| L-002 | module monkey-patch installer stack | many `install_*(_legacy)` mutate one shared module | explicit dependency graph | each installer mapped and replaced | OPEN |
| L-003 | `ChargeControllerV2(ChargeController)` | MAIN, DESULFATION and recovery SAFE_WAIT now use modular decision/runtime owners; historical superclass remains reachable for MIX/final SAFE_WAIT and other non-migrated paths | modular stage engine | migrate MIX/final SAFE_WAIT, then remaining stages until superclass execution is unreachable | IN_PROGRESS |
| L-004 | `_run_legacy_scaffold_tick -> super().tick()` | authoritative MAIN, DESULFATION and recovery SAFE_WAIT bypass historical tick; MIX and final SAFE_WAIT still use the historical scaffold | explicit modular stage runtime services | remove MIX/final SAFE_WAIT historical scaffold calls in ERADICATION-04 | IN_PROGRESS |
| L-007 | `ProductionStartRunner -> V2StartRunnerAdapter -> v2_startup` | new route hands execution to preserved owner | modular start/application/execution service | new START transaction parity | OPEN |
| L-008 | legacy UI read adapter | OperatorSnapshot reads old HMI/runtime globals | canonical read model | migrated screens do not use old app | OPEN |
| L-009 | direct actuator writers outside execution port | runtime/logger/restore/handlers own many setters | single execution service | static inventory reaches zero outside allowed physical implementation | OPEN |
| L-010 | `legacy_recipe_adapter` | preflight/controller/recovery use compatibility naming | modular recipe/config owner | consumers moved and adapter removed | OPEN |
| L-011 | `legacy_safety` | historical FSM uses clamp/timeout; reporting also reads Mix limits | modular safety/strategy variables | values have one canonical owner | OPEN |
| L-012 | `legacy_transition_audit` | controller audits movements produced by legacy fallback | canonical decision journal | no legacy transition source | OPEN |
| L-014 | UI buttons/callbacks scattered across installers/handlers | UI is vulnerable to runtime refactors | modular ScreenSpec/ButtonSpec/action routing | screen-by-screen parity and removal | OPEN |

## Current migration boundary

**ERADICATION-03: MAIN -> DESULFATION -> recovery SAFE_WAIT -> verified MAIN return.**

The functional cutover is implemented in commit
`0f161a85a847d010ea6b7b860c065295145adf7a`.

Canonical owners now are:

- `runtime/charge/strategy/desulfation.py` + `desulfation_variables.py`;
- `runtime/charge/strategy/recovery_safe_wait.py`;
- `runtime/charge/strategy/safe_wait_variables.py`;
- `runtime/charge/runtime/recovery_scaffold.py` for common runtime mechanics.

Authoritative DESULFATION and recovery SAFE_WAIT no longer enter historical
`ChargeController.tick()`. The recovery continuation is session-bound by both
session identity and generation, and persisted state alone cannot authorize
Output ON. SAFE_WAIT -> MAIN remains a two-phase transition: the stage commit
occurs only after the execution layer verifies the physical enable transaction.

Pre-boundary exact-head CI for
`396b364b79816366380ee89d452256d1e0bacf08`, run `#1510`
(`37141127400`), passed on Python 3.10, 3.11 and 3.12.

Local validation for the functional cutover:

- `python -m compileall -q .`: PASS;
- `git diff --check`: PASS;
- full suite: 1793 tests PASS, 2 skipped;
- restart/session-generation/fresh-OFF/failed-enable/no-duplicate-enable/
  historical-tick-unreachable regressions: PASS.

Next boundary after final exact-head CI is ERADICATION-04: MIX -> final
SAFE_WAIT -> verified Storage/DONE.

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
final SAFE_WAIT remain ERADICATION-04 debt.
