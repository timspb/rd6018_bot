# RD6018 Idle-Armed Lifecycle Observation

Статус: **ARMED_WAITING**

## Arm check

Read-only observer check выполнен `2026-09-15T12:07:37Z` —
`2026-09-15T12:07:41Z` UTC.

- source: HA 102 state API;
- samples: 5, примерно 1 s interval;
- output: `ON` во всех samples;
- lease armed: `ON` во всех samples;
- timestamps: valid source/capture timestamps;
- writes: none.

V2 не перешёл в `active → idle`, поэтому условие ожидания нового START не
наступило. Текущая активность не была объявлена новым lifecycle.

## Waiting state

Observer armed for the following real sequence only:

```text
V2 active → idle
       ↓
V2 idle → START
       ↓
capture identity, program, phase, telemetry, safety and V2/V3 parity
       ↓
stop after DONE / STOP / natural termination
```

До реального START не создаются `session_id`, `trace_id`, START, phase,
Delta/Hold или termination events. Никакие события не реконструируются.

## Capture contract after START

Каждый snapshot должен сохранить timestamp, source, V2 state, program, phase,
telemetry V/I/P/temperature/CC-CV, protection, lease observation,
session/trace identity и parity classification:

`MATCH | EXPECTED_DIFFERENCE | DIVERGENCE | UNKNOWN`.

Сбор завершается только на реально наблюдённом `DONE`, `STOP` или natural
termination. Если окно закончится раньше, результат остаётся `PARTIAL`.

## Safety boundary

Не выполнялись START/STOP, изменение уставок, lease operations, ownership
transfer, deployment, HA/ESPHome writes, RD commands или physical commands.

## Next state

Статус остаётся `ARMED_WAITING`: нужен естественный переход V2 в idle и затем
реальный START. До этого `FULL_LIFECYCLE_CAPTURED` не утверждается.
