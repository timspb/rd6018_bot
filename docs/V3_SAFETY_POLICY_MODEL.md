# V3 Safety Policy Domain

Статус: domain-only boundary. Этот слой проверяет `ChargeIntent` и возвращает
решение; он не выполняет физические команды.

## Поток и владение

```text
ValidatedChargeRecipe
          ↓
ChargeStrategy
          ↓
ChargeIntent
          ↓
SafetyEngine
          ↓
SafetyDecision
          ↓
SafeOutputIntent (только контракт)
```

`ChargeStrategy` владеет алгоритмом, `SafetyEngine` — проверкой доменных
ограничений, а будущий `OutputAdapter` будет отдельным владельцем физического
применения. В Phase 8B SafetyEngine не импортирует HA, RD, ESPHome, Telegram,
lease или production controller и не вызывает actuator API.

## Policy data

`SafetyLimits` — конфигурационные данные policy: максимальные напряжение,
ток, температура и допустимый возраст telemetry. Они передаются в engine при
создании и не зашиты в алгоритме проверки.

## Проверки

SafetyEngine отклоняет:

- отсутствующую или недоступную strategy/ownership;
- invalid или stale measurements;
- превышение температурного, общего или chemistry envelope;
- неполный или неположительный active intent;
- запрещённый transition;
- MIX после исчерпания authority или с причиной `MIX_TIMEOUT`;
- BatteryProfile без validated recipe.

Завершённый intent без targets допускается как domain terminal result. В ответе
возвращаются `allowed`, совместимый alias `accepted`, `reason`, полный список
`SafetyViolation` и применённые только для проверки значения limits.

## CUSTOM

`CUSTOM` больше не получает скрытый `CALCIUM` factory default. Для custom DTO
обязателен явный `base_chemistry`, после чего разрешённые overrides проходят
обычный validator. Это не меняет существующий production mapping: новый слой
не подключён к production.

## Запрещённые пути

Safety domain не должен:

- включать или выключать Output;
- менять V/I/OVP/OCP;
- писать в HA или RD;
- менять lease, persistence или ownership state;
- вызывать Telegram handlers.

## Отклонения от канона стратегии

- Safety policy пока проверяет domain envelope, но не заменяет production
  readback/lease/thermal wrappers и не подключена к железу.
- `SafeOutputIntent` создан как контракт, физический OutputAdapter отсутствует.
- Storage/SafeWait остаются post-charge boundary.
