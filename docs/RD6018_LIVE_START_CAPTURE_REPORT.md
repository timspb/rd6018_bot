# RD6018 Live Start Capture

Observation: `ws81-20260915T130058Z`

Статус: `LIVE_START_CAPTURE_PARTIAL` — physical transition captured; V2 lifecycle not correlated

## Read-only evidence — delayed sample

| Field | Observation |
|---|---|
| V2 persisted state | `stopped` |
| set voltage readback | `13.0 V` |
| set current readback | `0.4 A` |
| battery voltage | `12.83 V` |
| output voltage | `12.84 V` |
| output current | `0.39 A` |
| output state code | `1` |
| internal temperature | `36.0 °C` |
| service | `active` |
| output state `last_changed` | approximately `2026-09-15T13:08:46.476Z` |

Setpoint readback timestamps were approximately `2026-09-15T13:08:46Z`. The
delayed sample then showed a real HA output-state transition from code `0` to
code `1` and measured output/current `12.84 V / 0.39 A`.

## Lifecycle result

- requested action timestamp: not observable from read-only sources;
- actual output state change: OBSERVED at approximately `13:08:46Z`;
- first active telemetry: OBSERVED at approximately `13:08:46Z`;
- V2 active/session transition: NOT OBSERVED (`manual_session_v2.json` remains `stopped`);
- V3 shadow decision: not generated because no active V2 lifecycle was observed;
- timeline events: no canonical START event captured;
- graph points: physical samples exist, but no session identity permits current-session graph binding;
- audit event: no START audit event captured.

This is a physical read-only observation, not a reconstructed V2 lifecycle.
No synthetic event or synthetic identity was created.
No ownership transfer, V3 execution, deployment change or additional physical
command was performed by this capture.
