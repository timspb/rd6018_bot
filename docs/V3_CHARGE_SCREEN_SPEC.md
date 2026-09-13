# V3 charge screen specification

Экран получает только `RuntimeUISnapshot` и `ChargeJournal`. Одна журнальная
запись отображается одной строкой; форматирование не находится в ChargeEngine.

Обязательные блоки: стадия/phase, профиль и chemistry, elapsed time этапа и
всего заряда, target V/I, active OVP/OCP limits, recipe, `waiting_for`,
transition evidence, Vmax/Imin, delta и hold.

PREP показывает старт/параметры/переход; MAIN — CC/CV и evidence; RECOVERY —
попытку, budget, причину и результат; MIX CC — Vmax/ΔV/hold; MIX CV —
Imin/ΔI/hold/containment; SAFE_WAIT — причину и следующий шаг; DONE — итог.

UI не создаёт ChargeIntent, не меняет state и не имеет доступа к RD, HA,
Output, controller или FSM.
