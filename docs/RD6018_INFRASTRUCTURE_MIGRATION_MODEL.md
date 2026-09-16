# RD6018 V3 infrastructure migration model — EPIC C

Status: shadow/contract checkpoint. V2 remains the control, lease and physical
owner. This model normalizes HA/ESP/RD boundaries without connecting clients,
changing fail-safe behavior or issuing commands.

## Scope and authority

```text
HA telemetry adapter ----+
                         +--> Telemetry arbitration --> V3 shadow view
ESP Direct adapter ------+

readback observation ----> comparison/evidence only
control intent ----------> existing Execution Boundary (deferred only)
lease observation -------> V3 evidence; V2/edge authority unchanged
```

Infrastructure adapters provide data and transport-shaped results. They do not
own domain decisions, safety decisions, containment, session state or physical
execution. `ConfigurationAuthority` supplies adapter timeouts, freshness and
verification references; adapters do not create hidden defaults.

## 1. Telemetry infrastructure

The existing `HATelemetryAdapter` and `ESPDirectTelemetryAdapter` implement the
read-only `TelemetryProvider` boundary. They normalize source reports into
`TelemetrySnapshot` with:

- voltage, current, power, temperature and output state;
- source timestamp and receive/freshness age;
- source (`ESP_DIRECT`, `HA`, `LAST_KNOWN`, `UNKNOWN`);
- confidence and freshness evidence.

Arbitration is deterministic:

```text
ESP Direct fresh
      |
      v
HA fresh
      |
      v
last known (stale, reduced confidence)
      |
      v
unknown
```

The selected snapshot and both source reports remain available for provenance
and comparison. Arbitration does not call safety, containment, lease or
control code.

| Area | V2 behavior | V3 model | Comparison/divergence |
|---|---|---|---|
| source read | current production source/runtime surface supplies live data | injected HA/ESP Direct read-only adapters | expected boundary improvement |
| priority | V2 consumers may use source-specific paths | ESP fresh > HA fresh > last-known > unknown | expected; source disagreement is evidence |
| freshness | runtime policy determines whether data is usable | explicit age/freshness/confidence fields | expected; threshold remains configuration-owned |
| provenance | source can be implicit in legacy consumers | source is mandatory in snapshot | architectural improvement |
| stale data | existing V2 safety behavior remains authoritative | V3 retains stale evidence but cannot authorize control | expected boundary |

## 2. Canonical readback contract

`application.infrastructure_contracts.ReadbackObservation` is the pure,
immutable comparison contract:

| Field | Meaning |
|---|---|
| `requested_value` | value requested by an intent or existing V2 transaction |
| `observed_value` | value reported by a read-only source |
| `timestamp` | observation time, not command creation time |
| `source` | HA, ESP Direct, RD or another explicit adapter label |
| `confidence` | normalized evidence quality in `[0, 1]` |

This contract records an observation; it does not verify hardware, send a
command, or mark an actuator action successful. The existing V2 readback and
OFF verification semantics remain unchanged.

| Area | V2 behavior | V3 model | Comparison/divergence |
|---|---|---|---|
| requested vs observed | transaction-specific readback structures | common immutable observation record | architectural improvement |
| source/time | source and capture details vary by path | mandatory source and timestamp | expected normalization |
| confidence | inferred by the owning transaction | explicit evidence quality field | expected; no automatic safety decision |
| mismatch | V2 owner applies existing abort/containment policy | V3 records mismatch for comparison only | V2 behavior retained |

## 3. Control model — intent only

The infrastructure layer recognizes only the transport-neutral operation
vocabulary already defined by `ActuatorIntent`:

- `OUTPUT_ON`;
- `OUTPUT_OFF`;
- `SET_VOLTAGE`;
- `SET_CURRENT`.

An intent carries owner, trigger, safety context, rollback and verification
expectation. EPIC C may validate/map an intent or produce a deferred shadow
result, but it must not call `ControlProvider`, `RDTransport`, HA, ESPHome or
any physical writer. `ExecutionDispatcher` and V2 remain unchanged.

## 4. Lease model

Lease authority is separate from telemetry authority and control intent:

| Lease element | Current owner | V3 shadow representation | Allowed action |
|---|---|---|---|
| lease authority | V2 edge/ESPHome contract | explicit owner/source observation | observe only |
| renewal intent | V2 runtime/edge lease owner | traceable candidate intent and comparison record | never renew |
| expiry observation | ESPHome/local dead-man plus V2 surface | observation with generation/state/age provenance | never clear or alter |
| containment relation | existing V2 safety/edge owner | relation in diagnostics/evidence | never replace |

The accepted lease contract remains external to V3 infrastructure migration:
TTL, renewal cadence, generation acknowledgement, local dead-man and
verified-OFF semantics are not changed here. Telemetry freshness never implies
lease renewal, and lease expiry is not rewritten as a generic telemetry error.

## 5. Transport failure taxonomy

Failure classes are deliberately distinct:

| Failure | V2 behavior | V3 model | Comparison/divergence explanation |
|---|---|---|---|
| HA unavailable | existing V2/runtime policy applies | `HA_UNAVAILABLE` source failure evidence | expected separation; no automatic V3 shutdown |
| ESP unavailable | existing V2/edge policy applies | `ESP_UNAVAILABLE` source failure evidence | expected separation; no fallback ownership transfer |
| RD unavailable | current transaction/transport owner handles it | `RD_UNAVAILABLE` transport evidence | V2 policy remains authoritative |
| stale telemetry | V2 safety/runtime policy decides current action | stale snapshot with age/confidence and source | unresolved only if source policy differs; do not guess |
| command unconfirmed | V2 readback/containment path handles uncertainty | `COMMAND_UNCONFIRMED` observation and comparison event | V2 verification semantics retained |

Each event carries trace/correlation, source, timestamp, failure class and
available snapshot/readback evidence. Failure classification itself does not
issue OFF, renew a lease, retry a command or change ownership.

## 6. Acceptance criteria

EPIC C shadow acceptance requires:

1. HA and ESP Direct adapters satisfy the same read-only telemetry contract;
2. arbitration is tested for fresh, stale, missing and conflicting sources;
3. readback observations have requested/observed value, timestamp, source and
   confidence;
4. control operations are represented only as typed intents;
5. lease authority, renewal, expiry and containment are separately classified;
6. all five transport failure classes produce comparison evidence;
7. no hidden transport owner or adapter-side safety decision exists;
8. static tests prove no HA/ESP writes, physical calls or execution ownership
   change;
9. V2 runtime, START, ACTIVE, ExecutionDispatcher and physical output tests
   remain unchanged and pass.

Rollback is observational: stop consuming V3 snapshots/evidence and return
diagnostics to the existing V2 view. No adapter state is restored into V2
control, lease, session or physical state.

## Explicit non-goals

This EPIC does not connect HA or ESP clients, issue control commands, renew or
expire a lease, alter stale/fail-closed policy, change the ExecutionDispatcher,
replace V2 control ownership, enable START/ACTIVE or perform physical output.

