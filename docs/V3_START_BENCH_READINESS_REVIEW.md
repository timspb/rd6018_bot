# V3 START Bench Readiness Review

Статус документа: audit only. Документ не включает ACTIVE и не разрешает
физическое выполнение START.

Дата проверки: 2026-09-14

## Итоговый статус

```text
SOFTWARE SHADOW: PASS
DRY_RUN:         PASS
HOST BOOT:       PASS
ACTIVE:          DISABLED
PHYSICAL START:  NOT EXECUTED
BENCH ACTIVE:    NOT READY / NOT AUTHORIZED
```

Причина статуса `NOT READY`: физическая bench-проверка rollback, verified-OFF,
readback и failure containment ещё не подтверждена на конкретном устройстве.
Кроме того, host 101 пока работает на `66b4758`, а последняя repo-правка
валидации START находится в `283c99e` и должна быть отдельно развернута и
проверена в DRY_RUN перед ACTIVE.

## 1. Software readiness

| Boundary | Status | Evidence |
|---|---|---|
| Production Telegram START route | PASS | `ProductionStartRouteAdapter`, единственный V3 route |
| Intent validation | PASS | `StartIntentValidator`, missing fields fail closed |
| Start preflight | PASS | ownership, telemetry, profile, recipe и safety checks |
| ApprovedStartPlan | PASS | immutable plan, без controller/physical объектов |
| Runtime start trace | PASS | trace содержит profile, recipe, target, ownership, session, safety |
| Execution contract | PASS | `StartExecutionRequest` / `StartExecutionPort` |
| Activation gate | PASS | ACTIVE запрещён по умолчанию |
| Physical execution | NOT RUN | намеренно не подключён |

Неполный intent (`intent` или `condition` отсутствует) теперь отклоняется до
recipe selection с причиной `invalid_start_intent`; plan и adapter result при
этом не создаются.

## 2. Runtime readiness

Подтверждено на host 101:

- deployed SHA: `66b4758f025dbefceb90fa2c810b28d8b361478d`;
- Python: `3.11.11`;
- service: `rd6018-bot.service`, `active (running)`;
- restart count после запуска: `0`;
- один polling process;
- Telegram polling достиг `Run polling`;
- V3 import validation: PASS;
- host git status: clean;
- DRY_RUN trace: создан, `controller_handoff=deferred_no_mutation`;
- physical command markers в service journal: отсутствуют.

Ограничение evidence: dashboard и пользовательский Telegram START не являются
bench ACTIVE доказательством. Host-side DRY_RUN был выполнен прямым безопасным
submit boundary, без нажатия START и без физической команды.

## 3. Safety readiness

### Подтверждено программно

- safety preflight является обязательным до ApprovedStartPlan;
- `HANDS_OFF` и active session блокируют запуск;
- ACTIVE mode отклоняется activation policy без всех gate flags;
- denied preflight не создаёт ApprovedStartPlan;
- failed/contained result имеет отдельное V2-to-V3 mapping;
- физический слой не вызывается из DRY_RUN.

### Не подтверждено на bench

- rollback после реального enable failure;
- `OFF_CONFIRMED` на реальном readback;
- `OFF_UNCONFIRMED` containment на реальном RD;
- session cleanup после физического failure;
- OVP/OCP/V/I programmed readback;
- emergency disable и повторная проверка Output OFF.

## 4. Bench prerequisites

Перед первым ACTIVE bench run должны быть отдельно подтверждены:

- конкретный RD6018 и безопасная нагрузка/аккумулятор;
- исходное Output OFF и current `0` через свежий readback;
- исправные HA/ESP transport и capability snapshot;
- согласованный safe bench profile из config;
- оператор и ручное разрешение на один run;
- активный bench lease с ограниченным scope;
- PhysicalExecutionGate `ARMED` только для этого run;
- safety preflight и hardware envelope PASS;
- transaction trace и audit storage доступны;
- rollback procedure и verified-OFF procedure готовы;
- после run ACTIVE снова отключается.

## 5. Explicit blockers before ACTIVE

ACTIVE bench execution запрещён до закрытия всех пунктов:

1. Развернуть `283c99e` на host 101 и повторить host DRY_RUN.
2. Получить software parity evidence для целевого profile/recipe/target.
3. Провести read-only discovery и fresh snapshot непосредственно перед bench.
4. Подтвердить manual lease, ownership и execution gate.
5. Провести отдельный verified-OFF run с положительным readback.
6. Провести rollback test для enable failure.
7. Провести failure test с неподтверждённым OFF и доказать containment.
8. Подтвердить V/I/OVP/OCP ordering и readback на физическом устройстве.
9. Зафиксировать operator approval, trace id, evidence и rollback record.
10. Только после этого вручную заполнить все четыре ACTIVE gate:
    `explicit_active_enable`, `bench_validation_passed`,
    `rollback_validation_passed`, `physical_gate_passed`.

## 6. Prohibited actions in this review

- ACTIVE не включать;
- Telegram START не нажимать;
- `controller.start()` не вызывать;
- FSM/session не изменять;
- HA writes не выполнять;
- set voltage/current/OVP/OCP не выполнять;
- Output не включать;
- production route не переводить в ACTIVE.

## Decision

```text
V3 START bench readiness: NOT READY
ACTIVE authorization: DENIED
Next safe step: deploy 283c99e, repeat DRY_RUN, then close physical
rollback/readback gates on a separately approved bench.
```
