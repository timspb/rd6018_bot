# V3 Legacy Eradication Ledger

Baseline: `main@6eb6980d1e4a4aeeb804ae25a59af8e292a3d324`.

This ledger is a shrinking debt list. Entries may be removed after migration;
new entries require explicit architecture review.

| ID | Reachable legacy boundary | Current evidence | Replacement target | Removal gate | Status |
|---|---|---|---|---|---|
| L-001 | `bot.py -> runtime.v2_runtime as _legacy -> _legacy_main()` | production composition root aliases historical runtime | modular composition + lifecycle | all runtime owners extracted | OPEN |
| L-002 | module monkey-patch installer stack | many `install_*(_legacy)` mutate one shared module | explicit dependency graph | each installer mapped and replaced | OPEN |
| L-003 | `ChargeControllerV2(ChargeController)` | MAIN decision/config/targets now use modular owners, but historical FSM is still the superclass | modular stage engine | remove historical MAIN scaffold call, then remaining stages | IN_PROGRESS |
| L-004 | `_run_legacy_scaffold_tick -> super().tick()` | MAIN/MIX inputs are masked to suppress legacy transitions | explicit common safety/evidence services | no historical FSM call in AUTO | IN_PROGRESS |
| L-005 | environment `V2_AUTHORITATIVE=0` | can restore legacy decision authority | no production legacy authority switch | env path removed | IMPLEMENTED_PENDING_CI |
| L-006 | direct START fallbacks | `handle_ah_input` and default `v2_bot_ui._start_profile` could mutate RD without the canonical route | production START route | fallbacks removed; missing/injected owner hard-denies | IMPLEMENTED_PENDING_CI |
| L-007 | `ProductionStartRunner -> V2StartRunnerAdapter -> v2_startup` | new route hands execution to preserved owner | modular start/application/execution service | new START transaction parity | OPEN |
| L-008 | legacy UI read adapter | OperatorSnapshot reads old HMI/runtime globals | canonical read model | migrated screens do not use old app | OPEN |
| L-009 | direct actuator writers outside execution port | runtime/logger/restore/handlers own many setters | single execution service | static inventory reaches zero outside allowed physical implementation | OPEN |
| L-010 | `legacy_recipe_adapter` | preflight/controller/recovery use compatibility naming | modular recipe/config owner | consumers moved and adapter removed | OPEN |
| L-011 | `legacy_safety` | historical FSM uses clamp/timeout; reporting also reads Mix limits | modular safety/strategy variables | values have one canonical owner | OPEN |
| L-012 | `legacy_transition_audit` | controller audits movements produced by legacy fallback | canonical decision journal | no legacy transition source | OPEN |
| L-013 | executable `bot_legacy.py` rollback entrypoint | can start preserved runtime directly | archive/test oracle only | direct execution disabled, then file removed | IMPLEMENTED_PENDING_CI |
| L-014 | UI buttons/callbacks scattered across installers/handlers | UI is vulnerable to runtime refactors | modular ScreenSpec/ButtonSpec/action routing | screen-by-screen parity and removal | OPEN |

## Current migration boundary

**ERADICATION-01: prevent legacy from silently becoming authoritative again.**

Scope:

1. remove environment-controlled legacy decision authority;
2. remove direct physical START fallbacks from capacity input and default V2 UI helper;
3. disable direct execution of `bot_legacy.py`;
4. add static regression contracts;
5. establish modular variable and UI contracts.

This boundary deliberately does not change charge chemistry, Delta, recovery,
safety thresholds or deployed VM104 runtime.

Next boundary after PASS: extract authoritative MAIN without
`super().tick()`/time masking.

## ERADICATION-02 progress

The canonical MAIN transition decision, MAIN strategy variables, base MAIN target
selection and the 12 A stage-current ceiling have been moved to modular owners.
`v2_authority.py` now re-exports the canonical MAIN decision for compatibility.

Remaining blocker for ERADICATION-02 PASS: authoritative MAIN still enters the
historical `super().tick()` scaffold with timing/blanking masks. The next change
must extract the common non-transition mechanics needed by MAIN and remove that
historical FSM call without changing accepted safety behavior.
