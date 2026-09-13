# V3 charge strategy model

Источник стратегии: `docs/assistant/CHARGE_STRATEGY.md`.

Это чистый domain layer. Он не вызывает HA/RD/Output/Safety/Telegram и не
подключён к production controller.

## Data-driven recipe

`BatteryProfile.recipe` содержит `ChargeRecipe`, состоящий из `MainPolicy`,
`RecoveryPolicy` и `MixPolicy`. Все числовые параметры задаются в отдельных
конфигурационных моделях: targets, limits, plateau/tail timing, recovery budget,
Delta thresholds, confirmations, hold и active-Mix authority. В программах нет
зашитых recipe-чисел.

## MAIN and Recovery

`MainPolicy` отвечает за normal tail, plateau detection и решение перехода.
Tail completion не использует Delta. При подтверждённом plateau `RecoveryPolicy`
расходует общий session budget и возвращает intent в MAIN. После исчерпания
budget переход идёт в MIX; Delta не участвует в решении входа в MIX.

## MIX

`MixPolicy` делегирует регулирование отдельной политике:

- CC: наблюдение Vmax, observed Vmax, падение напряжения на Delta, confirmations,
  sticky hold, exit;
- CV: наблюдение Imin, observed Imin, рост тока на Delta, confirmations, sticky
  hold, exit.

`MixPolicy` не является chemistry. Chemistry только выбирает профиль/recipe.
После accepted Delta intent описывает completion; SAFE_WAIT/Storage и
`MIX_TIMEOUT -> STOP_AND_DIAGNOSE -> Output OFF` остаются внешней orchestration
границей и не реализуются здесь.

## Ownership and blockers

Strategy runtime state хранит counters/timestamps отдельно от generic timers.
ChargeStrategy производит только `ChargeIntent`. SafetyEngine и OutputAdapter
должны оставаться следующими boundaries до любой production migration.
