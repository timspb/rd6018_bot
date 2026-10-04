# V3 Legacy Eradication Ledger

Baseline: `main@6eb6980d1e4a4aeeb804ae25a59af8e292a3d324`.

This ledger is a shrinking debt list. Entries may be removed after migration;
new entries require explicit architecture review.

| ID | Reachable legacy boundary | Current evidence | Replacement target | Removal gate | Status |
|---|---|---|---|---|---|
| L-001 | `bot.py -> runtime.v2_runtime as _legacy -> _legacy_main()` | production composition root aliases historical runtime | modular composition + lifecycle | all runtime owners extracted | OPEN |
| L-002 | module monkey-patch installer stack | many `install_*(_legacy)` mutate one shared module | explicit dependency graph | each installer mapped and replaced | OPEN |
| L-003 | `ChargeControllerV2(ChargeController)` | automatic MAIN, DESULFATION, recovery SAFE_WAIT, MIX and final SAFE_WAIT use modular decision/runtime owners; production Custom/Manual no longer enters the historical controller; superclass remains only for residual compatibility stages/helpers | modular stage engine | migrate residual compatibility stages/helpers until superclass execution is unreachable | IN_PROGRESS |
| L-004 | `_run_legacy_scaffold_tick -> super().tick()` | authoritative automatic MAIN, DESULFATION, recovery SAFE_WAIT, MIX/final SAFE_WAIT bypass historical tick; historical Custom is rejected/fail-closed and Manual uses its own runtime owner; `super().tick()` remains only for residual compatibility stages/helpers | explicit modular stage runtime services | remove the remaining historical scaffold reachability during residual convergence | IN_PROGRESS |
| L-007 | `ProductionStartRunner -> V2StartRunnerAdapter -> v2_startup` | new route hands execution to preserved owner | modular start/application/execution service | new START transaction parity | OPEN |
| L-008 | legacy UI read adapter | OperatorSnapshot reads old HMI/runtime globals | canonical read model | migrated screens do not use old app | OPEN |
| L-009 | direct actuator writers outside execution port | runtime/logger/restore/handlers own many setters | single execution service | static inventory reaches zero outside allowed physical implementation | OPEN |
| L-010 | `legacy_recipe_adapter` | preflight/controller/recovery use compatibility naming | modular recipe/config owner | consumers moved and adapter removed | OPEN |
| L-011 | `legacy_safety` | historical FSM uses clamp/timeout; reporting also reads Mix limits | modular safety/strategy variables | values have one canonical owner | OPEN |
| L-012 | `legacy_transition_audit` | controller audits movements produced by legacy fallback | canonical decision journal | no legacy transition source | OPEN |
| L-014 | UI buttons/callbacks scattered across installers/handlers | UI is vulnerable to runtime refactors | modular ScreenSpec/ButtonSpec/action routing | screen-by-screen parity and removal | OPEN |

## Current migration boundary

**ERADICATION-05: Manual/Custom — LOCALLY COMPLETE; EXACT-HEAD CI PENDING.**

Functional code commit:
`c99f1180d7fbe38063c4f453083bd428ce646a62`.

Canonical production ownership for this boundary:

- `manual_mode.py` owns the Manual program/session semantics;
- `ProductionManualSessionManager` in `manual_runtime_v2.py` owns the
  production Manual runtime and authorization lifecycle;
- the preserved five-step Custom dialog is compatibility presentation only and
  routes its request to `ProductionManualSessionManager.start_from_legacy_ui`;
- authoritative `ChargeControllerV2.start(PROFILE_CUSTOM,...)` and
  `start_custom(...)` reject the historical Custom FSM;
- an active historical Custom residue never enters `ChargeController.tick()`;
  it fails closed to Output OFF and clears the stale controller session;
- a persisted historical Custom session is not resumed after restart; Manual
  requires explicit operator reauthorization;
- characterization may instantiate the old Custom controller only with
  `authoritative=False` in tests. That is not a production rollback path.

Accepted five-step Custom UI semantics are preserved when translated to Manual:
voltage, current, Delta, active-time limit and capacity. Existing Manual
restart/re-authorization, cooling, verified-enable, stop and fail-closed
contracts remain owned by the Manual runtime.

Validation on exact code commit
`c99f1180d7fbe38063c4f453083bd428ce646a62`:

- ERADICATION-05 architecture/fail-closed suite: 8/8 PASS;
- start-route isolation: 8/8 PASS;
- recovery trace identity: 3/3 PASS;
- legacy enable inventory: 2/2 PASS;
- Manual runtime: 14/14 PASS;
- Manual mode: 7/7 PASS;
- Manual profile: 5/5 PASS;
- Manual context: 4/4 PASS;
- AUTO/manual-off: 4/4 PASS;
- modular Manual program: 5/5 PASS;
- Manual mode boundary: 3/3 PASS;
- `python -m compileall -q .`: PASS;
- `git diff --check`: PASS;
- full local suite: **1812 tests PASS, 2 skipped**.

ERADICATION-05 is locally complete. Remaining gate:
documentation checkpoint -> push -> exact-head GitHub CI on Python 3.10,
3.11 and 3.12. On PASS, close ERADICATION-05 as remote-verified and begin
ERADICATION-06: safety and execution convergence.

Previous boundary ERADICATION-04 is remote-verified by GitHub Actions run
`#1516` / `37170224025` on Python 3.10, 3.11 and 3.12.

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
