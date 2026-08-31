# Mix Timeout Policy

Status: **ACCEPTED / IMPLEMENTED IN V2 AUTHORITY / PHYSICAL OFF-PATH VALIDATION PENDING**

This note defines the semantics of the existing Mix fallback maxima. It does not increase any duration.

## Core decision

The Mix maximum is an **automation-confidence boundary**, not a target duration and not evidence of successful completion.

Current automatic active-Mix ceilings remain:

| Chemistry | Automatic Mix maximum |
|---|---:|
| Ca/Ca | **20 h** |
| EFB | **24 h** |
| AGM | **10 h** |

If the active-time ceiling is reached without an already accepted Delta finish-hold, V2 now emits:

```text
MIX_TIMEOUT
-> STOP_AND_DIAGNOSE
-> request Output OFF
-> runtime verified-OFF boundary owns physical shutdown proof
-> no SAFE_WAIT / Done / Storage success path
-> operator/manual investigation required
```

`v2_authority.decide_mix_transition()` therefore no longer returns `COMPLETE_TO_SAFE_WAIT` for an exhausted Mix observation window. It returns `STOP_AND_DIAGNOSE` with reason `MIX_TIMEOUT`. `ChargeControllerV2` already maps that authority action to terminal `turn_off`; the production runtime safety layer remains responsible for proving physical OFF and retaining `_off_unconfirmed` containment if OFF cannot be proved.

## Timeout is not successful completion

The ordinary successful path remains separate:

```text
accepted CV ΔI / CC ΔV evidence
-> sticky finish hold
-> SAFE_WAIT
-> Done / Storage
```

An already-started valid finish hold keeps its accepted completion semantics even if the wall/profile deadline is crossed while that hold is running. The timeout applies when the active-Mix authority budget is exhausted **without** that accepted completion path.

The timeout is not itself a diagnosis. It does not prove sulfation, capacity loss, cell fault, stratification, or another specific defect. It proves only that automatic high-voltage authority has reached its configured boundary without standard convergence.

## Durable active-time authority

Timeout evaluation in the production controller no longer needs to trust raw wall time since `stage_start_time`. The production diagnostic controller is composed with `MixActiveAuthorityMixin`, which supplies the persisted active-Mix elapsed budget to the existing V2 decision function.

Rules:

- Mix time advances only while Output cannot be proved OFF;
- explicit Output OFF and Cooling freeze the active budget;
- live-process increments use `time.monotonic()`;
- accumulated elapsed time is persisted independently from Ah;
- after process restart, an earlier durable `active=true` record conservatively charges the uncertain downtime instead of granting it as free HV authority;
- a missing/corrupt/mismatched durable Mix authority record rejects restoration rather than reconstructing authority from Ah or an old stage timestamp.

## Relationship to adaptive current containment

`MIX_ADAPTIVE_CURRENT_CONTAINMENT.md` and this timeout policy solve different failure modes:

- adaptive current containment can only tighten available current/power during an ongoing Mix;
- the Mix active-time ceiling bounds how long AUTO may remain in the high-voltage experiment at all.

Neither mechanism replaces verified Output OFF, thermal protection, OVP/OCP, fresh telemetry, or the edge safety lease/watchdog.

## Remaining physical validation

Software tests can prove state-machine semantics, persistence and monotonicity, but the occupied hardware is still required later to prove the complete actuator path:

1. run a shortened bench-only timeout configuration on a safe load;
2. prove `MIX_TIMEOUT` never enters SAFE_WAIT/Storage;
3. prove Output OFF is physically confirmed;
4. inject failed/delayed OFF and prove `_off_unconfirmed` containment continues;
5. restart during active Mix and during Cooling/OFF and compare durable active time against the trace.

Until those BENCH gates pass, the branch semantics are implemented but not claimed as physically validated.