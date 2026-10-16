# D079 — live-protection ownership (2026-10-16)

Base: accepted D078 main `17f5881f927ec1ad8f65e1b4beddf713a806b800`.

## Real boundary

- `runtime/safety/engine.py` evaluates the *proposed charge intent*; it does not
  own physical writes.
- `runtime/safety/live_protection.py` now owns the **pure** evaluation of
  already-normalized live OVP/OCP and internal PSU precritical-temperature
  observations. No transport, logger, actuator or session access.
- `runtime/production_runtime.py::data_logger` gathers current observations
  and remains the dispatcher for the **unchanged** journal messages, operator
  notifications and established `_hard_stop_charge()` call order.
- `application/execution_port.py` and the existing composed safe-output path
  retain actuator execution and readback ownership. No second writer is added.
- `runtime/safety/soft_watchdog.py`, managed-runtime containment and the
  independent 900-second ESPHome edge lease remain separate responsibilities.

## Scope and behavior invariants

This extracts a misowned conditional policy from the production composition
without changing thresholds, firmware, data sources, alarm strings, or number
and order of OFF calls. OVP/OCP continue to act only for active charge; internal
PSU precritical applies if Output is ON **or** the charge controller is active.
Missing normalized evidence does not become a confirmed trip. Independent
watchdogs and other policies have not been weakened or unified.

D079 is **software-only**, not live production validation. It neither activates
MAIN Iset/OCP ratcheting nor changes MIX, Delta, AGM, session restore, or
the 900-second edge safety lease.

## Next ownership seams

Normalize telemetry-loss transitions between `soft_watchdog.py`,
`managed_runtime_safety.py` and production restoration **after** a
behavioral inventory. Keep short communication gaps separate from confirmed
electrical faults, prohibit new aggressive writes on stale data, and preserve
independent ESPHome containment. Complete MAIN current-cap lifecycle and
MIX owner-committed current evidence before any activation.
