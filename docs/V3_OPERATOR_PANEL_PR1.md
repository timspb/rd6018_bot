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

Добавить read-only legacy snapshot provider в composition root и сравнить новый
renderer с V1/V2 panel до переноса любой callback-группы.
