# Mix Active-Time Authority

Status: **ACCEPTED / IMPLEMENTED IN V2 PRODUCTION COMPOSITION / PHYSICAL RESTART VALIDATION PENDING**

The Mix 20/24/10-hour fallback is an automatic high-voltage authority budget. It must therefore be based on time for which Mix is actually energized, not on legacy wall time, Ah reconstruction, or time spent paused in Cooling/Output OFF.

## Implemented authority

`mix_active_authority.py` provides a durable session-bound clock and `MixActiveAuthorityMixin` is composed into `DiagnosticProductionChargeControllerV2`, the controller used by the production V2 bootstrap.

For one Mix session:

```text
Mix + Output ON/unknown -> active budget advances
Mix + proven Output OFF -> active budget freezes
Cooling / other OFF pause -> active budget freezes
successful Mix exit -> normal completion path
active budget exhausted without accepted finish hold -> MIX_TIMEOUT
```

A telemetry state that cannot prove Output OFF is conservatively charged as active time. Runtime telemetry safety independently handles the missing/unknown Output state as a fail-close condition.

## Time sources

Inside one running process, active increments use `time.monotonic()` so NTP/system-clock adjustments cannot enlarge or shrink live Mix authority.

The persisted record contains:

- exact V2 session id;
- accumulated active seconds;
- whether the last durable state was active;
- last wall timestamp only for crash-boundary conservatism;
- optional terminal reason.

The authority is never reconstructed from Ah.

## Restart semantics

A process restart destroys the old monotonic epoch. The durable accumulated budget remains authoritative.

If the last durable record said Mix was active, the interval between the last durable write and reconstruction is **conservatively charged as active**. This prevents a bot crash from granting free HV time merely because no monotonic sample could be recorded during the outage.

If the durable record proved inactive before restart, downtime does not consume Mix authority.

If the durable state is missing, corrupt, or belongs to another session, an active/Cooling-from-Mix session is rejected for restore. V2 does not guess elapsed authority from Ah or `stage_start_time`.

## Cooling and OFF

The existing production Cooling contract already preserves the exact source stage/target and freezes evidence clocks. The new Mix authority adds an independent durable active-time source. A Cooling interval cannot consume the 20/24/10-hour Mix budget after the controller has proved the Mix output inactive.

This is intentionally separate from the 15-minute communication lease:

```text
edge lease renewal != Mix authority renewal
```

Renewing communication authority never resets or extends Mix chemistry authority.

## Timeout integration

The existing V2 decision engine still receives a `mix_elapsed_s`, but production composition supplies that value from the durable active-time authority rather than raw wall time since stage entry. This keeps the central policy pure while replacing the unsafe time source at the production boundary.

Normal Delta finish-hold remains a separate accepted completion path. If no finish hold has started and the active-time ceiling is reached, the result is `MIX_TIMEOUT -> STOP_AND_DIAGNOSE`, not SAFE_WAIT success.

## Software validation

Unit coverage proves:

- active time advances while active;
- explicit inactive intervals freeze the budget;
- active crash downtime is conservatively charged after reconstruction;
- inactive crash downtime does not consume budget;
- missing or mismatched session state is rejected;
- corrupt state is rejected;
- terminal reason and elapsed budget survive reconstruction.

The production dashboard/timer path uses the durable elapsed value when available instead of presenting the raw legacy wall clock as Mix authority.

## Remaining BENCH gate

When the hardware is free, validate:

1. normal Mix with Output ON against an external trace clock;
2. Cooling duration does not consume Mix active budget;
3. explicit Output OFF pause does not consume Mix active budget;
4. process restart while Mix was energized conservatively consumes the outage interval;
5. process restart after proven OFF does not consume the outage interval;
6. missing/corrupt authority file prevents automatic Mix restoration;
7. shortened bench timeout produces `MIX_TIMEOUT` and verified physical OFF.

Until those tests are run, software authority is implemented and CI-testable, but no physical timing claim is made.