# RD6018 Manual Mode Decision Migration

Дата: 2026-09-16
Статус: `MANUAL_MODE_DECISION_BOUNDARY_READY`

## Целевая граница

```text
Manual input/state
  -> V3 ManualPhaseLifecycle
  -> ExecutionIntent-equivalent decision
  -> existing V2 guarded physical owner
  -> HassClient/RD
```

`HassClient`, Modbus/HA transport и hardware safety guards не изменялись.

## Что перенесено

`ManualPhaseLifecycle` теперь владеет решением MAIN→MIX:

- CV/voltage/min-current evidence;
- confirmation count и hold duration;
- phase transition reason;
- новые MIX targets;
- deterministic `decision_id` for the transition instance and a typed
  `ExecutionIntent` carrying the approved V/I request.

`manual_mode.py` остаётся источником Manual input/state и больше не вызывает
`set_current()` или `set_voltage()` напрямую.

## Execution bridge

`ManualExecutionBoundary` получает уже сформированное решение и typed
`ExecutionIntent` вместе с identity:

- требует `session_id` и `trace_id`;
- не рассчитывает phase или targets;
- использует существующие guarded V2 setter methods через переданного owner;
- проверяет Output ON, battery voltage и canonical V2 setpoint readback;
- сохраняет decision/intent/session/trace audit record.

При отсутствии identity или readback запись отклоняется; synthetic identity не
создаётся. При неуспешной транзакции существующий Manual owner выполняет свою
обычную verified-OFF failure path.

## Проверки

- MAIN→MIX decision создаётся lifecycle-моделью;
- targets берутся из V3 lifecycle decision;
- `manual_mode.py` не содержит прямых setter-вызовов;
- bridge требует identity и проверяет readback;
- `HassClient` и physical owner не менялись;
- live hardware test не выполнялся до прохождения boundary tests.
