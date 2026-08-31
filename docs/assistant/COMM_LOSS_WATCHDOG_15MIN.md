# Communication-Loss Watchdog — 15 Minute Target

Status: **ACCEPTED DESIGN DECISION / NOT YET IMPLEMENTED**

This note tightens the intended communication-loss safety boundary. The currently implemented ESPHome edge lease remains 30 minutes with a 10-minute bot renewal cadence until code/config/tests are changed and physically validated.

## Accepted target

For every controller-managed `Output ON`:

```text
watchdog TTL      = 15 minutes
renewal cadence   = 5 minutes
```

The 15-minute value is the maximum intended blind-operation interval after the last positively acknowledged controller heartbeat. Mix is the highest-consequence case because it may hold 16.3–16.5 V, but the watchdog remains global for all managed charging rather than creating stage-transition holes.

A missed or invalid renewal while the command path is still available should continue to request and verify `Output OFF` immediately. The TTL is the independent backstop when the remote control path is actually unavailable.

## Why 15 / 5

A 5-minute cadence gives three renewal opportunities inside one 15-minute lease. A single transient failure therefore does not immediately interrupt a charge, while the maximum unattended energized interval is materially lower than the current 30-minute lease.

The target is deliberately not shortened further until real HA/ESPHome/network outage and recovery tests establish normal worst-case latency/jitter. False shutdown is acceptable; silently extending high-voltage authority is not.

## Native RD6018 Timer Off must share the same authority heartbeat

If/when the RD6018 Current Session timer is proven writable and safe on the physical unit, the native timer must not become an independently self-renewing second 15-minute lease.

Otherwise two sequential watchdog windows can stack:

```text
bot heartbeat lost
        ↓
ESPHome edge lease continues for almost 15 min
        ↓
ESPHome stops refreshing RD timer
        ↓
RD timer may still have almost another 15 min
        ↓
worst case approaches 30 min
```

That is not the intended safety bound.

Instead, one positively acknowledged controller renewal should refresh both authorities from the same heartbeat generation:

```text
bot renewal
   ↓
ESPHome validates fresh direct RD Modbus
   ↓
refresh local edge lease to 15 min
   ↓
reset/verify native RD Timer Off to 15 min
   ↓
renewal ACK only after required readback/verification
```

ESPHome must **not** autonomously reset the native RD timer between bot renewals merely because ESPHome itself is alive. After the last accepted bot heartbeat, neither watchdog authority may acquire a later deadline on its own.

Conceptual invariant:

```text
RD_native_deadline <= accepted_control_deadline
edge_deadline      <= accepted_control_deadline
```

where `accepted_control_deadline` is at most 15 minutes after the last successful controller renewal.

If native-timer refresh/readback fails while it is configured as a mandatory backend, the renewal must not be treated as healthy merely because the ESPHome RAM lease refreshed. Safety must either preserve the earlier native deadline or converge to verified `Output OFF`.

## Independence from Mix chemistry time

The communication-loss watchdog is not the Mix 20/24/10-hour chemistry clock.

Refreshing a 15-minute edge/native watchdog must never reset, reconstruct, extend, or otherwise mutate Mix active-time authority:

```text
watchdog refresh:  00:10 remaining -> 00:15 remaining
Mix active time:   13:40 elapsed   -> 13:40 elapsed
```

The accepted Mix timeout policy and future monotonic Mix active-time accounting remain separate safety/strategy layers.

## Physical validation gate

Before changing production from 30/10 to 15/5:

1. change ESPHome lease TTL and bot renewal cadence together;
2. update renewal ACK expectations for a fresh ~15-minute lease;
3. test one missed 5-minute renewal without a false trip;
4. test sustained bot/HA/network loss and prove local OFF no later than 15 minutes after the last accepted heartbeat;
5. test late recovery remains latched and cannot silently resume an old charge;
6. test ESPHome reboot quarantine with the shorter lease;
7. if native RD Timer Off is added, prove its reset/readback semantics on a dummy load and prove the two watchdog layers do not stack into a >15-minute authority window.

Until those gates pass, `docs/RD6018_FAILSAFE.md` describes the **current implemented 30/10 lease**, while this document records the accepted target.