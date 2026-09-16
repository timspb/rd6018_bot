# RD6018 V3 shadow acceptance model — Phase 10.2

## Metrics

`ShadowAcceptanceModel` calculates metrics from analytical shadow evidence:

- decision parity: equal rate, expected divergence rate, unexpected conflict
  rate;
- safety parity: safety, containment and telemetry-interpretation conflicts;
- configuration stability: unresolved configs, conflicting sources and missing
  authority;
- transport readiness: HA telemetry, ESP telemetry and arbitration stability;
- execution readiness: intent parity, rollback coverage and verification
  coverage.

Rates use the number of shadow observations as the denominator. No observations
is `NOT_READY`, never an implicit pass.

## Status rules

| Status | Objective condition |
|---|---|
| `NOT_READY` | No evidence, unresolved configuration, safety parity failure, or a hard blocker. |
| `OBSERVATION_READY` | Evidence exists and hard blockers are absent, but observation volume or acceptance metrics are incomplete. |
| `SHADOW_ACCEPTED` | Minimum observation volume, conflict-rate threshold, zero safety conflicts, stable configuration/transport and complete execution evidence. |
| `OWNERSHIP_CANDIDATE` | All `SHADOW_ACCEPTED` criteria plus a separate explicit approval flag. This model does not change ownership. |

Default criteria are 100 observations and unexpected conflict rate ≤ 1%.
Thresholds are explicit inputs, not hidden production defaults.

## Non-goals

This is an analysis/reporting model only. It does not authorize takeover, start
V3 execution, call HA/ESP, alter V2, change START/ACTIVE, or modify physical
ownership.
