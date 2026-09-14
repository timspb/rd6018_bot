# V3 charge screen specification

Экран получает только `RuntimeUISnapshot` и `ChargeJournal`. Одна журнальная
запись отображается одной строкой; форматирование не находится в ChargeEngine.

Первая строка панели фиксирована: слева `RD6018 · ЗАРЯД · <режим
регулятора>`, справа — текущая стадия (`MAIN`, `MIX`, `FLOAT` и т.п.). Для
ручного запуска справа показывается только фактическая стадия, например
`MIX`; идентификатор АКБ находится отдельной строкой ниже.

Обязательные блоки: стадия/phase, профиль и chemistry, elapsed time этапа и
всего заряда, target V/I, active OVP/OCP limits, recipe, `waiting_for`,
transition evidence, Vmax/Imin, delta и hold.

PREP показывает старт/параметры/переход; MAIN — CC/CV и evidence; RECOVERY —
попытку, budget, причину и результат; MIX CC — Vmax/ΔV/hold; MIX CV —
Imin/ΔI/hold/containment; SAFE_WAIT — причину и следующий шаг; DONE — итог.

UI не создаёт ChargeIntent, не меняет state и не имеет доступа к RD, HA,
Output, controller или FSM.
