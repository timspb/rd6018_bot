# RD6018 canonical START authority and orchestration

## Canonical flow

```text
OperatorIntent
  -> StartAuthority
  -> StartOrchestration
  -> ProductionStartExecutionPort
  -> V2StartTransactionAdapter
  -> V2 physical owner
```

`StartAuthority` is the single lifecycle admission owner. It validates the
operator request, delegates all existing eligibility and safety checks to
`StartPreflightService`, and creates the request/trace identity. A session
identity is created only for an approved START; denied requests retain only
request correlation and never receive a synthetic session.

`StartOrchestration` consumes only an approved plan. It records the ordered
authorization and handoff audit context, propagates `request_id`, `session_id`
and `trace_id`, then delegates to the existing production START port.

The route adapter is transport-only. It does not repeat validation or choose
targets. `ProductionStartExecutionPort` remains mode-aware: DRY_RUN and ACTIVE
share the same authority/orchestration path, while ACTIVE remains fail-closed
behind `StartActivationPolicy` and the existing V2 runner.

## Ownership and lease boundaries

The V2 runtime remains the physical execution owner. No START component writes
hardware or bypasses ExecutionPort/V2 handoff. Existing bot-managed lease
semantics remain scoped to managed automation; local/manual/autonomous paths are
not made dependent on the START authority's correlation context.
