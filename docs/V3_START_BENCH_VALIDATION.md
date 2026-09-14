# V3 START bench validation gate

Документ определяет условия перед первым ручным ACTIVE bench execution.
Создание checklist не включает ACTIVE и не меняет production wiring.

## 1. Preconditions

- [ ] Physical bench подготовлен; аккумулятор и нагрузка соответствуют утверждённому сценарию.
- [ ] RD6018, HA/ESP transport и readback доступны.
- [ ] Начальное состояние Output известно и подтверждено.
- [ ] Rollback path протестирован.
- [ ] Verified-OFF path протестирован.
- [ ] Failure containment проверен.
- [ ] `StartActivationPolicy` заполнена только после evidence.
- [ ] `explicit_active_enable=False` по умолчанию подтверждено.
- [ ] `bot.py` не подключает ACTIVE START автоматически.
- [ ] Secrets, node identity и production configuration проверены отдельно.

## 2. SHADOW validation

- [ ] `StartPreflightService` создаёт ожидаемый результат.
- [ ] `ApprovedStartPlan` immutable.
- [ ] Profile и chemistry mapping совпадают с V2.
- [ ] Recipe identity совпадает с ожидаемой V2 recipe.
- [ ] Target voltage/current совпадают с golden trace.
- [ ] Ownership decision зафиксирован.
- [ ] Session decision зафиксирован.
- [ ] Safety decision и deny reasons зафиксированы.
- [ ] `trace_id` создан и коррелируется во всех shadow records.
- [ ] Physical calls отсутствуют.

Evidence:

```text
UserIntent
  -> StartPreflightService
  -> ApprovedStartPlan
  -> RuntimeStartService
  -> StartExecutionTrace
```

## 3. DRY_RUN validation

- [ ] `ProductionStartExecutionPort` выбран явно.
- [ ] DRY_RUN выполняет полный routing через V2 adapter boundary.
- [ ] `StartExecutionRequest` содержит тот же `trace_id`.
- [ ] `V2StartTransactionInput` содержит тот же `trace_id`.
- [ ] Result mapping проверен для success/failure/denied/contained.
- [ ] Rollback mapping проверен для:
  - [ ] `NOT_REQUIRED`;
  - [ ] `OFF_CONFIRMED`;
  - [ ] `OFF_UNCONFIRMED`;
  - [ ] `SESSION_CLEARED`;
  - [ ] `SESSION_CONTAINED`.
- [ ] `controller.start()` не вызывается.
- [ ] FSM/session не изменяются.
- [ ] HA writes отсутствуют.
- [ ] Output/setpoint/physical calls отсутствуют.
- [ ] Production import isolation остаётся PASS.

`ProductionStartRunner` является отдельным gated handoff boundary для будущего
ACTIVE режима. Он принимает только `StartExecutionRequest`, вызывает только
инъецированный V2 transaction owner и нормализует результат с тем же
`trace_id`. Без всех ACTIVE gate flags runner не вызывается.

## 4. ACTIVE bench procedure

ACTIVE разрешается только после ручного одобрения и заполнения всех gates.
Один запуск выполняется отдельно, без scheduler, Telegram automation или
автоматического retry.

### Перед запуском

- [ ] Operator, timestamp, branch и commit записаны.
- [ ] Один `trace_id` назначен всей транзакции.
- [ ] Ownership: `PB_MANAGED`, без `HANDS_OFF`.
- [ ] Нет active session.
- [ ] Fresh telemetry получена.
- [ ] Output OFF подтверждён.
- [ ] Battery/profile/recipe одобрены.
- [ ] Safety preflight PASS.
- [ ] Hardware envelope PASS.
- [ ] Manual bench lease и execution gate PASS.
- [ ] `StartActivationPolicy` имеет все четыре ACTIVE prerequisites.

### Во время запуска

- [ ] Ровно один START command.
- [ ] Transaction trace записан.
- [ ] Controller handoff выполнен единственным owner.
- [ ] Session/FSM transition записан.
- [ ] `SafetySupervisor.preflight()` PASS.
- [ ] `SafeOutputCoordinator` выполняет утверждённый порядок.
- [ ] OVP/OCP/V/I programmed readback PASS.
- [ ] Output enable выполняется только после readback.
- [ ] Final Output/readback state подтверждён.

### После запуска

- [ ] Final V/I/OVP/OCP readback сохранён.
- [ ] Output state сохранён.
- [ ] Controller/FSM state сохранён.
- [ ] Journal/audit содержит полный trace.
- [ ] Никаких вторых START или duplicate callbacks.

## 5. Failure tests

Каждый тест выполняется отдельно и завершается containment/cleanup.

- [ ] Enable command failure.
- [ ] Programmed readback failure.
- [ ] Final Output readback failure.
- [ ] `OFF_CONFIRMED` после failed start.
- [ ] `OFF_UNCONFIRMED` → fail-closed containment.
- [ ] Session cleared только после подтверждённого OFF.
- [ ] Session contained при неподтверждённом OFF.
- [ ] Повторный START запрещён до восстановления ownership/telemetry.
- [ ] Restart не возобновляет незавершённый START автоматически.

## 6. Exit criteria

ACTIVE не считается разрешённым, пока не выполнено всё:

- [ ] Все SHADOW пункты PASS.
- [ ] Все DRY_RUN пункты PASS.
- [ ] Все preconditions PASS.
- [ ] Все failure tests PASS.
- [ ] Bench validation evidence сохранено.
- [ ] Rollback evidence сохранено.
- [ ] Verified-OFF evidence сохранено.
- [ ] `explicit_active_enable=True` установлено только отдельным ручным решением.
- [ ] `bench_validation_passed=True`.
- [ ] `rollback_validation_passed=True`.
- [ ] `physical_gate_passed=True`.
- [ ] ACTIVE включён только для конкретного bench run.
- [ ] После run ACTIVE снова отключён.

## Current status

На момент создания документа:

```text
SHADOW:   implemented/tested
DRY_RUN:  implemented/tested
ACTIVE:   disabled
BENCH:    not authorized by this document
```

Этот checklist сам по себе не является разрешением на физическое включение.
