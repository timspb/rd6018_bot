# RD6018 Operator Panel Composition Integrity

Статус: `OPERATOR_PANEL_COMPOSITION_READY`

## Граница сборки

`OperatorStateSnapshot` является единственным входом текущего состояния. Из него
собирается один неизменяемый `OperatorPanelState`, содержащий:

- `ChargeCardViewModel`;
- `GraphViewModel`;
- `OperatorLogViewModel`;
- `ControlsState`;
- ссылку на diagnostics view без включения diagnostics в charge card.

Panel не читает runtime, history, journal, HA, ESPHome или physical adapters.

## Ownership

| Данные | Представление |
|---|---|
| Telemetry | graph и card |
| Phase | card и current-session log |
| Canonical events | log |
| Diagnostics | отдельная reference/view |

Каждый panel строится из одного snapshot; параллельные источники для отдельных
экранов запрещены.

## Session boundary

Graph и log фильтруются по текущему `session_id` и trace. При новой сессии graph
получает новый buffer. При отсутствии identity отображается `UNKNOWN`/
`AMBIGUOUS_SESSION`; старые события не реконструируются и не переносятся.

## UI safety

Range/action controls являются presentation-only. Они меняют только UI state и
не имеют execution callback. Diagnostics не форматируются внутри charge card.

Проверено тестами WS77: composition, session reset, degraded/unknown state,
diagnostics separation и отсутствие runtime/physical dependencies.
