# V3 SafetyEvidence pipeline

```text
Telemetry / Diagnostics -> SafetyEvidence -> SafetyEngine -> SafetyDecision
```

`SafetyEvidence` — единственный domain-level мост между диагностикой и Safety.
Он содержит источник, время, authority, severity, допустимость, confidence и
ссылки на evidence. `SafetyEngine.evaluate_evidence()` агрегирует несколько
источников по приоритету `HARD_STOP > BLOCK_AUTOMATIC_HV > VERIFY_BEFORE_HV >
ALLOW` и выдаёт только `SafetyDecision`.

`SafetyDecision` здесь не является командой: shadow consumer не создаёт
`OutputIntent`, не вызывает RD/HA и не меняет lease. Физическое выключение
останется отдельной Output migration gate.

`SafetyParityComparator` сравнивает только decision snapshots V1/V2 и V3;
расхождения фиксируются как `MISMATCH` и не исправляются автоматически.

V1 UI не входит в этот контур и остаётся отдельным этапом.
