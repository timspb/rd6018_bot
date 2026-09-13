# V3 Phase 5E + Phase 6 — complete charge domain

Статус: domain complete, production не подключён

Baseline: `09d434a4d00df3e551a2c048d9bc2abc1c90a17f`

## Domain path

```text
BatteryProfile
      ↓
ChargeEngine
      ↓
ProgramRegistry
      ↓
+ ManualProgram
+ MinimumProgram
+ DeltaProgram
      ↓
ChargeIntent
```

`DeltaProgram` реализует только pure decision logic: unarmed → tracking,
confirmation → sticky hold, hold completion и invalid/stop outcome. `DeltaConfig`
задаёт mode CV/CC, reference, delta, confirmations и hold duration. Program не
вызывает инфраструктуру и не изменяет state.

`ProgramRegistry` отвечает только за register/lookup/create. Default registry
содержит `manual`, `minimum`, `delta`; unknown names отклоняются. Он не выполняет
programs и не владеет safety/output.

`ChargeEngine` сохраняет прежний direct-program API и дополнительно умеет создать
active program через `ProgramRegistry` по name/config. Его output — только
`ChargeIntent`.

## Ownership

- BatteryProfile/Measurements/ChargeState/ChargeIntent — domain data contracts.
- Program classes — pure algorithm decisions.
- Registry — lookup/creation only.
- Engine — orchestration only.
- SafetyEngine, OutputAdapter, HA/RD/ESP, lease, persistence и Telegram остаются
  внешними boundaries.

## Decision contracts

Existing Manual/Minimum representative contracts остаются fixed vectors. Delta
contract vectors дополнены native transition tests. Любой mismatch должен быть
зафиксирован по полю и разобран до дальнейшей миграции; registry не скрывает
расхождения.

## Migration readiness

Чистый domain path существует независимо от legacy runtime. Это не означает
production parity: текущие controller/FSM, legacy Manual/Minimum/Delta behavior,
restore, safety, lease и output execution ещё не переведены на этот путь.

Следующая миграция требует отдельного adapter/parity gate для полного Delta
contract, затем явного safety integration design. До этого `RuntimeApp` и
production entrypoint не должны импортировать registry/programs как actuator
path.

Production runtime, controller/FSM, UI, ESPHome/YAML и node 101 не изменялись.
