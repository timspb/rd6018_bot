# D080 — software watchdog policy owner

The software watchdog now has one decision owner and one effect owner:

```text
production_runtime.soft_watchdog_loop
  -> runtime.safety.soft_watchdog (app snapshot + mutable incident + effects)
      -> runtime.safety.watchdog_policy (immutable snapshot/state -> decision)
      -> logger / log_event / _hard_stop_charge
```

`watchdog_policy` is deterministic and has no application, logging, HA,
execution, or actuator dependency. `soft_watchdog` remains the sole production
adapter that inspects app ownership and dispatches the existing effects.
Production composition and the independent 300-second and high-voltage
60-second watchdog authorities are unchanged.

The policy preserves the former heartbeat/clock comparison semantics after
normalizing values: missing heartbeat (`<= 0`) resets, as does a comparison
showing age below timeout or suspended authority. It does not pre-reject
non-finite clock, heartbeat, or timeout values: IEEE comparisons with NaN are
false, so malformed evidence cannot newly suppress an OFF request for managed
authority. Zero and negative timeouts also retain the former aged-heartbeat
behavior. The policy also preserves the 180-second software timeout supplied by the runtime,
60-second bounded retry, passive idle incidents, authority suspension during
HANDS_OFF/edge autonomy/release or unresolved startup, terminal successful
containment, and reset after a fresh or absent/nonpositive heartbeat.

The remaining live restoration seam is in `runtime/production_runtime.py`:
after a communication outage, `data_logger` restores an in-memory active
session or rebuilds an idle session from persisted state and may resume Output
through the existing execution owner. D080 does not change that policy; it
still requires production-level review and offline restoration tests before a
separate ownership extraction.

The ESPHome physical edge lease remains 900 seconds with its existing 300
second renewal cadence and exact node contract. No lease or firmware behavior
was changed. D080 is software-only evidence; the existing exact ESPHome
contract test and target-node BENCH acceptance remain required for edge lease,
ownership, and live-adoption changes. There was no hardware, HA, Telegram,
deployment, or live API activity for D080.
