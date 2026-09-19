# RD6018 Safety Philosophy Audit

Статус: **SAFETY_BOUNDARY_CONFIRMED**

Дата аудита: 2026-09-16  
Режим: read-only audit; runtime, ownership и физическое исполнение не изменялись.

## Scope

Проверены:

- V3 `application/safety/SafetyPolicy`;
- V2 hardware/output safety boundary в `safe_output.py`;
- V2 runtime safety guard в `runtime_safety_v2.py`;
- ESPHome `rd6018_intrinsic_safety.yaml`;
- ESPHome `rd6018_safety_lease.yaml`;
- связанные safety/lease contract tests.

## 1. Dead-man lease

Результат: **CONFIRMED**, с явным разделением режимов.

- TTL lease равен 900 секундам и применяется к `managed_session`, то есть к remote/autonomous control ownership.
- Истечение lease в managed режиме приводит к edge-local containment (Output OFF/latched trip). Это ожидаемая dead-man семантика для удалённого управляемого режима, а не универсальная safety-логика батареи.
- `autonomous_mode` отделённым persistent-флагом исключён из managed lease renewal/expiry path. При валидном состоянии `autonomous && !managed` boot quarantine и lease expiry не отключают локальный режим.
- `HANDS_OFF` не объявляет автономный режим и не запускает скрытый resume; это отдельное освобождение managed ownership.
- Конфликт `managed_session && autonomous_mode` закрывается fail-closed, поэтому два ownership authority не допускаются.

Вывод: lease не является владельцем локальной intrinsic safety и не используется для преобразования локального режима в remote fault. В managed режиме потеря heartbeat намеренно является containment-событием.

## 2. Offline operation

Результат: **CONFIRMED**.

`rd6018_intrinsic_safety.yaml` явно отделён от WiFi, HA, ESPHome availability, Telegram и managed lease. Локальная защита использует только локальные RD/Modbus evidence:

- внутреннюю температуру PSU;
- hardware protection register;
- локальный Output OFF path.

Отсутствие/устаревание telemetry само по себе не превращается в автономный intrinsic OFF; managed communication-loss policy остаётся отдельным владельцем в lease/runtime слое. Это сохраняет различие между локальной работой RD и удалённой управляемой сессией.

## 3. Chemistry neutrality

Результат: **CONFIRMED**.

- V3 `application/safety/SafetyPolicy` принимает только конфигурируемые hardware limits и emergency protection codes.
- В SafetyPolicy нет SLA/Li/AGM/EFB/Ca/Ca/KAK assumptions, battery names или chemistry profiles.
- V2 `SafetyPolicy` содержит физический envelope и принимает `recipe_voltage_ceiling_v` как входной предел вызывающего слоя; recipe semantics не определяются safety layer.
- В `runtime_safety_v2.py` chemistry/recipe selection остаётся выше safety boundary; safety только проверяет envelope и readback.

## 4. Setpoint neutrality

Результат: **CONFIRMED**.

Voltage/current targets трактуются как requested operator/program intent. Safety:

- не выбирает targets;
- не выбирает программу или химию;
- проверяет targets на абсолютные hardware ceilings и корректность OVP/OCP envelope;
- проверяет фактический output/readback после применения.

Таким образом, setpoint не является safety truth: authoritative safety evidence — фактические telemetry/readback, protection status, freshness и emergency state.

## 5. Safety scope

Результат: **CONFIRMED**.

ALLOW/DENY/containment ограничены следующими классами:

- hardware voltage/current/temperature limits;
- protection status и unknown protection;
- telemetry/readback integrity and freshness;
- explicit emergency conditions;
- безопасная проверка output state и programmed readback.

Transport/HA/WiFi/Telegram не импортируются V3 Safety Domain. HA/ESPHome участвуют только как внешние источники/исполнители существующего V2 boundary; они не становятся владельцами safety decision.

## Evidence matrix

| Область | Evidence | Результат |
|---|---|---|
| Lease scope | `rd6018_safety_lease.yaml`, lease contract tests | 900s managed dead-man; autonomous path отделён |
| Offline safety | `rd6018_intrinsic_safety.yaml`, intrinsic contract tests | local protection не зависит от WiFi/HA/bot |
| V3 safety purity | `application/safety/policy.py`, `models.py` | chemistry/transport/ownership отсутствуют |
| V2 output safety | `safe_output.py`, `runtime_safety_v2.py` | limits, protection, freshness, readback |
| Setpoint semantics | `OutputRequest`, `SafetyPolicy.preflight/verify_live_output` | intent проверяется; фактический readback остаётся authoritative |

## Residual boundary note

Managed lease expiry и локальная intrinsic protection обе могут привести к physical containment, но имеют разные владельцы и разные причины:

- lease: remote/managed ownership dead-man;
- intrinsic safety: локальная защита RD/ESPHome от hardware fault.

Их нельзя объединять в один общий «WiFi fault» или chemistry decision. Текущая реализация сохраняет это разделение.

## No changes

- V2 runtime не изменялся.
- SafetyPolicy не изменялась.
- Lease ownership и autonomous mode не изменялись.
- HA/ESPHome/Modbus configuration не изменялась.
- Команды и физические операции в рамках аудита не выполнялись.

## Final decision

**SAFETY_BOUNDARY_CONFIRMED** — проверенные safety boundaries соответствуют заданной философии: lease ограничен managed remote ownership, локальная safety работает offline, chemistry и setpoints не являются скрытой safety authority, а safety decision основан на hardware limits, protection, telemetry integrity и emergency evidence.
