# RD6018 V2 Setter Boundary Audit

Дата: 2026-09-16  
Режим: read-only code audit; live hardware не запускался.

## Итог

**CONTAMINATED — boundary violation найдена выше setter-а.**

Сам `HassClient.set_voltage()` / `set_current()` является транспортным setter-ом,
но текущий MAIN→MIX caller принимает lifecycle/phase решение в V2 Manual path и
пишет уставки напрямую в `app.hass`. Поэтому путь пока не соответствует канону
`V3 decision → ExecutionIntent → safety → V2 execution owner`.

## 1. Кто принимает решение MAIN→MIX

Фактический путь:

```text
manual_mode.ManualSessionManager.observe_once()
  → _main_tail_reason()
  → _advance_profile_to_mix()
```

`_main_tail_reason()` в `manual_mode.py:508-548` проверяет CV, минимальный ток,
подтверждения и hold timer, после чего возвращает `manual_main_to_mix`. Это
решение принадлежит V2 legacy/manual runtime, а не V3 phase/lifecycle engine.

**Результат: FAIL.**

## 2. Кто формирует targets

`_advance_profile_to_mix()` читает `self.request.profile.mix` и формирует новый
`ManualChargeRequest` с `stage="mix"` (`manual_mode.py:550-575`). Следовательно,
новые voltage/current targets выбираются V2 Manual profile path.

**Результат: FAIL.**

## 3. Что делает V2 setter

`hass_api.py:169-178` содержит только `set_voltage`, `set_current`, `set_ovp` и
`set_ocp`, делегирующие в `_tracked_set()` и HA transport. Decision logic,
phase logic и battery chemistry там отсутствуют.

Установленный `RuntimeSafetyGuard`/`StrictRuntimeSafetyGuard` выполняет
дополнительные runtime safety/readback проверки для live writes. Это остаётся
execution/safety boundary, а не источником выбора фазы.

**Результат: PASS для самого setter-а.**

## 4. Прямой bypass

Да, существует:

```text
V2 Manual phase decision
  → app.hass.set_current()
  → app.hass.set_voltage()
  → physical adapter
```

Текущий caller не передаёт через этот переход:

- `ExecutionIntent`;
- `decision_id`/полный identity envelope;
- V3 `SafetyDecision`;
- `DecisionAuditTrail` до physical write.

Identity-bearing `PHASE_TRANSITION` публикуется после успешной записи targets
(`manual_mode.py:566-575`), то есть это не approval/audit перед исполнением.
`application.v2_identity_bridge` существует как contract-only модель, но этот
caller её не вызывает.

**Результат: FAIL.**

## 5. Решение по коду

Setter не содержит decision logic, поэтому новый hardware adapter не создавался
и `hass_api.py` не расширялся. Обнаруженное нарушение находится в caller и
требует отдельной интеграции V3 phase decision с `ExecutionIntent`, safety,
identity и audit до передачи approved targets V2 owner.

До такой интеграции controlled live retest полного V3 bridged MAIN→MIX цикла
не считается доказанным. Live output в рамках этого аудита не менялся.

## Acceptance

| Проверка | Статус |
|---|---|
| Setter только применяет target и возвращает readback result | PASS |
| MAIN→MIX решается V3 engine | FAIL |
| Targets формируются V3 intent/phase output | FAIL |
| Identity присутствует до physical write | FAIL |
| Audit присутствует до physical write | FAIL |
| Прямой domain/legacy caller bypass отсутствует | FAIL |

**Final status: `V2_SETTER_BOUNDARY_VIOLATION_FOUND`.**
