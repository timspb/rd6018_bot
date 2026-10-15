# MAIN/MIX dynamic hardware containment proposal — 2026-10-15

Status: **domain prototype and design proposal only**. The pure MAIN policy in
`runtime/charge/strategy/main_current_guard.py` has no production caller. No
RD6018, node104, Home Assistant, ESPHome, network, or deployment action was
performed. Passing software tests do not establish physical containment.

## MAIN current ratchet

At the beginning of a MAIN segment, compute:

```text
I0 = min(recipe-authorized initial current, 0.10 * capacity_Ah, 12 A)
Ihardware = I0
```

The 0.1 A RD6018 hardware floor is mandatory. An initial or proposed value
below it is rejected. Accumulate MAIN active time only between observations with explicitly ON
Output, MAIN stage, and fresh current evidence. A stale sample or missing
current breaks continuity; subsequently restored telemetry cannot fill that
unknown interval. Truly unobserved long polling gaps still need a physical
runtime cadence/continuity contract before hardware actuation.
After each 1800 proven-active seconds, with fresh measured current, make at
most one pending proposal:

```text
Inext = min(previous acknowledged hardware limit, measured current + 1.0 A, I0)
```

The proposal does not change authority. Commit the ratchet only after fresh measured-current evidence and independently
confirmed **programmed Iset = proposed limit, OCP = proposed limit + 0.1 A**
readbacks positively acknowledge the
proposed limit inside the execution transaction. Missing, stale, contradictory,
timed-out or ambiguous acknowledgement faults the policy closed. The pure
module never calls an actuator, reads a clock, or writes setpoints.

Output OFF cooling pauses accrued MAIN time and retains the limit. AGM voltage
steps remain in the same segment. Merely visiting another stage or restoring a
stage does not reset the limit. Only an explicitly identified intermediate DESULFATION-to-MAIN transition
**after verified Output OFF and independently fresh restoration of Iset = I0
and OCP = I0 + 0.1 A** starts a new segment. A bare software transition
cannot assert that hardware was reset. This does not touch the independent
session desulfation budget.

Snapshots carry schema, session, battery, segment, current bounds, accrued ON
time and pending transaction. Restore rejects malformed state, wrong session or
battery, impossible bounds, and clock rollback. Persisted data never authorizes
Output ON. Callers must reconcile hardware readbacks after process restart;
unknown outage time must not be guessed as additional MAIN time.

## MIX finish and containment are separate

An accepted Delta starts the existing sticky **2-hour** finish hold. Evidence
remains CV `Imin -> max(0.03 A, 0.3 * Imin)` rise and CC `Vmax -> 0.03 V` drop.
During that hold, natural current rise and voltage sag must remain observable.
Do not change Iset or OCP at the Delta threshold: either can force CC or clip the
trajectory and censor the evidence.

The existing V3 pure MIX candidate has a default 0.4 A and the accepted V2
actuator remains disabled. This proposal does not activate either. OCP alone
does not prove containment: a current ceiling can distort evidence and does not
protect against thermal, voltage-sag, sensor, communication, or actuator faults.

Proposed stage-local thermal trajectory guard inputs are calibrated current
rise `dI/dt`, battery temperature `T`, temperature slope `dT/dt`, and voltage
sag. The guard must preserve current temperature behavior: 35 C warning, 40 C
pause, 45 C critical. No numeric trajectory headroom is proposed here; limits,
filtering, sensor uncertainty, confirmation windows, and response action are
**calibration-gated**. Any configured guard must coexist with the 900 s edge
lease and 60 s HV fast watchdog, keeping the established command path available.
It must not claim that OCP alone contains an abnormal trajectory.

## Exact candidate integration points (not wired)

- `runtime/charge/runtime/main_scaffold.py`: source of MAIN stage and Output
  state context; a future caller may feed immutable evidence to the pure guard.
- `runtime/charge/charge_controller.py`: requested path name is absent on this
  branch. Current charge ownership is modular; locate the live controller only
  as part of a separately authorized production integration.
- `application/execution_port.py`: transaction boundary for applying a typed
  execution intent and checking programmed readbacks. A future integration
  must sequence set-current/OCP under the existing protected OCP ordering and
  commit policy state only after independent fresh readback. No direct source
  writes from this policy are permitted.
- Durable session persistence: add a versioned owner and atomic snapshot/restore
  contract before any production use. Existing session journaling and process
  restart semantics need explicit compatibility review; volatile restoration
  must fail closed and may not resume Output ON.
- Cooling: use positive Output OFF evidence to pause active time, retain the
  segment cap, and require the existing safe resume transaction.
- User voltage limit: the user's **15.5 V ceiling applies to currently authorized physical
  experiments**, not a change to canonical Ca/EFB/AGM automatic MIX recipes
  (16.3-16.5 V). No physical MIX test beyond 15.5 V is authorized. This pure
  prototype grants no voltage authority.

## Open production gates

1. Production wiring requires exact RD6018 current/OCP
   readback behavior characterization at bounded approved voltage/current on the available bench, including
   ordering, transient behavior, delayed/stale reports, rejected writes and
   ambiguous acknowledgement containment.
2. Calibrate and bench-validate current slope, temperature slope, voltage sag,
   sensors, filtering, and intervention timing across supported battery types.
3. Verify the matching ESPHome 900 s lease and 60 s HV watchdog contract on the
   exact node, with an available command path during guard response.
4. Define durable snapshot ownership, crash consistency, recovery policy,
   session/battery identity checks, and journal migration. Reconcile live
   readbacks before any subsequent intent.
5. Add modular production integration only after safety/execution review and
   exact-head tests. This document and the pure policy are not deployed and do
   not imply containment on hardware.
