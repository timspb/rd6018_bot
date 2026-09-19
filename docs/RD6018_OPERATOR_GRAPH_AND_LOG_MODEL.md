# RD6018 Operator Graph / Controls / Log Model

Статус: **OPERATOR_GRAPH_LOG_READY**

Новая presentation-граница:

```text
OperatorStateSnapshot + current canonical events
        ↓
GraphViewModel / ChargeCardViewModel / OperatorLogViewModel
        ↓
OperatorPanelViewModel
        ↓
TelegramOperatorPanelFormatter
```

## Graphs

`GraphViewModel` содержит только текущую session и три series: Voltage,
Current и Battery temperature. Range-фильтры: `30m`, `2h`, `session`.
При новой session старые точки не проходят фильтр; ambiguous/missing/stale
samples дают empty/degraded graph. Температура БП в graph model отсутствует.

## Controls

Presentation state имеет кнопки `30м`, `2ч`, `Сессия`, `Лог` и action labels
`Пауза`, `Стоп`, `Обновить`. Они являются UI-state/presentation-only
contracts. В WS76 нет control handler, V2 owner, lease path или physical call.

## Log

`OperatorLogViewModel` фильтрует canonical events по текущим session/trace и
оставляет только релевантные lifecycle, Delta/Hold, pause/resume, stop/done и
safety events. Ambiguous session явно отображается как `UNKNOWN`; события
старых sessions не смешиваются.

## Panel

Порядок Telegram presentation: graphs → compact charge card → range buttons →
action buttons. Log остаётся отдельным view contract. Diagnostics не входят в
основную карточку.

## Verification

Добавлено 7 focused tests: graph series/range, reset/isolation, controls,
current-session log, ambiguity, panel layout/diagnostics separation и
architecture guard. V2 runtime, V3 domain, safety, execution и deployment не
изменялись.
