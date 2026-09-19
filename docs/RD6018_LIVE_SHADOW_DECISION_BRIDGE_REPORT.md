# RD6018 Live V2/V3 Shadow Decision Bridge Report — WORKSTREAM 92

Статус: `LIVE_SHADOW_DECISION_BRIDGE_VALIDATED`

Режим: read-only. V2 оставался production/physical owner; V3 только строил
simulation decision и comparison. START, STOP, PAUSE, writes, lease changes и
ownership transfer не выполнялись.

## 1. Live input

Источник: последний подтверждённый read-only snapshot из HA/RD/ESPHome
observation run, `2026-09-15 11:03:54 UTC`.

| Поле | V2 observation |
|---|---|
| session/profile | Baic72 / Manual |
| lifecycle | ACTIVE |
| phase | MIX |
| measured | 17.10 V / 3.49 A / 59.67 W |
| temperature | 42 °C internal; 37 °C external |
| protection | code 0; OVP/OCP OFF |
| regulation | CC ON; CV OFF |
| lease | armed; TTL 900 s; approx. 777 s remaining |
| Modbus freshness | approx. 0.983 s |

Source health: HA authenticated read-only snapshot, ESPHome state available,
RD readback fresh. No command/service/write call was made.

## 2. V3 shadow decision

```text
program:  manual:Baic72
phase:    MIX
targets:  17.5 V / 3.5 A
safety:   ALLOW (protection clear, lease armed, telemetry fresh)
intent:   simulation-only setpoint tuple; not submitted
```

## 3. Comparison

| Field | V2 actual | V3 shadow | Result |
|---|---|---|---|
| program | Manual Baic72 | manual:Baic72 | MATCH |
| phase | MIX | MIX | MATCH |
| targets | 17.5 V / 3.5 A | 17.5 V / 3.5 A | MATCH |
| safety | clear / armed / fresh | ALLOW | MATCH |
| intent | observed setpoint tuple | simulation intent | MATCH |
| identity | no session/trace in legacy state | no reconstruction | UNKNOWN |

Decision parity: `MATCH` for available decision fields. Overall evidence
confidence is `PARTIAL_LEGACY_IDENTITY_UNKNOWN`, because the persisted V2
session did not expose `session_id` or `trace_id`.

## 4. Fail-closed checks

- Missing telemetry would produce `UNKNOWN` and safety `DENY`.
- Stale state would produce `UNKNOWN` without a handoff.
- Identity mismatch would produce `UNKNOWN`/`DENY`.
- Legacy identity was not fabricated and no fake lifecycle event was emitted.

## 5. Side-effect proof

The bridge performed no HA service call, ESPHome service call, RD command,
Modbus write, lease operation or physical execution. V3 did not influence V2.

## 6. Limitation

This run validates decision parity against the captured live snapshot. It does
not close the legacy identity gap and does not authorize Canary, execution or
ownership transfer.

