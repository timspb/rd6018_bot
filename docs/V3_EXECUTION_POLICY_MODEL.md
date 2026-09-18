# V3 execution policy

```text
SafetyDecision -> ExecutionPolicy -> SafeOutputIntent -> future executor
```

`SafetyEngine` решает, допустимо ли состояние/намерение. `ExecutionPolicy`
проверяет prerequisites передачи уже созданного `SafeOutputIntent` будущему
исполнителю. Она не меняет intent, не применяет лимиты и не выполняет команд.

Для `ENABLE_OUTPUT` обязательны fresh telemetry, валидные V/I, protection и
readback. `SET_VOLTAGE` и `SET_CURRENT` требуют соответствующего target и
fresh telemetry. `RESET_PROTECTION` требует reason/source и безопасного state.
`DISABLE_OUTPUT` разрешён даже при safety deny, чтобы не блокировать аварийный
fail-closed путь.

Parity requirements are represented by the test-only
`tests/execution_policy_parity_fixtures.py` helper;
ни V2 actuator, ни RD/HA не вызываются. V1 UI остаётся отдельным потоком.
