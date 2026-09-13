# V3 battery diagnostics domain

Диагностический контур отделён от стратегии заряда, safety и физического
исполнения:

```text
Telemetry Evidence -> Battery Diagnostics -> Diagnostic Authority -> Safety Evidence
```

`DiagnosticEvidenceItem` хранит только наблюдаемый факт, время, источник,
уровень уверенности и качество. `HypothesisAssessment` — интерпретация фактов,
но не абсолютный диагноз. В V3 сохранены гипотезы V1/V2: `CELL_FAULT`,
`SELF_DISCHARGE`, `SULFATION`, `STRATIFICATION`, `CAPACITY_LOSS`,
`THERMAL_ABNORMALITY`, `CHARGER_PATH`, а также уровни `NORMAL/WATCH/VERIFY/
PROBABLE/HIGH`.

`BatteryCondition` — отдельное продольное состояние АКБ и не смешивается с
гипотезой неисправности. `DiagnosticAuthority` определяет только допустимость
автоматического HV-контекста (`ALLOW`, `VERIFY_BEFORE_HV`,
`BLOCK_AUTOMATIC_HV`, `HARD_STOP`). Остановка Output выполняется только через
Safety/Output boundary; diagnostics напрямую actuator не вызывает.

Существующие V1/V2 assessment-объекты переводятся `LegacyDiagnosticAdapter` в
shadow report без запуска controller tick или физического пути. Подозрение на
банку формулируется как `CELL_FAULT` с evidence references; утверждение о
конкретной банке требует отдельных измерений.

V1 UI, battery registry и SG policy остаются отдельными migration-потоками.
