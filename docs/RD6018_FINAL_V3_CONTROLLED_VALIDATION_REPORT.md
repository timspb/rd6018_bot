# RD6018 Final V3 Controlled Validation Report

Статус: **BLOCKED_WITH_REASONS**

Режим: controlled canary preview evidence review.  
Physical ownership: V2.  
V3: decision/shadow plane.  
Новый physical run в рамках этого отчёта не запускался; использованы ранее
зафиксированные controlled evidence и focused contract tests. Это исключает
повторное включение RD6018 только ради формального отчёта.

## Global safety limits

Проверяемые evidence соблюдают:

- current `<= 0.9 A`;
- voltage target не ниже свежего battery voltage;
- после каждого подтверждённого `OFF -> ON` выдержано `>= 10 s`;
- protection/readback/telemetry проверялись до и после операций;
- физический fault намеренно не создавался.

## Summary matrix

| Test | Scope | Status | Evidence |
|---|---|---|---|
| A — full control path | V3 intent -> identity bridge -> V2 owner -> RD | **PASS** | WS106 bridged cycle |
| B — parameter control | voltage/current changes under limits | **PASS** | WS104 controlled suite |
| C — safety matrix | fresh/stale/invalid/protection/missing | **PASS** | WS102/104/55 tests |
| D — lease matrix | local/managed/renew/expiry/recovery | **PASS** | WS108 validation |
| E — full lifecycle observation | START -> PREP -> MAIN -> MIX -> HOLD -> DONE | **PARTIAL** | full natural chain not evidenced |
| F — operator UI acceptance | card/graph/log/diagnostics | **PASS** | WS75/77/78 contracts |
| G — recovery | restart/stale/ambiguous/audit continuity | **PASS** | WS65 recovery tests |

## A — Full control path

Статус: **PASS** по controlled evidence.

WS106 подтвердил путь через существующего V2 physical owner:

```text
V3 ExecutionIntent
  -> StartOrchestration
  -> ExecutionIdentityEnvelope
  -> V2 bridge
  -> existing V2 physical owner
```

Зафиксированы `intent_id`, `decision_id`, `session_id`, `trace_id`, START/STOP
timestamps, Output OFF/ON verification. 13.0 V / 0.4 A, максимум 0.39 A,
ON hold 10.157 s, итоговый Output OFF и current 0.0 A.

Ограничение: V2 не экспортирует отдельный canonical `SessionStopped` audit event;
STOP evidence остаётся boundary correlation + physical verification, не synthetic
V2 lifecycle event.

## B — Parameter control

Статус: **PASS** по WS104 evidence.

Подтверждены:

- current 0.4 -> 0.8 A, максимум 0.79 A;
- voltage 13.0 -> 13.5 V;
- отдельный профиль 13.8 V / 0.5 A;
- после каждого теста readback, current, protection и verified OFF;
- ранний STOP не выполнялся.

Все операции выполнялись существующим V2/HA boundary; V3 не имел direct hardware
path.

## C — Safety matrix

Статус: **PASS**.

Подтверждено без создания опасного physical fault:

- fresh telemetry/readback -> `ALLOW`;
- stale Modbus -> `DENY`;
- invalid readback -> `DENY`;
- protection fault simulation -> `DENY`;
- missing evidence -> `DENY`.

Safety layer не получает chemistry authority и не вмешивается в local/manual mode;
его scope ограничен limits, protection, telemetry integrity и emergency evidence.

## D — Lease matrix

Статус: **PASS** по WS108 controlled in-memory validation и edge contract.

- local/autonomous mode не ARM-ит managed lease;
- managed START требует `controller_active`, затем ARM;
- heartbeat renewal подтверждается generation/readback;
- expiry лишает managed automation authority;
- fake STOP и fake DONE не создаются;
- recovery требует нового явного authorization path;
- physical safety остаётся отдельной edge-local authority.

## E — Full lifecycle observation

Статус: **PARTIAL**.

Не доказана одна свежая непрерывная естественная цепочка:

```text
START -> PREP -> MAIN -> MIX -> HOLD -> DONE/STOP
```

