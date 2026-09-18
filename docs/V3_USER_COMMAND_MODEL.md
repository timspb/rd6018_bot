# V3 user command boundary

```text
Any UI -> UserCommand -> CommandValidator -> DomainIntent -> Runtime/Policy
                                                        -> Safety/Execution
```

Команды `START`, `STOP`, выбора профиля, изменения настроек и подтверждения
безопасности являются data-only объектами. `UserCommandAdapter` превращает их
только в `DomainIntent`; он не создаёт `SafeOutputIntent`, не включает Output и
не вызывает controller/FSM/RD/HA.

`CommandValidator` проверяет профиль, telemetry, активность runtime,
confirmation и diagnostic authority. При `HARD_STOP` команда блокируется.
Test-only `tests/legacy_action_fixtures.py` содержит shadow mapping V1 action names.

Telegram/HA consumers и V1 UI остаются отдельными слоями миграции.
