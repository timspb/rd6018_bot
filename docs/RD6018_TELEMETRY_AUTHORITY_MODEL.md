# RD6018 telemetry authority — Phase 8.4

## Boundary

`HATelemetryAdapter` and `ESPDirectTelemetryAdapter` are read-only adapters.
They normalize injected source reports into the transport-neutral
`TelemetrySnapshot` contract. They do not construct clients or write to a
source.

`TelemetrySnapshot` contains voltage, current, derived power, temperature,
output state, source timestamp, receive timestamp, age/freshness, source and
confidence.

## Arbitration

```text
ESP Direct fresh
        |
        v
HA fresh
        |
        v
last known (stale, confidence 0.25)
        |
        v
unknown (confidence 0.0)
```

Freshness is evaluated against the adapter's `max_age_s`. Stale source reports
are retained as evidence but never outrank a fresh source. `TelemetryArbitrator`
does not call safety, charge, containment, lease or actuator logic.

## Forbidden behavior

Telemetry adapters do not expose or call:

- output commands or setpoint writes;
- HA writes or ESP writes;
- safety decisions;
- charge decisions;
- physical execution.

The `TelemetryProvider` protocol declares only `read()`. Any control contract
is deliberately outside this boundary.

## Rollout boundary

This phase adds application contracts and injected-reader adapters only. No HA
or ESP client is connected, and production START, ACTIVE, Telegram, safety or
physical runtime is unchanged.
