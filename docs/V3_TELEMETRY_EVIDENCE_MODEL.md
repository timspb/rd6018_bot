# V3 telemetry evidence layer

The V3 telemetry layer is a data boundary only. It normalizes observations and
describes their provenance and quality; it does not create `ChargeIntent`,
apply safety decisions, call HA/RD, or persist production state.

## Flow

```text
HA / RD / ESP / external sensor
              |
              v
TelemetrySnapshot + field quality
              |
       +------+------+
       |             |
 ChargeStrategy  future diagnostics
              |
              v
        SafetyEngine
```

`TelemetrySnapshot` is immutable and includes electrical, temperature, Output,
protection, programmed-readback, charge-context, and accumulated-Ah fields.
`TelemetryFieldQuality` is evaluated per field as `VALID`, `STALE`, `INVALID`,
or `MISSING`, with timestamp, age, and source.

`TelemetryHistory` is bounded in-memory evidence for plateau, MIX, relaxation,
and future diagnostic consumers. It is not stored in `ChargeState.timers`.
`ChargeAccumulator` integrates positive charging current using snapshot time and
has explicit start/reset/restore state. `TelemetryRecorder` is a persistence
interface with an in-memory implementation only at this phase.

Diagnostic consumers may turn accumulated telemetry evidence into a separate
`DiagnosticDecision`. A confirmed cell fault is represented as `HARD_STOP` with
evidence provenance; `SafetyEngine` consumes that decision and marks shutdown
as required. Telemetry collection still does not infer faults or execute the
shutdown.

## Ownership and limits

The layer owns no transport client, actuator, lease, output, strategy, or
diagnostic inference. Production HA normalization, battery registry,
`battery_fault_engine`, SG, and bank-fault scoring remain separate migration
steps. New sources or fields extend these models without changing strategy
interfaces.
