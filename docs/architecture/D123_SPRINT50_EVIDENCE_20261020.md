# D123 Sprint 50 — production host construction cut

Status: source-only P4 composition slice. No production host, HA, ESPHome node,
firmware, service, deployment, GitHub, or physical output was accessed or changed.

## Cut and boundary

`runtime.production_runtime` now imports and constructs exactly one
`ProductionChargeController`. The production loop already routed its automatic
tick through `application.charge_session_tick.run_charge_session_tick`; the
remaining runtime construction had bypassed the existing production session
host and its recipe-aware target bounds, production pause/restore extensions,
and finish/runtime-signal session handling.

A static architecture regression checks the runtime import set and its single
`charge_controller` constructor. The existing runtime type assertion remains as
a behavioral composition check. `ProductionChargeController` still subclasses
`ManagedChargeController` for state, lifecycle, start, and restore behavior.
Removing that inheritance would require a separate session/state/lifecycle
migration and would cross the deferred ordinary-session/MAIN Guard restore
admission boundary. MAIN Guard restore admission remains fail-closed/deferred.

START still configures this same app-owned host before the verified ExecutionPort
transaction. Session persistence still uses the canonical persistence writer and
production session extensions. Restore still uses the existing restore flow and
Guard admission checks. Action batches and verified stage commits still use the
existing application execution owner. No algorithms, recipes, leases, safety,
OVP/OCP, Manual, or physical priorities changed.

## Verification

- Focused production construction, START, session restore, action execution,
  verified transaction, Guard binding, and application tick set: **81 PASS**.
- Full Python 3.12 offline unittest discovery: **2,444 tests, 3 skipped, 0 failures**.
- `python -m compileall -q .`: PASS.
- `git diff --check`: PASS.

## Remaining work

- P4: remove `ProductionChargeController` inheritance/facade by migrating its
  remaining state, session, lifecycle, and restore boundaries to the canonical
  application/session owners; preserve the single FSM and production extensions.
- P2: complete remaining audit/session lifecycle ownership. MAIN Guard restore
  admission remains explicitly deferred and fail-closed.
- P5: Python 3.10/3.11 matrix, exact release SHA and clean-state release gate,
  then separately authorized deployment and supervised physical acceptance.
