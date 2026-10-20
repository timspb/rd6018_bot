# D123 Sprint 47 — production application tick entry

Status: source-only P4 composition cut; no production, HA, ESPHome, or physical bench access.

## Change

- Changed the production data logger to call `application.charge_session_tick.run_charge_session_tick` directly instead of dynamically dispatching through `charge_controller.tick`.
- Kept the call inside the existing runtime execution/guard-owner lock and retained the same telemetry and action arguments.
- Updated AST contracts for MAIN Guard observation, session recovery, and output-action execution to require the direct application call in the same lock scope.
- The base controller `tick` remains only as a compatibility handoff for existing unit/characterization callers; active production runtime no longer depends on it.

## Verification

- Python 3.12 `compileall`: PASS.
- Focused MAIN Guard/order/Manual/Cooling/Mix set: **29/29 PASS**.
- Full offline unittest discovery: **2,441 tests, 3 skipped, 0 failures**.
- No production service, HA, ESPHome node, or physical equipment was contacted or changed.

## Boundary

P4 facade cleanup remains incomplete: the base `ManagedChargeController.tick` compatibility handoff and other controller state/persistence/diagnostic responsibilities remain. P2 Guard restore admission remains fail-closed/deferred; P5 multi-version/release gates and physical acceptance remain open. Python 3.10/3.11 are unavailable locally.
