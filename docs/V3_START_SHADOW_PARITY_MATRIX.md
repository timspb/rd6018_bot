# V3 START shadow parity matrix

## Scope

Матрица сравнивает зафиксированные ожидания V2 START с read-only цепочкой:

```text
StartPreflightService
        |
        v
ApprovedStartPlan
        |
        v
RuntimeStartService
        |
        v
StartExecutionTrace
```

`start_profile_transactional()` в тестах матрицы не вызывается: его реальное
выполнение мутирует controller/session и до отдельного execution gate запрещено.
Golden traces представляют значения, которые должны быть эквивалентны V2
контракту.

## Success cases

Проверены профили:

- AGM → `agm:normal`;
- EFB → `efb:normal`;
- Ca/Ca → `ca_ca:normal`;
- Custom → `custom:normal`.

Сравниваются profile, chemistry, recipe, target V/I, ownership, session,
safety и итоговый allowed.

## Deny cases

Проверены:

- HANDS_OFF;
- active session;
- stale telemetry;
- invalid profile;
- unsafe voltage;
- unsafe temperature;
- Output already enabled.

Для каждого проверяется deny reason из golden matrix.

## Current result

Golden success vectors MATCH. Deny vectors подтверждают fail-closed поведение.
Матрица не доказывает физическое выполнение и не заменяет V2/V3 bench parity.

## Remaining blockers

Перед execution adapter остаются:

1. подтвердить golden values на реальных V2 capture traces;
2. определить единый execution owner для controller/session handoff;
3. сохранить transactional failure/off confirmation semantics V2;
4. пройти отдельный dry-run и physical bench gate;
5. только после этого подключать START execution.

