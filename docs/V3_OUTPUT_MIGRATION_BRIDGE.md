# V3 Output Intent Factory и V2 Bridge Shadow

## Поток

```text
ChargeIntent
      ↓
SafetyEngine
      ↓
SafetyDecision
      ↓
OutputIntentFactory
      ↓
SafeOutputIntent
      ↓
ShadowOutputBridge
      ↓
V2 command representation
      X
physical execution
```

`OutputIntentFactory` конвертирует только разрешённый `SafetyDecision`,
содержащий исходный domain intent. Отклонённое решение не может попасть в
output layer. Завершённый intent преобразуется в `disable_output`, активный —
в `enable_output` с его targets.

## Bridge

`mapping.py` создаёт только data representation старой actuator-команды.
`ShadowOutputBridge` возвращает `ShadowExecutionRecord` с
`executed=False` и причиной `shadow_only`. Ни один старый actuator, HA API,
RD или ESPHome объект не импортируется и не вызывается.

## Ownership

- ChargeStrategy/ChargeProgram/Recipe владеют только domain decision data.
- SafetyEngine является единственным владельцем допуска.
- OutputIntentFactory переносит разрешённый результат в output contract.
- Shadow bridge только наблюдает и сравнивает mapping.
- Production V2 actuator path остаётся действующим и независимым.

## Migration blockers

Физический bridge нельзя включать до доказательства parity V2 wrappers,
readback, lease, verified-OFF и physical bench tests на целевом RD6018.

## Отклонения от канона стратегии

- Bridge пока не исполняет команды.
- `SafetyDecision` содержит только ссылку на domain intent, но автоматическая
  интеграция с production не сделана.
- Числовые лимиты принадлежат `SafetyLimits`/recipe policy, mapping их не
  задаёт и не изменяет.
