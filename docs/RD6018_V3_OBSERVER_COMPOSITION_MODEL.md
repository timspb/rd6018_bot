# RD6018 V3 Observer Composition — WORKSTREAM 35

## Status

`V3_OBSERVER_COMPOSITION_READY`.

`V3ObserverComposition` is the single read-only composition root:

`Evidence sources → Telemetry → ActiveSessionParity → Explanation → Dashboard → Telegram formatter`.

It accepts reader callables only and does not accept actuator clients,
handlers, lease writers or physical adapters. Startup/shutdown are idempotent;
reader failures are recorded as degraded sources and produce `UNKNOWN` values.

One `OperatorDashboardState` is passed to the formatter, so Telegram does not
read HA, ESPHome, history or runtime independently.
