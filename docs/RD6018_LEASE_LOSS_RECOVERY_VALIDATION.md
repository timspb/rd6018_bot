# RD6018 Lease Loss and Recovery Behavior Validation

Статус: **LEASE_RECOVERY_VALIDATED**

Дата: 2026-09-16  
Режим: model + controlled in-memory validation. Реальный RD6018 Output, HA/ESPHome
ownership и physical safety не изменялись.

## Validation boundary

Проверялся только managed automation lease boundary:

```text
bot-managed START
    -> ARM
    -> 900s TTL / heartbeat renewal
    -> renewal loss
    -> edge lease expiry / containment state
    -> explicit recovery
```

Физическое истечение lease на production node не моделировалось командой. Controlled
проверка использовала `EdgeSafetyLease` с in-memory HA/readback double и статические
ESPHome contract checks.

## 1. Lease ownership

Результат: **PASS**.

- `runtime_safety_strict.py` требует `controller_active` перед `_arm_edge_lease()`.
- `EdgeSafetyLease.arm()` дополнительно требует свежий direct Modbus evidence,
  отсутствие boot quarantine/trip и положительный generation/readback ACK.
- Поэтому idle, local/manual без bot-managed session и автономный режим не ARM-ят
  managed lease.
- `autonomous_mode` — отдельная explicit edge state; он не выводится из отсутствия
  lease или network loss.

## 2. Controlled ARM and renewal

Результат: **PASS**.

В controlled run подтверждено:

1. начальное состояние: `armed=false`, `tripped=false`, `remaining=0`;
2. `arm()` принят только после положительного edge ACK;
3. generation изменился;
4. remaining lease восстановлен до номинальных 900 секунд;
5. `renew(force=True)` повторно подтвердил lease.

Это только readback/contract exercise; physical Output не включался.

## 3. Lease expiry behavior

Результат: **PASS**.

Controlled expiry state был представлен edge readback как:

- `armed=false`;
- `lease_tripped=true`;
- `remaining=0`.

Проверено:

- managed automation больше не имеет подтверждённого права продолжать управление;
- edge contract предусматривает local containment для managed session;
- lease boundary не создаёт `SessionStopped`, `DONE` или fake lifecycle event;
- lease API не имеет методов lifecycle mutation.

Physical safety остаётся отдельной edge-local authority. Этот тест не выдаёт lease
expiry за доказательство физического Output OFF без отдельного readback.

## 4. Recovery behavior

Результат: **PASS для contract recovery; production physical recovery не выполнялась**.

В controlled model после снятия test trip:

- `disarm()` дождался `armed=false` и `remaining=0`;
- финальный lease state: `armed=false`, `tripped=false`;
- lifecycle STOP/DONE не генерировался;
- новое управление возможно только через новый штатный bot-managed START и новый ARM.

В production recovery должен оставаться explicit: свежий Output/readback, отсутствие
активного trip/quarantine и повторная авторизация. Старый session нельзя silently
resume только на основании lease recovery.

## 5. Audit identity

Lease boundary фиксирует authority/readback identity:

- generation — edge lease renewal identity;
- timestamp/monotonic age — renewal freshness;
- `session_id`, `trace_id`, `decision_id` не создаются lease layer;
- при отсутствии lifecycle identity lease не синтезирует её и не создаёт fake START,
  STOP или DONE.

Следовательно, identity correlation должна приходить от bot-managed orchestration,
а lease только прикрепляется к уже существующей managed operation.

## Scenario result

| Scenario | Result | Evidence |
|---|---|---|
| Lease appears after managed start boundary | PASS | `controller_active` guard + ARM ACK |
| Local/manual mode arms lease | PASS — prohibited | no `controller_active`, ARM blocked |
| Heartbeat renewal | PASS | generation/readback/remaining ACK |
| Lease expiry | PASS | tripped/unarmed/zero remaining model |
| Fake STOP/DONE on expiry | PASS — absent | no lifecycle emitter in lease API/edge contract |
| Recovery | PASS — controlled contract | explicit disarm/readback; no implicit resume |
| Physical safety mutation during validation | PASS — none | in-memory only; no production command |

## Tests

Добавлен focused suite:

`tests/test_workstream108_lease_recovery.py`

Он проверяет ARM, renewal, expiry readback, отсутствие lifecycle mutation, autonomous
separation и edge containment contract. Existing lease and ESPHome contract tests were
used as supporting evidence.

## No changes / no side effects

- V2 runtime не изменялся.
- Lease ownership и physical safety не изменялись.
- Production node и service не перезапускались.
- Реальные START/STOP, setpoint changes и physical commands не выполнялись.
- Synthetic lifecycle events в runtime не создавались.

## Final decision

**LEASE_RECOVERY_VALIDATED** — managed lease loss лишает только managed automation
authority и переводит edge в предусмотренный containment state; lease не создаёт
fake lifecycle events и не выполняет silent session recovery. Recovery требует нового
явного managed authorization path.
