# RD6018 V3 logical end-to-end shadow validation — Phase 7.2

## Scope

This phase validates the logical pipeline with domain objects and shadow
transport adapters only. It does not modify production composition and does not
send commands to HA, ESPHome or RD6018.

```text
OperatorIntent
      |
      v
ChargeApplicationService
      |
      v
ChargeEngine -> DomainDecision
      |                 |
      |                 +--> ContainmentResultRequest
      +--> ActuatorIntent
                     |
                     v
              ExecutionDispatcher
                     |
             HA shadow / ESP shadow
                     |
                     v
               ExecutionResult
```

## Validated scenarios

| Scenario | Shadow assertion |
|---|---|
| START AGM | Profile registry and application service create a logical active session and domain decision. |
| Telemetry update | New telemetry is evaluated without a provider or transport object. |
| Phase transition | Domain transition is represented as a domain diagnostic event. |
| STOP request | Application produces a containment request; dispatcher returns deferred result. |
| Containment request | Request preserves trace, owner, rollback and verification context. |
| Transport deferred | Both shadow adapters return the same deferred semantics and perform no I/O. |
| Invalid safety context | Blocked context is rejected by the adapter before any execution boundary. |

## Cross-cutting evidence

- `DiagnosticEvent` and `TraceCorrelation` preserve one trace across domain and
  execution observations;
- `ConfigurationModel` resolves documented profile and safety values while
  retaining source provenance;
- candidate persistence is an in-memory state snapshot only; no file, DB or
  runtime state is written;
- shadow adapters implement contract-shaped behavior but contain no HA or
  ESPHome client and no physical writer.

## Explicit non-goals

This validation does not change START, ACTIVE, Telegram, production bootstrap,
SafetySupervisor, SafeOutputCoordinator, HA, ESPHome, persistence, or physical
execution. A deferred `ExecutionResult` is not evidence of a physical action.
