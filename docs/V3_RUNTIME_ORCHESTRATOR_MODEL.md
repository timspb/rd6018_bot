# V3 runtime orchestrator

```text
Telemetry -> RuntimeOrchestrator -> Diagnostics -> ChargeService -> Safety
                                      -> ExecutionPolicy -> Journal -> UI snapshot
```

`RuntimeContext` содержит только явно переданные сервисы. `RuntimeOrchestrator`
владеет порядком вызовов и lifecycle, но не владеет FSM, charge algorithm,
safety policy или physical output. Ошибки telemetry/strategy/diagnostics/safety
фиксируются в журнале и не проходят незамеченными.

`process_command()` принимает внешний command adapter и возвращает его
`DomainIntent`; прямого пути UI → Output нет. `build_snapshot()` только отдаёт
последнюю view model. Production runtime не подключён.

V1 UI и его presentation semantics остаются отдельным потоком.
