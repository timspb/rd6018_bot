# V3 production START route wiring

Current route:

```text
Telegram callback: v2_battery_start
        |
        v
OperatorIntent(START_CHARGE)
        |
        v
ProductionStartRouteAdapter
        |
        v
StartPreflightService
        |
        v
ApprovedStartPlan
        |
        v
        ProductionStartExecutionPort(DRY_RUN)
        |
        v
V2StartTransactionAdapter.prepare()
        |
        v
ProductionStartRunner (constructed, ACTIVE-gated)
        |
        v
V2StartTransactionExecutor -> V2 transaction owner (ACTIVE only)
```

The production default is `DRY_RUN`. It performs telemetry, ownership, recipe,
target and safety preflight, creates a correlation trace and prepares the V2
transaction input. It does not mutate session/FSM state, call
`start_profile_transactional()`, program setpoints, enable Output, or write
Home Assistant.

Composition creates one shared `StartActivationPolicy`, transaction adapter,
`ProductionStartRunner` and `V2StartTransactionExecutor`. The transaction
executor creates
an immutable `V2StartEventContext` containing `trace_id`, actor, source,
intent/condition metadata, profile, capacity and correlation metadata. This
context is data-only and does not contain controller, FSM, session, HA or
physical objects. In the default DRY_RUN route it is not consumed by the V2
owner.

Operator feedback is a separate `OperatorFeedbackPort`. The
`LegacyOperatorFeedbackBridge` carries only status text, trace correlation and
metadata to a future Telegram/UI adapter; no Telegram object is placed in
`V2StartEventContext`, and the bridge has no runtime or physical authority.
`TelegramOperatorFeedbackAdapter` is the transport implementation for sending
or editing that feedback; it does not create intents or invoke execution.

ACTIVE calls use the canonical `ProductionStartRunner` with
`StartActivationPolicy`; the default policy still denies ACTIVE. Legacy callback
feedback is a pure presentation event factory and is not an execution boundary.

`v2_startup.start_profile_transactional()` remains the preserved V2 execution
owner for the future explicitly gated ACTIVE handoff. The Telegram route no
longer calls it directly.

## Current invariants

- exactly one `v2_battery_start` callback is registered;
- ACTIVE construction is rejected by the route adapter;
- pending START preview is retained after DRY_RUN because no charge started;
- V2 controller, FSM, SafetySupervisor, SafeOutputCoordinator and physical
  layer are unchanged;
- rollback and verified-OFF mapping remain in `V2StartTransactionAdapter`.

## Remaining blockers before bench ACTIVE

1. Complete the documented START bench validation checklist.
2. Validate rollback and `OFF_UNCONFIRMED` containment on the target hardware.
3. Prove physical gate, lease and readback parity.
4. Enable ACTIVE only through a separately reviewed feature configuration.
5. For ACTIVE, provide the real V2 event/message context required by the
   preserved owner; the data-only context is intentionally insufficient for
   physical execution and must not be treated as a bench approval.

Until all gates pass, Telegram START is a non-actuating preflight/DRY_RUN
operation and must not be reported as a started charge.
