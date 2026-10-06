# V3 START activation boundary

Status: **current post-ERADICATION authority**.

The historical `StartActivationPolicy` flag bundle was deliberately removed by
commit `c107d8e` ("Simplify production START control path"). It is not part of
the current executable repository and must not be treated as a live gate.

## Current control path

```text
Operator START
  -> ProductionStartRouteAdapter
  -> StartPreflightService
  -> ApprovedStartPlan
  -> ProductionStartExecutionPort.submit_active()
  -> ProductionStartRunner
  -> StartTransactionRunner
  -> application.start_transaction_service.start_profile_transactional()
```

ACTIVE is therefore controlled by the canonical transaction path itself, not by
a second feature-flag authority layer.

## Mandatory fail-closed gates

Before physical START the current path requires:
- valid operator intent and profile/capacity;
- ownership available (not HANDS_OFF);
- no active charge session;
- fresh complete telemetry and Output OFF;
- recipe selection and target preview;
- SafetySupervisor preflight PASS;
- the application execution owner to program V/I/OVP/OCP and verify readback;
- Output ON verification;
- verified-OFF containment on failed start.

`SHADOW` and `DRY_RUN` remain explicit modes for tests and diagnostics.
Production composition uses the ACTIVE route after preflight.

No separate `explicit_active_enable`, `bench_validation_passed`,
`rollback_validation_passed`, or `physical_gate_passed` flags exist in the
current codebase. Documents that still require those flags are historical and
must be updated rather than reintroducing the retired authority layer.
