# Communication-Loss Watchdog — 15 Minute Target

Status: **ACCEPTED / IMPLEMENTED / PHYSICAL EDGE WATCHDOG PASS**

The V2 branch configures the ESPHome edge lease for a 15-minute TTL and the bot-side positive-ACK renewal cadence for 5 minutes. The exact 900 s local edge contract is now physically flashed and bench-tested on the real ESP8266/RD6018 node.

## Implemented target

For every controller-managed `Output ON`:

```text
watchdog TTL      = 15 minutes
renewal cadence   = 5 minutes
```

`EdgeSafetyLeaseConfig` defaults to 900 s / 300 s. `esphome/packages/rd6018_safety_lease.yaml` uses `rd6018_safety_lease_ttl_ms: "900000"`. The positive acknowledgement contract remains unchanged: generation must advance, direct RD Modbus must be fresh, boot quarantine/trip must be clear, and the reported remaining lease must be near-full before renewal is accepted.

The 15-minute value is the maximum intended blind-operation interval after the last positively acknowledged controller heartbeat. Mix is the highest-consequence case because it may hold 16.3–16.5 V, but the watchdog remains global for all managed charging rather than creating stage-transition holes.

A missed or invalid renewal while the command path is still available continues to request and verify `Output OFF` immediately. The TTL is the independent backstop when the remote control path is actually unavailable.

## Why 15 / 5

A 5-minute cadence gives three renewal opportunities inside one 15-minute lease. A single transient failure therefore does not immediately interrupt a charge, while the maximum unattended energized interval is materially lower than the historical 30-minute lease.

False shutdown is acceptable; silently extending high-voltage authority is not.

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

No native RD timer write has been added at this stage.

## Independence from Mix chemistry time

The communication-loss watchdog is not the Mix 20/24/10-hour chemistry clock.

Refreshing a 15-minute edge/native watchdog never resets, reconstructs, extends, or otherwise mutates Mix active-time authority:

```text
watchdog refresh:  00:10 remaining -> 00:15 remaining
Mix active time:   13:40 elapsed   -> 13:40 elapsed
```

The V2 branch keeps Mix active-time authority in its own durable state and advances it only for Mix intervals that cannot be proved Output OFF.

## Software coverage

Repository tests lock the 15/5 geometry in both Python and the ESPHome package contract:

- default bot lease TTL = 15 minutes;
- default renewal cadence = 5 minutes;
- a pre-due poll does not renew;
- a due poll requires generation/readback acknowledgement;
- a short remaining lease is rejected;
- the ESPHome package contains the 900000 ms TTL and retries direct local OFF every 5 s.

## Physical validation completed 2026-09-02

The canonical V2 firmware was built/flashed with ESPHome 2026.8.2 and the following were physically observed on the real edge:

1. `Safety Lease TTL = 900 s` on the deployed node.
2. Direct Modbus remained fresh at normal few-second age.
3. Boot quarantine cleared only after fresh direct Output-OFF proof.
4. Verified-OFF arm started a live countdown near 900 s and advanced Generation.
5. A lease allowed to expire with Output already OFF latched `Safety Lease Tripped` and could not be silently revived by a late Renew.
6. Verified-OFF Disarm cleared the trip latch only after Output OFF was directly observable.
7. A second run used a physically energized RD6018 output on a safe battery-disconnected bench. With no further renewals, the 900 s expiry autonomously drove Output OFF and output voltage/current to zero.
8. The trip remained latched after that physical shutdown until verified-OFF Disarm.
9. The same watchdog behavior was later observed after `Safety Lease Adopt Live Output`: adopted Output ON, no renew, 900 s expiry, autonomous local Output OFF, trip latch.

Result:

```text
last accepted managed heartbeat
        ↓
no renew for 900 s
        ↓
edge trip latch
        ↓
local Modbus Output OFF
        ↓
physical RD6018 output de-energized
```

This closes the core **local edge D056 watchdog** gate.

Detailed bench record:

`docs/assistant/PHYSICAL_EDGE_VALIDATION_2026-09-02.md`

## Still pending

The watchdog itself is physically proven, but these broader items remain separate open work:

- full bot/HA/network outage injection across every recovery path;
- ambiguous command/ACK fault injection;
- process-restart containment for the complete D061/D062 runtime;
- any future native RD Timer Off integration and proof that it cannot stack authority beyond 15 minutes.

Those open items do not invalidate the physical 900 s local edge shutdown result; they are wider system-integration gates.
