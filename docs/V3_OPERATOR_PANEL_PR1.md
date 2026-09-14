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
