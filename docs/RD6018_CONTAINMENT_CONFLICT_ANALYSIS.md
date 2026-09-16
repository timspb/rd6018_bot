# RD6018 Containment Conflict Analysis

Status: Phase 3.3 read-only analysis. No runtime behavior or ownership is
changed by this document.

## 1. Trigger overlap

| Trigger | Owners | Actions | Verification | Potential conflict |
|---|---|---|---|---|
| HA loss | `data_logger`, soft watchdog, hardware watchdog, HA-loss recovery window | observe degradation; after current timeout policy, hard stop/OFF | HA live/readback, controller/session state | multiple timers can classify the same outage differently; recovery deferral and watchdog policy must not produce contradictory records |
| Telemetry stale | `runtime_safety`, `runtime_safety_v2`, watchdog | fail closed, block writes, possibly ensure OFF | raw live snapshot/freshness checks | one path may be observation-only while another requests OFF; result severity is not currently unified |
| Readback failure | `HassClient`, `runtime_safety`, `SafeOutputCoordinator`, strict safety | abort transaction, force OFF, preserve uncertainty | positive output/readback evidence | repeated OFF requests can overlap; an exception does not prove physical OFF |
| Watchdog timeout | `soft_watchdog_loop`, `watchdog_loop` | `_hard_stop_charge`, controller/session stop, Output OFF | HA live values and controller timestamp | two watchdogs can request the same containment; action and logging ownership are duplicated |
| Lease expiry | `EdgeSafetyLease`, ESPHome dead-man | edge containment/local Output OFF | lease generation/state, edge-local readback | Python may report unknown while ESPHome has already acted; lease failure is not equivalent to confirmed HA Output OFF |
| Manual stop | `ManualSessionManager`, `manual_mode`, `manual_runtime_v2`, UI stop route | stop session and request OFF | session state and output readback | operator stop can race with watchdog/safety stop; session may become stopped before physical result is known |
| Emergency stop | operator emergency route, V2 runtime/safety | hard/managed stop and verified OFF | positive OFF evidence | emergency route and watchdog can both call containment; duplicate notifications and trace-less events are possible |

## 2. Action overlap

### Same trigger, multiple actions

The same trigger can currently produce more than one logical action:

```text
trigger
  -> safety decision
  -> controller/session stop
  -> Output OFF request
  -> lease disarm or lease preservation
  -> notification/logging
```

These are not equivalent actions:

- controller stop changes software ownership/state;
- Output OFF changes physical state;
- lease disarm changes edge watchdog authority;
- lease preservation leaves the edge fail-safe authority armed;
- notification only reports an outcome.

The main conflict risk is treating all of them as one successful “shutdown”.
The `ContainmentResult` contract separates requested action, physical owner and
verification state, but it is not yet connected to runtime.

### Duplicate physical requests

Potential duplicate paths include:

- soft watchdog and hardware watchdog both calling `_hard_stop_charge`;
- safety guard and `SafeOutputCoordinator` both forcing OFF after one failed
  transaction;
- manual stop racing with a watchdog-triggered stop;
- strict safety requesting OFF while the edge lease independently expires;
- recovery/diagnostic paths issuing a second OFF after an uncertain first OFF.

Repeated OFF requests are not automatically unsafe, but they complicate
verification and event correlation. The current system must preserve the most
conservative result when acknowledgements disagree.

## 3. Verification overlap

Current verification evidence comes from different authorities:

| Evidence | Authority | Does it prove physical OFF? |
|---|---|---:|
| Controller/session stopped | V2 controller/session | No |
| HA switch state | HA telemetry | Only if fresh and trusted |
| RD readback | HA/adapter readback | Yes, subject to freshness and source integrity |
| Edge lease disarmed | `EdgeSafetyLease` | Proves lease state, not necessarily every output observation |
| ESPHome dead-man state | ESPHome edge | Strong local containment evidence |
| OFF command accepted | command transport | No; acknowledgement is not physical readback |

Conflicts arise when one layer records “stopped” while another has
`OFF_UNCONFIRMED` or `UNKNOWN`. The result must not be upgraded to
`OFF_CONFIRMED` merely because the controller stopped or a command returned.

## 4. Duplicate ownership classes

### Decision ownership

Several layers can decide that containment is required:

- watchdog;
- runtime safety;
- strict lease safety;
- manual session;
- emergency operator route.

This is acceptable as defense in depth, but there is no single normalized
decision identity yet.

### Physical action ownership

The intended production boundary is the composed V2 safety/output surface.
The edge lease/ESPHome remains an independent final physical safeguard. Legacy
runtime paths still reach the composed surface from multiple callers.

### State ownership

Controller, manual session, safety latch, lease state and persisted state can
transition independently. A session `STOPPED` state therefore cannot be used
as a substitute for a verified physical OFF result.

## 5. Conflict severity

| Risk | Severity | Why |
|---|---|---|
| Duplicate OFF requests | Medium | usually fail-safe, but can obscure the authoritative transaction |
| Controller stopped while OFF unknown | High | software state may imply safety prematurely |
| HA says OFF while edge lease is tripped/unknown | High | telemetry authorities disagree |
| Lease expiry during Python containment | High | two independent physical timelines require correlation |
| Manual stop racing watchdog | Medium | session/result correlation can be lost |
| Multiple timers for HA loss | High | inconsistent timeout interpretation can cause premature or delayed action |
| Missing trace/session correlation | Medium | post-incident reconstruction becomes ambiguous |

## 6. Safe normalization direction

This is a future migration proposal, not an implementation instruction:

1. Every owner keeps its current authority and action.
2. Each owner emits one observation with a common `trace_id`/`session_id`.
3. Decision, physical request, physical verification and lease state remain
   separate fields.
4. A monotonic containment severity rule preserves the most conservative state:
   `OFF_UNCONFIRMED` or `UNKNOWN` must not be downgraded by a later software
   “stopped” event.
5. Only a fresh positive physical/edge observation may produce
   `OFF_CONFIRMED`.
6. Deduplication should affect reporting only until runtime parity is proven;
   it must not suppress an actual safety action.

## Conclusion

The largest current conflict is not that multiple safety owners exist; it is
that their software stop, physical OFF, lease and verification outcomes are
reported as separate events without one normalized correlation envelope.
Phase 3.3 should therefore remain analysis-only. Connecting the observation
contract to writers or deduplicating shutdown calls requires a separate
behavior-reviewed phase with failure and bench evidence.

