# D123 Sprint 49 — retire diagnostic snapshot adapter

Status: source-only P4 slice; no production, HA, ESPHome, or physical bench access.

## Change

- Removed the `ManagedChargeController._bank_fault_risk_snapshot` forwarding method.
- `DiagnosticProductionChargeController` now invokes the canonical `runtime.charge.diagnostics.bank_fault_risk_snapshot` directly, passing itself as the read-only diagnostic context.
- Updated the characterization test and added a static ownership gate preventing the controller facade from returning.
- Updated the controller owner map. Scoring, thresholds, diagnostic context mutation, and all actuator/charge authority are unchanged.

## Verification

- Focused diagnostic/temperature/inventory and ownership tests: **18/18 PASS**.
- Python 3.12 `compileall`: PASS.
- Full offline unittest discovery: **2,443 tests, 3 skipped, 0 failures**.
- `git diff --check`: PASS.
- No production service, HA, ESPHome node, or physical equipment was contacted or changed.

## Boundary

This removes one read-only diagnostic adapter only. Controller lifecycle, persistence, session evidence, and production construction remain. P2 Guard restore admission remains fail-closed/deferred; P5 multi-version/release gates and physical acceptance remain open.
