# V3 Operator Panel — PR1

## Scope

Добавлены application-facing operator contracts, read-only snapshot mapping,
framework-free declarative panel renderer и injected Telegram transport adapter.
Charge strategy, FSM, safety, connectors, physical execution и существующие
V1/V2 callbacks не изменяются.

## Ownership

```text
Telegram adapter -> OperatorInterface -> OperatorSnapshot -> renderer
                                  \
                                   -> operator intent boundary
```

Presentation получает только данные. HA, RD, controller и physical objects в
ViewModel и renderer не передаются.

## Panel policy

`PanelStore` хранит один authoritative `PanelHandle` на chat. При refresh панель
редактируется через существующий message id. Новое сообщение создаётся только
при отсутствии handle или необходимости смены типа сообщения. Старый
`TerminalPanelManager` и V1 UI остаются production-compatible.

## State layouts

`IDLE`, `CHARGING` и `FAULT` имеют декларативные строки и action matrix.
Generic power toggle не создаётся. Safety и freshness телеметрии могут только
сократить набор действий.

## Next step

Read-only `OperatorSnapshotProvider` теперь адаптирует live state, HMI state,
diagnostics и journal в V3 snapshot. `compare_hmi_to_snapshot()` фиксирует
расхождения без изменения runtime. Следующий шаг — подключить provider в
composition root и сравнить новый renderer с V1/V2 panel до переноса любой
callback-группы.

Provider подключён в `bot.py` как read-only `operator_interface`. Основной
dashboard refresh и graph dashboard получают состояние через
`get_operator_snapshot()`; callbacks и их execution path не изменены.

Details boundary также закрыт: `operator_details`, `operator_service_details` и
`operator_more` используют `get_operator_details()`, `get_service_details()` и
`get_operator_snapshot()`. Их renderer получает только DTO/snapshot. Legacy
execution callbacks и ownership-conflict guard остаются отдельными переходными
read/runtime связями до следующей миграции.

## Capability boundary

`OperatorSnapshotProvider.get_operator_actions()` формирует read-only
`OperatorActionsView`. В нём находятся только логические возможности оператора:
START/STOP/PAUSE/RESUME, выбор профиля, журнал, график, диагностика и
специальные ownership-действия. Callback IDs и Telegram handlers остаются в
presentation adapter и не входят в application contract.

Основной dashboard получает `OperatorSnapshot` и `OperatorActionsView` через
`OperatorInterface`; `build_operator_keyboard(..., actions=...)` только
рендерит этот capability matrix. Старый двухаргументный builder сохранён как
совместимый fallback для ещё не мигрированных внутренних вызовов и не изменяет
execution callbacks.

Оставшиеся переходные UI/runtime связи:

- fallback `build_operator_keyboard(app, state)` и `_build_dashboard_keyboard`
  для legacy ownership/recovery paths;
- `_ownership_conflict()` в `operator_dashboard.py`, который только отображает
  конфликт владельцев;
- graph range/presentation helpers, читающие параметры графика;
- execution callbacks (`v2_bot_ui`, `v2_mix_mode`, `bot_legacy`, managed stop и
  pause handlers). Они намеренно не затронуты этим PR.

## UserIntent routing

`IntentDispatcher` является единой application-точкой для read-only действий:
`SHOW_LOG`, `SHOW_GRAPH`, `SHOW_DIAGNOSTICS` и `REFRESH_PANEL`. Он не вызывает
controller, SafetyEngine, HA или physical layer. Для ещё не подключённого
legacy route возвращается явный результат `routed_to_preserved_callback`, после
чего существующий callback продолжает прежнюю presentation-логику.

`START_CHARGE`, `STOP_CHARGE`, `PAUSE`, `RESUME` и изменение профиля пока
отклоняются как `execution_intent_not_migrated`; их callbacks и семантика
остаются прежними. Исключение — `STOP_CHARGE`: его `StopCommandHandler`
маршрутизирует intent в существующий `operator_managed_stop` callback, но не
вызывает stop transaction сам. Token binding, confirmation, ownership check и
verified Output OFF полностью остаются в managed-stop runtime.
