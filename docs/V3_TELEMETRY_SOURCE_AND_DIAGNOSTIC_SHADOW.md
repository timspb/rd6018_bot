# V3 telemetry source and diagnostic shadow

Этот этап добавляет только read-only границы домена.

`runtime.telemetry.source.normalize_live()` принимает уже полученный live-отчёт,
нормализует названия и типы полей в `TelemetrySnapshot` и сохраняет качество
каждого поля (`VALID`, `STALE`, `INVALID`, `MISSING`) вместе с provenance.
Адаптер не обращается к HA, не пишет состояние и не создаёт `ChargeIntent`.

`LegacyDiagnosticAdapter` преобразует уже рассчитанный V1/V2 assessment в
`DiagnosticDecision`. Он не запускает legacy evaluator и не владеет safety,
output или persistence. Явное подтверждение отказавшей банки сохраняется как
гипотеза/причина для последующей Safety-проверки; сам факт неисправности не
выводится этим адаптером из одного измерения.

Поток:

```text
HA/RD report -> telemetry evidence -> Strategy / Diagnostics -> Safety
V1/V2 assessment -> diagnostic shadow adapter -> V3 DiagnosticDecision
```

V1 UI намеренно не входит в этот migration step. Его владельцы и presentation
semantics остаются отдельным потоком, который будет разобран отдельно.
