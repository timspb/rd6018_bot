# RD6018 V3 Observer Live Run Validation R2

## Result

**`BLOCKED` for deployment validation.** Live sources are reachable and a
local observer-format snapshot was built from the same read-only observations,
but deployed node 101 revision `10af870` does not contain the V3 observer
modules. No deployment or restart was performed.

## Deployment boundary

| Check | Result | Evidence |
|---|---|---|
| node 101 access | PASS | saved WinSCP session, read-only |
| `rd6018-bot.service` | PASS | `active` |
| deployed revision | PASS | `10af870` |
| `V3ObserverComposition` on 101 | BLOCKED | module absent |
| `OperatorDashboardState` on 101 | BLOCKED | module absent |
| Telegram operator adapter on 101 | BLOCKED | module absent |
| V3 deployment run | NOT RUN | would require deployment change |

This is a deployment-parity blocker, not an authentication or source-
availability blocker.

## Live source checks

All checks were read-only:

- HA `192.168.1.102`: API reachable; 220 states returned, 57 RD6018-related.
- ESPHome `192.168.1.28:6053`: native API reachable; device info and 66
  entities returned; no service calls were made.
- RD observation: output `ON`; approximately `17.11 V`, `3.49 A`, `59.74 W`;
  constant-current mode; internal/external temperature `44/36 °C`;
  protection code `0`.
- Lease observation: armed; approximately 676 seconds remaining at the
  observation point. No renewal, disarm, or lease command was sent.

## Current-session snapshot

The read-only persisted manual state on node 101 reported:

- profile: `Baic72`;
- state: `active`;
- phase: `mix`;
- identity: absent (`LEGACY_NO_IDENTITY`).

The local V3 observer contracts rendered one read-only snapshot from these live
observations:

- session: `Baic72 / mix / active`;
- telemetry: `17.11 V / 3.49 A / 59.74 W / 44 °C`;
- parity: `MATCH` for supplied V2/V3 state fields;
- safety: protection code `0`, lease armed;
- timeline: `UNKNOWN / 0 events` because the active legacy session has no
  identity and no canonical timeline;
- Telegram formatter: current state, explanation `UNKNOWN`, and
  `CONTROL: недоступен`.

This local formatting check is not claimed as deployment-runtime validation.

## UI findings

| Requirement | Result |
|---|---|
| current active session | PASS locally |
| current telemetry | PASS locally |
| no fake START | PASS |
| no stale timeline events | PASS; timeline empty/unknown |
| Delta/Hold markers | BLOCKED; no canonical timeline/identity |
| phase explanation | PARTIAL; reason/next transition `UNKNOWN` |
| control path | PASS; observe-only |

## Side-effect proof

No START/STOP, HA write, ESPHome service, RD command, lease operation,
restart, ownership change, or physical execution was performed.

## Required next step

Deploy the existing V3 observer modules through the normal deployment
procedure, preserving the current service and backing up the dirty deployed
tree first. Then repeat this R2 validation. Until then status remains
`BLOCKED`; production readiness is not inferred.
