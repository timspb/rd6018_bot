# V3 Phase 8A — SafetyEngine intent boundary

Статус: shadow-only safety decision boundary

Baseline: `bd276787b69b9e5f8ce0d47dd58caee3e47149b3`

## Intent flow

```text
ChargeIntent + Measurements + SafetyContext
                 ↓
            SafetyEngine
                 ↓
            SafetyDecision
                 X
            no Output/RD call
```

`SafetyEngine` проверяет context validity, ownership allowance, optional thermal
limit и configured voltage/current envelope. Он возвращает `accepted`, `reason`
и `limits_applied`; он не изменяет intent, state или measurements.

Safe completed intent без targets допускается как domain terminal result. Active
intent с отсутствующим, отрицательным или превышающим limit target отклоняется.

## Ownership

- ChargeProgram/ChargeEngine формируют только intent.
- SafetyEngine является будущим владельцем safety decision.
- OutputAdapter, HA/RD/ESP, lease, persistence и Telegram не входят в Phase 8A.
- `SafetyDecision` не является разрешением физического вызова: physical adapter
  integration будет отдельным gate.

## Migration blockers

- сопоставить `SafetyLimits` с действующими production safety envelopes;
- доказать parity thermal/readback/lease/ownership semantics;
- определить единый adapter path после safety decision;
- пройти focused/full regression и physical bench gates.

Никакие существующие safety wrappers, lease semantics, AUTONOMOUS/HANDS_OFF,
controller/FSM или production output paths не изменялись.
