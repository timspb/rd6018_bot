# RD6018 Canary Blocker Closure — AUTONOMOUS WORKSTREAM 94

Статус: `BLOCKED_WITH_REASONS`

Design/policy closure выполнена; live approval и live safety evidence не
создавались искусственно. V2 остаётся production/physical owner.

## 1. Canary approval model

Добавлен data-only контракт `application.canary_approval.CanaryApproval`:

```text
approval_id
mode: OBSERVE_ONLY | SHADOW_DECISION | APPROVED_CANARY
scope
constraints
approved_at / expiry
rollback_conditions
revoked
```

Контракт immutable, проверяет expiry и требует rollback conditions. `revoke()`
возвращает новый объект. Создание approval, активация Canary и authority
transfer этим workstream не выполнялись.

## 2. Fresh safety evidence policy

Для review обязательны:

- fresh RD readback и output state;
- telemetry timestamp/freshness;
- lease owner, active, remaining, tripped/quarantine и armed freshness;
- protection state;
- source availability/confidence;
- containment/rollback observation.

Freshness policy: stale safety/lease indicators блокируют review; missing или
unknown safety state даёт `DENY/BLOCKED`; telemetry stale даёт `UNKNOWN`, а не
assumed safe. Никакие renewal, takeover или physical recovery не выполняются
автоматически.

## 3. Source parity authority map

| Source | Authoritative fields | Derived/normalized | Diagnostics only |
|---|---|---|---|
| RD readback | measured V/I, output, protection, CC/CV, device status | power, freshness | transport age/errors |
| ESPHome | edge availability, lease entities, published device state | source confidence | API connectivity details |
| HA | entity mirror and historical/read-only observations | arbitration view | Recorder gaps |
| V2 state | program, lifecycle, phase, targets, session state | V3 shadow input | legacy identity gaps |

No single source is allowed to silently override fresh conflicting safety or
physical observations. Conflicts are `DIVERGENCE/BLOCKED` until explained.

## 4. Legacy identity policy

- Legacy sessions without `session_id`/`trace_id` remain allowed for observe-only
  parity.
- Legacy sessions are forbidden as Canary decision inputs.
- New sessions require identity before canonical lifecycle evidence.
- No synthetic identity, fake START or post-factum lifecycle is permitted.

## 5. Static configuration/namespace audit

Passed: pure `application/charge_program`, `application/charge_engine` and
`application/execution_intent` contain no forbidden V2/HA/ESPHome/Modbus
imports or physical calls.

Still open:

- `v3_core` mixes domain, parity, hardware-validation and bench namespaces;
- program catalog owns recipe/default values that need canonical configuration
  provenance;
- compatibility-shaped phase fields remain in some development models.

These are cleanup blockers, not silently ignored findings.

## 6. Blocker disposition

| Blocker | Status | Closure requirement |
|---|---|---|
| CB-APPROVAL | OPEN | real explicit approval from authorized owner |
| CB-SAFETY-FRESHNESS | OPEN | fresh lease/containment evidence with timestamps |
| CB-SOURCE-PARITY | OPEN | one correlated HA/ESPHome/RD/V2 read-only window |
| CB-LEGACY-IDENTITY | POLICY CLOSED | legacy observe only; identity-bearing new session required |
| CB-CONFIG-NAMESPACE | OPEN | separate namespaces and close duplicate provenance |

## 7. Side effects

No START, STOP, PAUSE, physical command, lease operation, ownership transfer,
production activation or V3 hardware control was performed.

**Conclusion:** policy gaps are closed, but blockers requiring fresh external
evidence and explicit human approval remain. Correct status is
`BLOCKED_WITH_REASONS`; `V3_CANARY_REVIEW_READY` is not yet supportable.

## 8. Fresh read-only evidence after explicit authorization

Fresh HA GET snapshot was collected after authorization. No service endpoint
was called. At observation time:

```text
HA: reachable
ESPHome TCP 192.168.1.28:6053: reachable
Output: OFF
RD voltage/current/power: 0.0 V / 0.0 A / 0.0 W
Battery voltage: 12.73 V
Protection: code 0, normal, tripped=false
CC/CV: CC=false, CV=true
Readback setpoints: 13.0 V / 0.4 A
Temperatures: internal 31 C, external 25 C
```

This is a safe idle observation and does not prove authenticated direct
ESPHome parity or a live lease state. It therefore improves freshness for the
HA/RD read path but does not close `CB-SAFETY-FRESHNESS` or `CB-SOURCE-PARITY`.
No physical action was taken despite the observed configured setpoints.
