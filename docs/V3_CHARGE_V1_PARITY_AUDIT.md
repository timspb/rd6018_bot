# V3 charge domain — V1 parity audit

## Scope

Это domain-only сверка на baseline `81b769b3eede241cc69fc1dd7cd780ac96d11090`.
Output, Safety, production controller, ESPHome и физический узел не подключались.

## V1 source of truth

| V1 source | Extracted behavior |
|---|---|
| `docs/assistant/V1_BEHAVIORAL_AUDIT.md`, §3.3 | CV управляет напряжением и наблюдает ток; CC управляет током и наблюдает напряжение. |
| `docs/assistant/CHARGE_STRATEGY.md`, §Mix | CV: `Imin -> ΔI`; CC: `Vmax -> ΔV`; подтверждение и sticky hold — отдельные переходы. |
| `charge_logic.py`, `_exit_cc_condition`, `_exit_cv_condition`, `_check_delta_finish` | V1 code records `v_max_recorded`/`i_min_recorded`, but `_exit_cc_condition` currently checks voltage fall while the requested/domain CC contract checks current fall. This is an explicit V1 docs/code conflict. |

Числовые recipe/setpoint значения из V1 в V3 не переносились.

## Parity findings

| V1 behavior | V3 implementation | Result | Required fix |
|---|---|---|---|
| CC ждёт Vmax, затем фиксирует ток в точке Vmax и проверяет падение тока | `DeltaRuntimeState.observed_vmax` и `observed_reference_current`; `DeltaProgram` проверяет `Inow <= observed_reference_current - delta` | MATCH с заданным domain-контрактом | V1 docs/code должны быть reconciled before claiming full historical parity |
| CV ждёт Imin, затем фиксирует минимум и проверяет рост тока | `DeltaRuntimeState.observed_imin`; `DeltaProgram` проверяет `Inow >= observed_imin + delta` | MATCH | — |
| Confirmation counter и hold — часть Delta state | Отдельные поля `confirmation_count` и `hold_started` | MATCH | — |
| Chemistry — вход политики, не отдельная программа | Явный `ProductionChemistry -> ChemistryProfile` mapping; программы остаются Manual/Minimum/Delta | MATCH | — |
| Unknown production chemistry не должна молча попасть в профиль | Boundary mapping поднимает `ValueError` | MATCH | — |

## Исправленный дефект V3

До этой правки `DeltaProgram` использовал настроенное `reference` как экстремум и
читал `delta_confirmations`/`delta_hold_started` из `ChargeState.timers`. Это было
неэквивалентно V1 и также смешивало CC/CV. Теперь `reference` используется только
как gate достижения Vmax (CC) или Imin (CV), а baseline и timing принадлежат
отдельному `DeltaRuntimeState`.

## Unresolved V1 contradiction

`CHARGE_STRATEGY.md` и текущий requested domain contract описывают CC как
наблюдение тока после достижения Vmax, тогда как `_exit_cc_condition()` в
`charge_logic.py` проверяет падение напряжения от `v_max_recorded`. Это не было
изменено в production/V1 code. До подключения V3 к runtime требуется отдельное
решение владельца source of truth и отдельный regression vector; этот документ
не объявляет полную историческую эквивалентность, пока конфликт не закрыт.

## Boundaries

`runtime.charge.intent.ChargeIntent` — доменный результат программы. Он не является
`pb_domain.ChargeIntent`, который хранит production intent (`NORMAL`, `RECOVERY`,
и т.д.). В V3-коде импорт доменного класса выполняется из
`runtime.charge.intent`; production-код продолжает использовать `pb_domain`.

Contract vectors (`runtime/charge/contracts`) фиксируют ожидаемые решения. Runtime
shadow (`runtime/charge/shadow`) сравнивает реальные источники решений. Эти пути не
смешиваются.

## Evidence

Добавлены regression cases для CC/CV transition direction, observed references,
hold/completion и production chemistry mapping. Actuator/HA/RD/lease dependencies
не добавлялись.
