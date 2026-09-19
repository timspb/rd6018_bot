# RD6018 V3 Operator Timeline Canonical Integration

Статус: **OPERATOR_TIMELINE_CANONICAL_READY**

## Canonical source

Operator timeline теперь строится из:

1. `ChargeLifecycleSnapshot` — identity/current phase/current lifecycle state;
2. `CanonicalChargeEvent` — event timeline;
3. `CanonicalTimelineSnapshot` — уже нормализованный session-filtered view.

Journal, legacy history, raw JSON/SQLite и grep по логам не являются UI source. Они могут быть только upstream input для canonical event normalization.

## Dashboard flow

```text
ChargeLifecycleSnapshot + CanonicalChargeEvent[]
                 |
                 v
       CanonicalOperatorTimeline
                 |
                 v
        OperatorDashboardState
```

Каждый dashboard snapshot использует одну текущую session identity и trace identity. Events другой session или другого trace отфильтровываются.

## Display contract

Timeline event содержит:

- timestamp;
- phase;
- reason;
- condition;
- canonical event type;
- trace_id.

Поддерживаются SessionStarted, phase events, DeltaStarted/Completed, HoldStarted/Completed, TerminationDetected и SessionStopped. При отсутствии событий отображается `UNKNOWN`, а не пустая фиктивная строка.

## Graph reset

`graph_session_id` равен текущему `session_id`. Новая или восстановленная сессия получает отдельный graph identity; события старой session не продолжают текущий график.

## Degraded cases

- active session без matching canonical events: `UNKNOWN`;
- restored session: сохраняет исходные `session_id`/`trace_id`;
- ambiguous legacy state: не создаёт fake START и не добавляет события;
- stale telemetry не создаёт timeline transition.

Production runtime, V2, node 101 и physical execution не изменялись.
