# D123 Sprint 43 — retire controller stage-router facade

Status: source-only P4 slice; no production, HA, ESPHome, or physical bench access.

## Change

- Removed `ManagedChargeController._run_stage_scaffold_tick`, the last controller entry point that forwarded automatic stage routing to the application owner.
- Migrated remaining characterization and authority tests to call `application.charge_stage_tick.run_charge_stage_tick` directly; architecture assertions now enforce that the controller has no stage-router method.
- No stage policy, target, ownership, persistence, or actuator behavior changed.

## Verification

- Python 3.12 `compileall`: PASS.
- Focused AutoStrategy and MAIN/MIX/Recovery/Residual migration tests: **33/33 PASS**.
- Full offline unittest discovery: **2,439 tests, 3 skipped, 0 failures**.
- No production service, HA, ESPHome node, or physical equipment was contacted or changed.

## Boundary

P4 remains incomplete: the transitional controller still owns other state, persistence, diagnostics, and compatibility responsibilities. P2 MAIN Guard restore remains fail-closed/deferred; P5 multi-version/release gates and physical acceptance remain open. Only Python 3.12 is available in this local environment; the 3.10/3.11 matrix is not verified.
