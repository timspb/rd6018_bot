# RD6018 long-running shadow acceptance model — EPIC H.1

Status: observation and analysis only. Ownership is unchanged: V2 remains the
decision/execution owner and V3 remains shadow-only.

## 1. Collector scope

`ShadowAcceptanceCollector` aggregates long-running evidence. It does not
consume authority, execute intents, alter V2/V3 state, write HA/ESP, renew a
lease or control physical output.

## 2. Metrics

### Decision metrics

- equal;
- expected difference;
- conflict;
- unknown.

Rates are calculated over all recorded decision comparisons.

### Execution metrics

- intent parity;
- safety gate parity;
- verification parity.

These are data comparisons from H.0, not proof that an adapter or physical
command ran.

### Runtime metrics

- V2 health samples and unhealthy observations;
- V3 health samples and unhealthy observations;
- restart events;
- worker failures.

### Safety metrics

- containment divergence;
- lease divergence;
- stale telemetry events.

Stale telemetry is measured for visibility; it is not automatically a
containment decision.

### Configuration metrics

- unresolved configuration usage;
- provenance conflicts.

## 3. Thresholds and bands

Default thresholds are explicit collector inputs:

- minimum decision observations: 100;
- maximum conflict rate: 1%;
- unknown rate: 0%;
- worker failures: 0;
- safety divergence: 0;
- configuration provenance conflicts: 0.

| Band | Condition |
|---|---|
| PASS | no blockers and minimum decision volume reached |
| WARNING | no hard blocker, but evidence volume is below minimum |
| BLOCKED | conflict/unknown threshold exceeded, parity failed, runtime unhealthy, safety divergence or configuration conflict |

No observations is `BLOCKED`, never an implicit pass.

## 4. Blockers

The collector blocks acceptance on:

- decision conflict/unknown rate;
- intent, safety-gate or verification parity failure;
- V2/V3 unhealthy samples or worker failures;
- containment or lease divergence;
- unresolved configuration use or provenance conflict.

The collector reports these conditions only. It does not roll back authority,
stop V2, start V3 execution or invoke containment.

## 5. Acceptance result

`LongRunAcceptance` returns all metric groups, per-group PASS/WARNING/BLOCKED
bands, blockers and `ownership_changed=False`. A passing result is evidence for
future review, not a takeover authorization.

Overall readiness requires sustained `PASS` with explicit operator review and
separate staged-takeover gates. This model alone cannot promote V3.

## Explicit non-goals

This phase does not change V2/V3 ownership, execute V3, enable START/ACTIVE,
write HA/ESP, alter lease semantics or perform physical output.

