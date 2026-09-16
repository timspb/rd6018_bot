# V3 physical executor contract

```text
SafeOutputIntent -> PhysicalExecutor contract -> DryRunExecutor -> ExecutionRecord
```

`PhysicalExecutor` разделяет prepare, validate, execute, verify и rollback.
В текущем этапе `DryRunExecutor.execute()` только записывает последовательность
операций с `simulated=true`; transport, RD, HA и lease отсутствуют.

Для ENABLE зафиксирована последовательность `set V/I -> set OVP/OCP ->
readback -> enable`. Для DISABLE: `disable -> read output state -> confirm OFF ->
reset protection`. Для RESET: `reset OVP/OCP -> readback`. Реальный executor
потребует отдельного V2 bridge и bench validation с verified-off/readback/lease
доказательствами.

V1 UI не входит в physical execution gate и остаётся отдельным потоком.
