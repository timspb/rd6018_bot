# RD6018 V3 Controlled Live Observation — WORKSTREAM 14

## Status

**BLOCKED for full observation completion; LIVE READ-ONLY EVIDENCE COLLECTED.**

The first snapshot was collected through authenticated HA GET requests using
the existing V2 runtime token read from node 101. No write endpoint was called.
Direct ESPHome API observation was not started because the direct API key is not
available in the local checkout or the node-101 `.env`; HA remains the observed
external source for this run.

## Safety boundary

V2 remains the only production, decision, execution and physical owner. No V3
START/STOP, actuator command, lease operation, HA write, ESPHome write or
physical command was performed.

## Observation metadata

- observation source: HA `192.168.1.102:8123`, authenticated GET only;
- V2 owner: production/runtime and physical owner;
- V3 status: observer/analyzer only;
- observation time: `2026-09-15T06:48:48Z`–`2026-09-15T06:48:59Z`;
- direct ESPHome TCP `192.168.1.28:6053`: reachable, API observation not run;
- HA source: available and responding;
- write operations: none.

## Real HA/RD evidence

| Signal | Observed value | Freshness/evidence |
|---|---:|---|
| Output switch | `on` | last update `06:10:38Z` |
| RD output voltage | `17.17 V` | `06:48:55Z` |
| RD output current | `3.49 A` | `06:48:55Z` |
| RD output power | `59.93 W` | `06:47:43Z`, older than the other measurements |
| Battery voltage | `17.16 V` | `06:48:56Z` |
| Internal temperature | `43 °C` | `06:48:58Z` |
| External temperature | `35 °C` | `06:48:55Z` |
| Configured voltage/current | `17.50 V / 3.50 A` | `06:48:55Z` |
| OVP/OCP readback | `17.60 V / 3.60 A` | `06:48:54Z` |
| Protection code | `0` | `06:48:56Z` |
| Regulation mode | `1`; CC sensor `on`, CV sensor `off` | `06:48:56Z` / `06:10:44Z` |
| Output state code | `1` | `06:48:56Z` |

Lease observation from HA:

- armed: `on`;
- tripped: `off`;
- boot quarantine: `off`;
- autonomous mode: `off`;
- generation: `243`;
- TTL: `900 s`;
- remaining: `713.84 s`;
- Modbus age: `3.582 s`;
- last renew button timestamp: `06:45:52Z`.

## Session/state evidence

The read-only copy of `/root/rd6018_bot/manual_session_v2.json` reports:

- state `active`;
- battery `Baic72`;
- stage `mix`;
- configured `17.5 V / 3.5 A`;
- Mix hold `4 h`;
- `started_at = 2026-09-15T06:07:21Z`;
- saved `2026-09-15T06:10:39Z`;
- `stop_reason = manual_main_hold_complete`.

The `stop_reason` is historical metadata, not the current lifecycle state. The
systemd journal on 101 shows `active -> stopped` at `06:10:31Z`, followed by
`stopped -> cooling -> arming` and `arming -> active` at `06:10:39Z`. Therefore
the current live Output ON/CC state is consistent with the later active Mix
session. The remaining issue is that manual evidence is split between journal
and `charging_history.log`.

## Divergences and blockers

- **WARNING:** power sensor timestamp lags the fresh voltage/current samples.
- **MATCH:** persisted Manual session says active/Mix and the journal confirms
  the stop-to-cooling-to-active transition.
- **WARNING:** current manual phase evidence is in systemd journal, not in the
  coarse `charging_history.log` chain.
- **BLOCKER:** direct ESPHome entity/API parity was not observed in this run.
- **BLOCKER:** V3 diagnostics/observer worker was not started; evidence was
  collected by an external read-only probe, so no V3 trace ID is claimed.

No synthetic values were substituted for missing evidence. Full consistency
analysis is documented in `docs/RD6018_LIVE_STATE_CONSISTENCY_REPORT.md`.

## Required next step

Reconcile the persisted Manual/session history against the live HA state, then
run a bounded read-only observation window with direct ESPHome credentials and
V3 trace correlation. Do not start/stop or alter the lease to obtain this
evidence.

## Guardrails

No runtime, ownership, START/ACTIVE, HA, ESPHome, lease or physical state was
changed. `PRODUCTION_READY` is not issued.