Нельзя закрыть этот gap выводом `DONE` из Output OFF или реконструкцией истории.
Дополнительный blocker: существующий V2 physical path не экспортирует полный
canonical identity/audit для всех lifecycle events (`session_id`, `trace_id`,
`decision_id`, independent SessionStopped).

## Live observation addendum — 2026-09-15

Read-only evidence после запуска Manual path подтвердило фактический переход
MAIN -> MIX:

- MAIN был запущен с legacy runtime profile `14.1 V / 5.0 A`;
- ток MAIN снизился до `1.63 A`, после чего runtime выполнил
  `active -> stopped`, reason=`manual_main_hold_complete`;
- затем последовали `stopped -> cooling -> arming -> active`;
- физический Output был повторно включён для MIX;
- MIX продолжил наблюдаться при `15.52 V`, ток около `1.75 A`.

Это доказывает переход MAIN -> MIX, но одновременно фиксирует дефект
семантики persistence: `stop_reason=manual_main_hold_complete` остаётся в
активной MIX-сессии и выглядит как окончательное завершение. Это не должно
считаться `SessionStopped` или `DONE`.

Дополнительные findings:

- на live node применился legacy profile, а не запрошенный ограниченный
  `0.9 A` profile;
- последняя наблюдаемая current была выше лимита controlled suite `0.9 A`;
- V2 physical path не экспортирует независимые `session_id`, `trace_id` и
  `decision_id` для полного control/audit chain;
- MAIN -> MIX в текущем V2 реализован через физический OFF и повторный ON;
  необходимость этого как физического требования не доказана.

Обновлённый итог: A/B/C/D/F/G остаются PASS по имеющимся evidence и тестам;
E остаётся PARTIAL, а live profile/identity/persistence findings удерживают
финальный статус `BLOCKED_WITH_REASONS`.

## F — Operator UI acceptance

Статус: **PASS** на synthetic/read-only scenario contracts.

Проверено:

- Battery name / phase / AUTO-MANUAL / CC-CV;
- voltage, current, Ah, elapsed;
- MIX min/max и Hold timer;
- MAIN target/condition;
- graph voltage/current/power/temperature;
- session isolation и graph reset;
- UNKNOWN для missing/stale/legacy identity;
- diagnostics отдельно от charge card;
- presentation controls не вызывают execution.

Не показываются RD6018, служебные коды и внутренние decision fields.

## G — Recovery

Статус: **PASS** на model/contract validation.

Проверено:

- active state recovery;
- HOLD с stale telemetry без resume execution;
- denied/expired approval;
- ambiguous legacy snapshot без fake START;
- audit cursor continuity без duplicate events.

## Blockers

### B1 — Full natural lifecycle evidence отсутствует

Серьёзность: **BLOCKER для полного CANARY REVIEW**.  
Требуется: read-only capture одной естественной сессии от START до фактического
DONE/STOP с реальными event timestamps и source correlation. Нельзя синтезировать
или выводить события из output state.

### B2 — Legacy V2 identity/audit gap

Серьёзность: **BLOCKER для полного parity claim**.  
Требуется: экспорт identity из V2 boundary для фактических lifecycle events либо
явно ограниченный canary scope, запрещающий legacy sessions без identity.

### B3 — Live V2/V3 parity remains UNKNOWN where identity is absent

Серьёзность: **BLOCKER для утверждения full parity**, не для observe-only UI.  
Требуется свежий shadow snapshot с `session_id`/`trace_id`; при их отсутствии
результат должен оставаться `UNKNOWN_LEGACY_NO_IDENTITY`.

## No changes / side effects

- ownership не менялся;
- V2 physical architecture не менялась;
- V3 direct execution не подключался;
- HA/ESPHome/Modbus paths не обходились;
- новые physical commands в рамках WS109-112 не выполнялись;
- fake identity/events не создавались.

## Final decision

**BLOCKED_WITH_REASONS** — control, safety, lease, UI и recovery boundaries
подтверждены, но full canary review нельзя объявить готовым до получения полной
естественной lifecycle evidence chain и закрытия/явного ограничения legacy identity
gap.
