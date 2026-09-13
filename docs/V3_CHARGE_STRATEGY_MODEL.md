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

`FinishIntent` обозначает границу post-charge слоя; SAFE_WAIT и Storage здесь
не реализуются и actuator authority в этой модели отсутствует.

## Parity completion pass

Recovery exhaustion is profile policy: Ca/Ca/EFB may enter MIX after the
configured recovery budget, while AGM returns/remains in MAIN and uses its
configured fallback policy. `MainFallbackPolicy` models the separate long-MAIN
decision: Ca/Ca/EFB enter MIX; AGM enters MIX only for configured CV/low-current
evidence, otherwise returns a diagnostic stop intent.

`PlateauDetector` consumes measurement history and distinguishes flat CV plateau
from a materially falling current (progress). `MixAuthorityState` accounts for
active session time and produces `MIX_TIMEOUT` when the configured authority is
exhausted. Post-charge `FinishIntent` is only a boundary marker; SAFE_WAIT and
Storage are intentionally outside this domain.

`ChargeStrategy` is the new domain execution owner. The old registry/
`DeltaProgram` path remains available only for compatibility and shadow/adapter
tests; it is not wired into the new recipe-backed strategy path.

## MIX protection completion

CV MIX has an explicit `MixCurrentContainmentState`. After the configured delay
from MIX start, the domain limits the current intent to the confirmed
`Imin + Delta-I + headroom`; recalculation is cadence-controlled and monotonic,
so a rising measured current cannot raise the issued setpoint. The domain does
not write the device.

`ResetProtectionIntent` describes the OVP/OCP values the outer execution layer
must restore after normal MIX completion or emergency MIX stop. It is an intent
only; the physical reset remains outside this module.

`MixTemperatureIntegrityPolicy` reuses the shared, calibrated
`ExternalTempIntegrityMonitor`. A latched fresh-sample anomaly produces a MIX
stop/diagnostic decision; it does not compensate by lowering current or continue
the charge.
