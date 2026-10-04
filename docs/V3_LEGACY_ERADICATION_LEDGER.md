# V3 Legacy Eradication Ledger

Baseline: `main@6eb6980d1e4a4aeeb804ae25a59af8e292a3d324`.

This ledger is a shrinking debt list. Entries may be removed after migration;
new entries require explicit architecture review.

| ID | Reachable legacy boundary | Current evidence | Replacement target | Removal gate | Status |
|---|---|---|---|---|---|
| L-001 | `bot.py -> runtime.v2_runtime as _legacy -> _legacy_main()` | production composition root aliases historical runtime | modular composition + lifecycle | all runtime owners extracted | OPEN |
| L-002 | module monkey-patch installer stack | many `install_*(_legacy)` mutate one shared module | explicit dependency graph | each installer mapped and replaced | OPEN |
| L-003 | `ChargeControllerV2(ChargeController)` | MAIN, DESULFATION, recovery SAFE_WAIT, MIX and final SAFE_WAIT now use modular decision/runtime owners; historical superclass remains reachable only for other non-migrated program families/helpers | modular stage engine | migrate remaining stages until superclass execution is unreachable | IN_PROGRESS |
| L-004 | `_run_legacy_scaffold_tick -> super().tick()` | authoritative automatic MAIN, DESULFATION, recovery SAFE_WAIT, MIX and final SAFE_WAIT bypass historical tick; `super().tick()` remains only for Custom/non-migrated paths | explicit modular stage runtime services | remove the remaining historical scaffold reachability in later program-family boundaries | IN_PROGRESS |
| L-007 | `ProductionStartRunner -> V2StartRunnerAdapter -> v2_startup` | new route hands execution to preserved owner | modular start/application/execution service | new START transaction parity | OPEN |
| L-008 | legacy UI read adapter | OperatorSnapshot reads old HMI/runtime globals | canonical read model | migrated screens do not use old app | OPEN |
| L-009 | direct actuator writers outside execution port | runtime/logger/restore/handlers own many setters | single execution service | static inventory reaches zero outside allowed physical implementation | OPEN |
| L-010 | `legacy_recipe_adapter` | preflight/controller/recovery use compatibility naming | modular recipe/config owner | consumers moved and adapter removed | OPEN |
| L-011 | `legacy_safety` | historical FSM uses clamp/timeout; reporting also reads Mix limits | modular safety/strategy variables | values have one canonical owner | OPEN |
| L-012 | `legacy_transition_audit` | controller audits movements produced by legacy fallback | canonical decision journal | no legacy transition source | OPEN |
| L-014 | UI buttons/callbacks scattered across installers/handlers | UI is vulnerable to runtime refactors | modular ScreenSpec/ButtonSpec/action routing | screen-by-screen parity and removal | OPEN |

## Current migration boundary

**ERADICATION-04: MIX -> final SAFE_WAIT -> verified Storage/DONE — REMOTE-VERIFIED COMPLETE.**

The functional cutover is implemented in commit
`aecde476ccb65ae1aeeb086638d490cd9825992d`.

Canonical owners now are:

- `runtime/charge/strategy/mix.py` for the production MIX stage decision while
  retaining the reusable `MixPolicy` compatibility API;
- `runtime/charge/strategy/mix_variables.py` for MIX V/I targets, profile
  active-time limits and the sticky finish hold;
- `runtime/charge/strategy/final_safe_wait.py` for successful-completion
  continuation validation and relaxation decisions;
- `runtime/charge/strategy/safe_wait_variables.py` for the shared SAFE_WAIT
  relaxation margin/timeout;
- `runtime/charge/strategy/storage.py` for the managed Storage target;
- `runtime/charge/runtime/mix_scaffold.py` for accepted common runtime
  mechanics without historical stage transitions.

Authoritative MIX and final SAFE_WAIT no longer enter historical
`ChargeController.tick()`. Static regressions patch the historical tick to
fail if either path reaches it.

Accepted production semantics are preserved:

- CV MIX uses Imin / Delta-I evidence;
- CC MIX uses Vmax / Delta-V evidence;
- confirmed mode-specific evidence starts the sticky two-hour finish hold;
- active MIX authority remains Ca/Ca 20 h, EFB 24 h, AGM 10 h;
- successful completion enters final SAFE_WAIT with Output OFF;
- persisted final continuation state alone cannot authorize Output ON;
- a fresh physical Output OFF observation is required before Storage enable may
  be requested;
- SAFE_WAIT -> Storage/DONE remains a two-phase transaction and commits only
  after the execution layer verifies programmed OVP/OCP/V/I and physical
  Output ON.

The final continuation persists and validates session identity plus session
generation. Stale generations fail closed. The existing
`V2_MIX_MAX_HOURS` compatibility mapping is derived from the modular
`VariableSpec` owners rather than defining a second production value owner.

Pre-boundary exact-head CI for
`39f8ab2ef143ce1092aab267d511114c58395ff0`, run `#1512`
(`37147682685`), passed on Python 3.10, 3.11 and 3.12.

Local validation for the functional cutover:

- `python -m compileall -q .`: PASS;
- `git diff --check`: PASS;
- focused MIX/final/recovery/Storage/Cooling/compatibility regressions: PASS;
- historical-tick-unreachable, stale-generation, fresh-OFF, pending-enable and
  no-duplicate-enable regressions: PASS;
- full suite on exact code commit
  `aecde476ccb65ae1aeeb086638d490cd9825992d`: **1803 tests PASS, 2 skipped**.

ERADICATION-04 is locally complete. The remaining gate is exact-head GitHub CI
after the documentation checkpoint is pushed. On CI PASS, the next exact
boundary is ERADICATION-05: Manual/Custom.

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
