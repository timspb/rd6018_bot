# D123 Sprint 42 — stage authority application ownership

Status: source-only P4 migration slice; no production, HA, ESPHome, or physical bench access.

## Change

- Moved stage admission/dispatch and Diagnostic HV veto coordination out of `ManagedChargeController`, `DiagnosticProductionChargeController`, and `MixActiveAuthority` into `application.charge_stage_tick.apply_charge_stage_authority`.
- Preserved durable Mix elapsed-time projection and terminal `MIX_TIMEOUT` marking at the application boundary. The canonical mix scaffold now reads the strategy limit directly; AUTO display/timer logic also uses the canonical strategy function rather than a controller compatibility accessor.
- Kept stage policy/effects in their existing runtime owners. No actuator API or production behavior was added.
- Updated architecture tests to require the application-owned stage authority path.

## Verification

- Python 3.12 `compileall`: PASS.
- Full offline unittest discovery after stage-authority migration: **2,439 tests, 3 skipped, 0 failures**.
- After removal of the remaining Mix-limit controller accessor: focused authority/AUTO/cooling set **13/13 PASS**; `compileall` and `git diff --check`: PASS.
- No production service, HA, ESPHome node, or physical equipment was contacted or changed.

## Boundary

This is one P4 slice, not P4 completion. `ManagedChargeController` still contains substantial transitional state/persistence/diagnostic responsibilities, and `_run_stage_scaffold_tick` remains a compatibility entry used by legacy characterization tests. P2 Guard restore admission stays fail-closed and deferred pending canonical owner-wide execution plus native pre-ON reconciliation. P5 multi-version/release gates and physical acceptance remain open. The local environment provides Python 3.12 only; Python 3.10/3.11 matrix is not verified here.
