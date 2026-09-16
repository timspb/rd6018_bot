# RD6018 execution boundary model (Phase 8.1)

Статус: contracts + routing only. Physical execution is forbidden.

## Flow

```text
Application / Domain
        |
        v
ExecutionDispatcher
        |
        v
ExecutionRequest
        |
        v
ExecutionResult(deferred)
        |
        v
future approved adapter (not connected)
```

The dispatcher validates ownership and typed safety/rollback/verification
context. It does not invoke HA, ESPHome, RDTransport, controller,
SafeOutputCoordinator or any physical method.

## Contracts

`ExecutionRequest` carries the original intent or containment request, owner,
trigger, safety context, rollback policy, verification expectation, trace ID and
correlation metadata.

`ExecutionResult` distinguishes boundary acceptance from physical execution:

- `accepted=True, deferred=True` means validated and held for a future adapter;
- `rejected=True` means the request failed ownership/context validation;
- `verification_state` is a contract state, not a hardware observation.

## Ownership validation

Only currently approved V2/containment owners may be routed. UI, Telegram,
unknown and direct physical sources are not execution owners. Missing typed
safety context, rollback policy or verification expectation is rejected.

## Containment routing

Containment requests follow the same boundary and retain trace/correlation.
Routing does not issue OFF, perform verification, mutate session state or alter
the existing SafeOutput/lease semantics.

## Explicit non-goals

No adapter implementation, transport selection, physical writer, START/ACTIVE
wiring, Telegram integration, HA call, ESPHome call or RDTransport call exists
in Phase 8.1.
