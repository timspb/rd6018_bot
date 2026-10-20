# D123 Sprint 44 — diagnostic refresh application ownership

Status: source-only P4 slice; no production, HA, ESPHome, or physical bench access.

## Change

- Moved the stored-diagnostic refresh pre-step from `DiagnosticProductionChargeController.tick` into `application.charge_session_tick` before stage selection and authority evaluation.
- Removed the Diagnostic controller's `tick` override. Existing diagnostic veto/evidence behavior and refresh ordering are preserved.
- Added tests for awaited refresh and absence of a Diagnostic-specific tick override.

## Verification

- Python 3.12 `compileall`: PASS.
- Focused diagnostic/application/Mix tests: **19/19 PASS**.
- Full offline unittest discovery: **2,441 tests, 3 skipped, 0 failures**.
- No production service, HA, ESPHome node, or physical equipment was contacted or changed.

## Boundary

P4 remains incomplete. Production runtime still dispatches through `charge_controller.tick`, whose Mix active-time and production cooling wrappers carry live lifecycle behavior; their removal requires a coordinated application-owned boundary. P2 Guard restore admission remains fail-closed/deferred. P5 multi-version/release gates and physical acceptance remain open. Python 3.10/3.11 are unavailable in this environment.
