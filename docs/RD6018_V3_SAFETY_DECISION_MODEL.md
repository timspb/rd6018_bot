# RD6018 V3 Safety Decision Domain

Статус: **SAFETY_DECISION_DOMAIN_READY**

Создан pure safety domain в `application/safety/`.

## Boundary

```text
ChargeDecision
      |
      v
ExecutionIntent + SafetyContext
      |
      v
SafetyPolicy
      |
      v
SafetyDecision
      |
      v
allowed/limited/denied execution boundary
```

`SafetyPolicy` не знает V2, RD, HA, ESPHome, Modbus, lease implementation или physical writers.

## Inputs

`SafetyContext` принимает voltage, current, temperatures, protection codes, telemetry freshness/presence, execution intent, emergency flag и timestamp.

## Decision

`SafetyDecision` возвращает:

- `ALLOW`;
- `LIMIT` (зарезервирован для будущего policy result без выполнения action);
- `DENY`;
- `EMERGENCY`;
- reason, triggered rules, confidence и timestamp.

OVP/OCP/OTP, stale/missing telemetry и emergency conditions проверяются по лимитам, переданным через `SafetyPolicy`. Значения лимитов не зашиты в core.

## Tests

Проверены normal allow, OVP, OCP, OTP, stale/missing telemetry, emergency priority и отсутствие physical/infrastructure calls. ChargeProgram не изменяется safety domain.
