# Communication-Loss Watchdog — 15 Minute Target

Status: **ACCEPTED / IMPLEMENTED IN V2 BRANCH / PHYSICAL DEPLOYMENT VALIDATION PENDING**

The V2 branch now configures the ESPHome edge lease for a 15-minute TTL and the bot-side positive-ACK renewal cadence for 5 minutes. This is a software/configuration change only: the shorter package has not been compiled/flashed and fault-injected on the occupied physical RD6018 bench yet.

## Implemented target

For every controller-managed `Output ON`:

```text
watchdog TTL      = 15 minutes
renewal cadence   = 5 minutes
```

`EdgeSafetyLeaseConfig` now defaults to 900 s / 300 s. `esphome/rd6018_safety_lease.yaml` uses `rd6018_safety_lease_ttl_ms: "900000"`. The existing positive acknowledgement contract remains unchanged: generation must advance, direct RD Modbus must be fresh, boot quarantine/trip must be clear, and the reported remaining lease must be near-full before renewal is accepted.

The 15-minute value is the maximum intended blind-operation interval after the last positively acknowledged controller heartbeat. Mix is the highest-consequence case because it may hold 16.3–16.5 V, but the watchdog remains global for all managed charging rather than creating stage-transition holes.

A missed or invalid renewal while the command path is still available continues to request and verify `Output OFF` immediately. The TTL is the independent backstop when the remote control path is actually unavailable.

## Why 15 / 5

A 5-minute cadence gives three renewal opportunities inside one 15-minute lease. A single transient failure therefore does not immediately interrupt a charge, while the maximum unattended energized interval is materially lower than the historical 30-minute lease.

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

Refreshing a 15-minute edge/native watchdog never resets, reconstructs, extends, or otherwise mutates Mix active-time authority:

```text
watchdog refresh:  00:10 remaining -> 00:15 remaining
Mix active time:   13:40 elapsed   -> 13:40 elapsed
```

The V2 branch now keeps Mix active-time authority in its own durable state and advances it only for Mix intervals that cannot be proved Output OFF.

## Software coverage

Repository tests now lock the 15/5 geometry in both Python and the ESPHome package contract:

- default bot lease TTL = 15 minutes;
- default renewal cadence = 5 minutes;
- a pre-due poll does not renew;
- a due poll requires generation/readback acknowledgement;
- a short remaining lease is rejected;
- the ESPHome package contains the 900000 ms TTL and still retries direct local OFF every 5 s.

## Physical validation still required

Before this branch configuration is deployed to the real controller:

1. compile the exact ESPHome package;
2. flash it only when the current battery experiment is finished and the bench is safe to interrupt;
3. test one missed 5-minute renewal without a false trip;
4. test sustained bot/HA/network loss and prove local OFF no later than 15 minutes after the last accepted heartbeat;
5. test late recovery remains latched and cannot silently resume an old charge;
6. test ESPHome reboot quarantine with the shorter lease;
7. if native RD Timer Off is ever added, first prove its reset/readback semantics on a dummy load and prove the two watchdog layers do not stack into a >15-minute authority window.

Until those physical gates pass, the branch implementation is complete but deployment evidence is not. No native RD timer write has been added.