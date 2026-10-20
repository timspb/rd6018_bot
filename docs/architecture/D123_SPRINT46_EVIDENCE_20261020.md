# D123 Sprint 46 — production Cooling tick ownership

Status: source-only P4 slice; no production, HA, ESPHome, or physical bench access.

## Change

- Moved ProductionChargeController's Cooling preflight, pause capture, SAFE_WAIT-specific validation, resume accounting, timer shifting, OFF preservation, persistence, and notification formatting into `application.charge_session_tick`.
- Removed the production controller `tick` override, its argument adapter, and its local fail-closed action builder. `ManagedChargeController.tick` remains the single compatibility handoff to application orchestration.
- Preserved Cooling pause validation before automatic stage execution. Invalid durable pause returns stop/OFF containment without entering the session body.
- Updated the hourly-report isolation test to intercept the application session body rather than bypassing the application entry point.

## Verification

- Python 3.12 `compileall`: PASS.
- Focused Cooling/controller/diagnostic/Mix/ownership set: **45/45 PASS**.
- Full offline unittest discovery: **2,441 tests, 3 skipped, 0 failures**.
- No production service, HA, ESPHome node, or physical equipment was contacted or changed.

## Boundary

The production-class `tick` override is removed, while the base `ManagedChargeController.tick` remains as a compatibility handoff and active callers still reach application orchestration through it. Other transitional state/persistence/diagnostic responsibilities remain. P2 Guard restore admission stays fail-closed/deferred; P5 multi-version/release gates and physical acceptance remain open. Python 3.10/3.11 are unavailable locally.
