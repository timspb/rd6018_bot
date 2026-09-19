# RD6018 V3 Physical Execution Boundary Model

Статус: **PHYSICAL_EXECUTION_BOUNDARY_READY**

Создан transport-agnostic контракт в `application/physical_boundary/`.

## Contract

```text
ExecutionIntent
      |
      v
SafetyDecision
      |
      v
PhysicalExecutionRequest
      |
      v
acceptance -> apply -> readback -> verification
      |
      v
PhysicalExecutionResult
```

`PhysicalExecutionBoundary` только проверяет safety decision и формирует request либо rejected result. Он не содержит executor, adapter, transport или physical call.

## Request

`PhysicalExecutionRequest` фиксирует intent/decision identity, requested V/I, safety approval и timestamp.

## Result/failures

`PhysicalExecutionResult` различает accepted, rejected, applied, verified и mismatch. Failure taxonomy:

- `UNAVAILABLE`;
- `TIMEOUT`;
- `MISMATCH`;
- `STALE_READBACK`;
- `REJECTED`.

## Scope

RD6018, ESPHome, HA, Modbus, node 101 и production wiring не подключались. Реальные команды отсутствуют.
