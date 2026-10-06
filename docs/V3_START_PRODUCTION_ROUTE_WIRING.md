# V3 production START route wiring

Status: **current post-ERADICATION authority**.

```text
Telegram callback: v2_battery_start
  -> OperatorIntent(START_CHARGE)
  -> ProductionStartRouteAdapter (ACTIVE by default)
  -> StartPreflightService
  -> ApprovedStartPlan
  -> ProductionStartExecutionPort.submit_active()
  -> ProductionStartRunner.execute_async()
  -> StartTransactionRunner
  -> application.start_transaction_service.start_profile_transactional()
  -> canonical application execution port
  -> SafeOutput / RD6018
```

There is exactly one Telegram START callback. Production no longer calls the
historical `v2_startup` facade directly. The facade only re-exports the
application-owned START service for compatibility.

## Preflight authority

The route does not bypass safety. It creates no ApprovedStartPlan unless intent,
ownership, telemetry, profile/chemistry, recipe, target and SafetySupervisor
checks pass. HANDS_OFF, an active session, invalid/stale telemetry, Output
already ON or a denied safety decision all stop the route before execution.

## Physical owner and rollback

`start_profile_transactional()` remains the single START transaction owner.
It configures the controller session, selects PREP/Main, builds the recipe
envelope and delegates physical enable to the application-scoped execution
port. V/I/OVP/OCP programming and Output ON are accepted only with verified
readback.

Any exception or unverified enable enters failed-start containment. The same
application execution owner requests Output OFF; a verified OFF clears the
session, while an unconfirmed OFF keeps the controller contained for operator
attention. The V3 transaction adapter normalizes STARTED, denied/failed and
rollback states without becoming a second actuator owner.

## Modes

- `ACTIVE`: production default after preflight; uses the preserved transaction owner.
- `DRY_RUN`: explicit diagnostic mode; routes data and creates trace without mutation.
- `SHADOW`: explicit trace-only mode.

The retired `StartActivationPolicy` and authority-window stack were removed by
`c107d8e`. They are not current prerequisites and must not be reintroduced as
parallel execution authority.

## Current physical evidence

2026-10-07 independent ESP-direct bench evidence is PASS: dual-source read-only
MATCH, programmed readback PASS, OFF -> ON -> OFF executed, ON latency 1.509 s,
10 s hold, final OFF + 0.00 A after 2.531 s. This validates the transport and
readback substrate; it is not by itself a full chemistry charge run.
