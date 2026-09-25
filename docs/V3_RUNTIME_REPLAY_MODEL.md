# V3 runtime replay и decision trace

```text
Telemetry recording -> ReplayRunner -> RuntimeOrchestrator -> DecisionTrace
                                             -> Journal / ReplayComparator
```

Replay использует `TelemetryReplayRecord` и инъецируемый
`ReplayTelemetryProvider`. Каждый tick фиксирует telemetry, stage/phase,
charge, safety, execution decision и хвост журнала. Одинаковая входная
последовательность должна давать одинаковый trace; `MATCH/MISMATCH` сравнивают
только decision fields, а отсутствие expected checkpoint даёт `INCONCLUSIVE`.

Harness не импортирует физический bridge и не выполняет RD/HA/Output/lease
операции. Он предназначен для анализа перед bench gate. V1 UI остаётся
отдельным потоком.
