# V3 START Bench Readiness Review

Дата проверки: 2026-10-07.
Authority: current repository state after ERADICATION-09 and physical evidence PRs.

## Итоговый статус

```text
SOFTWARE ROUTE:        PASS
START PREFLIGHT:       PASS
ROLLBACK CONTRACT:     PASS (software + prior physical failure evidence)
DUAL-SOURCE READBACK:  PASS
ESP-DIRECT TRANSITION: PASS
LATENCY CHARACTERIZED: PASS
CONTROLLED CHARGE:     READY FOR EXPLICIT BATTERY/PROFILE SELECTION
PRODUCTION DEPLOYMENT: NOT CLAIMED BY THIS REVIEW
```

Старый статус 2026-09-14 устарел. В частности, retired
`StartActivationPolicy` больше не является executable authority: он был
удалён в `c107d8e` вместе с параллельным authority-window stack.

## 1. Software readiness

- Production Telegram START composition uses one `v2_battery_start` route.
- `ProductionStartRouteAdapter` is ACTIVE by default and always performs
  `StartPreflightService` before creating an ApprovedStartPlan.
- The async path is
  `ProductionStartExecutionPort -> ProductionStartRunner -> StartTransactionRunner`.
- The physical START owner is
  `application.start_transaction_service.start_profile_transactional()`.
- Historical `v2_startup.py` is compatibility-only.
- No second START/actuator owner is introduced by V3 routing.

## 2. Fail-closed START contract

A physical START is rejected before enable when any of these are false:
- ownership available (not HANDS_OFF);
- no active charge session;
- fresh complete telemetry;
- Output confirmed OFF;
- valid profile/chemistry/capacity;
- recipe selection and target preview;
- SafetySupervisor preflight.

The transaction owner then programs V/I/OVP/OCP through the canonical
application execution port and verifies readback before accepting Output ON.

On exception or unverified enable, failed-start containment requests OFF through
the same application execution owner. Verified OFF clears the session;
unconfirmed OFF leaves the controller contained and requires operator action.

## 3. Physical evidence closed in this sprint

Fresh 2026-10-07 evidence:
- HA102 and ESP128 snapshots VALID and MATCH;
- initial Output OFF and current 0.00 A;
- battery approximately 13.07 V;
- ESP-direct controlled target 13.57 V / 0.10 A;
- OVP 14.07 V / OCP 0.20 A;
- programmed readback PASS;
- Output ON confirmed in 1.509 s;
- 10 s ON hold;
- final OFF + 0.00 A confirmed in 2.531 s;
- final dual-source state remains MATCH.

Historical HA-ESP failure/retry evidence also demonstrates that a failed or
ambiguous enable is not accepted as success and the system returns to OFF.

## 4. Remaining boundary for a controlled charge bench

The transport/readback substrate is no longer the blocker. A controlled charge
must use the existing START transaction owner; no new charge loop is permitted.

Before executing it, the operator must explicitly identify the connected
battery:
- profile / chemistry (AGM, EFB, Ca/Ca as supported by current UI/domain);
- nominal capacity Ah;
- battery identity/id;
- intended program/condition.

Those values are safety-relevant inputs and cannot be inferred from the observed
13 V terminal voltage.

Immediately before START, repeat fresh telemetry/preflight and require Output
OFF. The resulting recipe target and current limit must be recorded in the same
trace. Any preflight or readback failure remains a hard deny.

## 5. Deployment statement

This review proves repository and HOME-PC bench readiness. It does **not** claim
that the current `main` is deployed on production node 101. Deployment/version
proof is a separate operational boundary.

## Decision

```text
Controlled charge bench software/physical substrate: READY
Next required input: explicit connected-battery profile + capacity + identity
No new architecture or activation-policy layer required
```
