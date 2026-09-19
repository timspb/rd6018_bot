# RD6018 V3 Physical Boundary Validation

Режим: validation model / shadow only. Physical execution, live ownership,
V2, HA, ESPHome, lease and START/ACTIVE не изменялись.

## Result

**V3 physical boundary: NOT VALIDATED for production.**

Pure contract and failure-model checks pass. Physical capability remains
`BLOCKED` because no real adapter, transport, lease takeover or hardware
command was connected or executed.

## 1. Physical execution capability map

`application/physical_boundary_validation.py` defines
`PhysicalExecutionCapability` for:

| Operation | Owner | Adapter | Transport | Status |
|---|---|---|---|---|
| OUTPUT_ON | V3 Execution Boundary | V3 adapter, not connected | RD transport, not configured | BLOCKED |
| OUTPUT_OFF | V3 Execution Boundary | V3 adapter, not connected | RD transport, not configured | BLOCKED |
| SET_VOLTAGE | V3 Execution Boundary | V3 adapter, not connected | RD transport, not configured | BLOCKED |
| SET_CURRENT | V3 Execution Boundary | V3 adapter, not connected | RD transport, not configured | BLOCKED |
| STOP | V3 Execution Boundary | V3 adapter, not connected | RD transport, not configured | BLOCKED |
| CONTAINMENT | V3 Execution Boundary | V3 adapter, not connected | RD transport, not configured | BLOCKED |

For each operation the model records target, expected verification and rollback.
It does not instantiate a transport or executor.

## 2. Readback verification model

The pure `ReadbackVerificationModel` enforces:

```text
command result != physical success
physical action -> fresh readback -> verification result
```

Explicit results cover:

- `MISSING_READBACK`;
- `READBACK_UNAVAILABLE`;
- `STALE_READBACK`;
- `READBACK_MISMATCH`;
- `VERIFIED`.

No command retry or physical action is performed by this model. Production
timeout values remain configuration/contract decisions; the tests use supplied
values only.

## 3. ESPHome / lease parity

The parity model records the current contract:

- current dead-man owner: ESPHome/edge dead-man;
- TTL: 900 s;
- renewal interval: 300 s;
- fail-safe: local dead-man containment on expiry.

The model detects duplicate owners and classifies expired/unavailable lease as
containment/fail-safe conditions. It does not renew, disarm, arm, or manipulate
the lease.

Required validation remains: exact deployed ESPHome package, matching Python
contract, generation/armed/tripped/remaining readback, expiry behavior and
manual intervention/rollback on the target node.

## 4. Safety-to-physical boundary

The modeled chain is:

```text
Detection -> Safety Decision -> Containment Request
           -> V3 Execution Boundary -> Adapter -> Readback Verification
```

Traceability is required at each stage. Current V2/SafeOutput/edge physical
safety writers are not replaced or disabled. Therefore the model is
`SHADOW_ONLY`/`BLOCKED` at execution, not a live safety owner.

## 5. Bench validation plan — not executed

| Scenario | Setup | Expected behavior | Rollback/pass criteria |
|---|---|---|---|
| Normal charge transition | isolated RD + matched ESPHome package | intent reaches approved adapter; fresh V/I/readback confirms each step | verified readback; abort to safe OFF |
| STOP | active bench session with operator approval | STOP creates OFF intent and requires fresh OFF confirmation | no resume after ambiguous OFF; pass only with positive OFF |
| Emergency containment | injected safety fault | containment path requests OFF and records trace | local dead-man remains final protection; verified OFF or latched failure |
| Readback failure | suppress/invalid expected readback | explicit missing/stale/mismatch result; no assumed success | safe containment and diagnostic evidence |
| Telemetry loss | remove telemetry source while output is controlled | policy follows approved recovery/containment window | no hidden command or unverified state |
| Lease loss | expire or isolate lease renewal | edge dead-man remains authoritative and fails safe | verify trip/OFF and manual reauthorization |
| Transport failure | disconnect adapter/transport | command is unconfirmed/deferred, never treated as success | rollback/containment according to policy |
| Restart recovery | restart software with output/lease states varied | no silent resume; fresh verification and operator gate | state classified and safe recovery recorded |

These tests require an approved bench, exact hardware/firmware, operator,
rollback procedure and explicit authorization. None were run in this
workstream.

## 6. Readiness assessment

| Gate | Status |
|---|---|
| pure capability model | PASS |
| readback failure model | PASS |
| lease parity model | PASS as documentation/contract |
| safety trace model | PASS as documentation/contract |
| real adapter capability | BLOCKED |
| exact ESPHome/lease parity | BLOCKED |
| bench evidence | NOT RUN |
| physical ownership transfer | NOT AUTHORIZED |

**Decision: V3 physical boundary is NOT VALIDATED. Do not cut over.**

No V2 runtime, physical command, HA/ESP write, lease operation or ownership
change was performed.
