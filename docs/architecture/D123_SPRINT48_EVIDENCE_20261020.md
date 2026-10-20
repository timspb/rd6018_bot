# D123 Sprint 48 — retire managed-controller tick facade

Status: source-only P4 composition cut; no production, HA, ESPHome, or physical bench access.

## Change

- Removed `ManagedChargeController.tick`; production already entered the automatic tick through `application.charge_session_tick.run_charge_session_tick` after Sprint 47.
- Moved HANDS_OFF/startup background isolation to a dynamic authority predicate on the application host. The application tick now exits observationally while suspended; no controller tick facade is restored.
- Updated real-controller unit callers to invoke the application API directly. The fake controller in its isolated HANDS_OFF tests intentionally retains a fake `tick` method to characterize its observable behavior.
- Updated D123 AST coverage to assert that the controller no longer defines `tick`.

## Verification

- Python 3.12 `compileall`: PASS after the final isolation adjustment.
- Focused isolation, runtime composition, and trace-context regression: **19/19 PASS**.
- Full offline unittest discovery after the final changes: **2,441 tests, 3 skipped, 0 failures**.
- No production service, HA, ESPHome node, or physical equipment was contacted or changed.

## Boundary

The controller-owned automatic tick facade is retired. P4 cleanup is not complete: other controller state, persistence, and diagnostic responsibilities remain. P2 Guard restore admission remains fail-closed/deferred; P5 multi-version/release gates and physical acceptance remain open. Python 3.10/3.11 are unavailable locally.
