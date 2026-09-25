# V3 bank-fault evidence and SafetyEvidence

Контур использует наблюдаемые признаки, а не флаг `BankFault=True`:

```text
Telemetry Evidence -> BankFaultEvidence -> Battery Diagnostics
                    -> DiagnosticAuthority -> SafetyEvidence -> Safety shadow
```

Поддерживаются признаки медленного роста напряжения, чрезмерной длительности
MAIN, слабого Ah-прогресса, relaxation decay, температурного роста без прироста
напряжения, self-discharge и устойчивого низкого напряжения. Их веса и пороги
находятся в `BankFaultPolicy`, поэтому scoring не содержит монолитных `score +=`
констант. Уровни: `STABLE`, `WATCH`, `PROBABLE`, `HIGH`.

`LegacyBankFaultAdapter` переводит только готовый V1/V2 risk snapshot в signals.
Он не запускает FSM, controller или actuator. Признаки формируют гипотезу
`CELL_FAULT suspected`; конкретная банка не заявляется без отдельных измерений.

`SafetyEvidence` — read-only boundary между authority и SafetyEngine. Он не
создаёт OutputIntent и не выключает заряд физически. V1 UI, registry, SG и
production wiring остаются отдельными этапами.

По канону V1/V2 высокий inferred score блокирует автоматический HV (`BLOCK_AUTOMATIC_HV`),
но не является сам по себе `HARD_STOP`: hard stop требует отдельного внешнего
подтверждения неисправности или независимого hard-safety слоя.
