# RD6018 V3 dual runtime model — EPIC F

Status: shadow/coexistence preparation. V2 remains the production execution
owner. V3 may run beside it only as a non-authoritative shadow runtime.

## 1. Runtime ownership

| Runtime | Role | Execution authority | Lifecycle owner |
|---|---|---:|---|
| V2 | production runtime | yes | V2 `bot.py`/existing bootstrap |
| V3 | shadow runtime | no | `V3RuntimeComposition` shell |

`DualRuntimeCoordinator` observes a supplied V2 health snapshot and starts or
stops only the V3 shell. It never starts, stops, restarts or otherwise mutates
V2.

## 2. Lifecycle isolation

Required startup order:

```text
V2 startup and health confirmation
              |
              v
V3 dependency initialization
              |
              v
V3 shadow workers
```

V2 must already be alive, healthy and the positive execution owner before V3
starts. Shutdown is isolated:

```text
stop V3 workers -> stop V3 shell
V2 lifecycle remains under V2 owner
```

Worker cancellation belongs to V3. A V3 worker failure cannot stop V2,
renew a lease, trigger a physical shutdown or create a second safety owner.

## 3. Resource isolation

| Resource | V2 namespace/owner | V3 namespace/owner | Rule |
|---|---|---|---|
| persistence | V2 runtime stores | `v3-shadow` candidate/in-memory boundary | never share restore namespace |
| diagnostics | V2 production events | `v3-shadow-diagnostics` | correlation remains distinguishable |
| telemetry | V2 production consumers | V3 read-only adapters/subscriptions | V3 does not publish control telemetry |
| configuration | V2 effective runtime view | V3 canonical/shadow view | V3 cannot mutate V2 values |
| UI | V2 production handlers | optional V3 shadow adapter | no duplicate production Telegram handler |

The namespaces are validated before V3 startup. Shadow evidence is analytical
and cannot become V2 restore state.

## 4. Duplicate ownership risks

The coexistence gate must prove absence of:

- duplicate control/execution owners;
- duplicate lease renewal or expiry handling;
- duplicate HA writes;
- duplicate ESP writes;
- duplicate production UI handlers;
- shared persistence/diagnostics namespaces that hide attribution.

V3 has `no_execution_authority=True`; its telemetry, diagnostics and shadow
workers are observational. V2 remains the sole control, lease and physical
owner throughout EPIC F.

## 5. Health model

`RuntimeHealthSnapshot` reports for both runtimes:

- `alive`;
- `healthy`;
- `execution_owner`;
- `shadow_healthy`;
- `no_execution_authority`;
- lifecycle and resource namespaces.

Expected snapshots:

| Field | V2 | V3 |
|---|---:|---:|
| alive | true when V2 process is alive | true when shell is started |
| healthy | V2 health contract | dependencies/diagnostics/shadow workers healthy |
| execution owner | true | false |
| shadow healthy | optional/false | true while shadow shell is healthy |
| no execution authority | false | true |

`DualRuntimeHealth.isolated` is false if an execution owner or resource
namespace conflict is detected.

## 6. Rollback and failure scenarios

| Scenario | Required action | Ownership result |
|---|---|---|
| V3 crash | cancel/record V3; leave V2 untouched | V2 remains sole owner |
| V2 crash | do not promote V3; preserve shadow-only state | no runtime owns V3 execution |
| partial startup | stop/cancel V3 partial workers; report unhealthy | V2 remains owner if alive |
| restart | restart V3 only after fresh V2 health confirmation | no implicit session/control resume |
| namespace conflict | reject V3 startup | no coexistence |
| ownership conflict | reject health acceptance and cutover | V2 remains authoritative |

Rollback is non-physical and does not send HA/ESP/RD commands. V3 shadow
records remain evidence only.

## 7. Acceptance criteria

EPIC F shadow acceptance requires:

1. V2 health is checked before V3 startup;
2. V3 startup/shutdown does not call V2 lifecycle methods;
3. V3 workers are owned and cancelled by V3;
4. persistence and diagnostics namespaces are distinct;
5. V3 reports no execution authority;
6. no duplicate control, lease renewal, HA/ESP write or UI handler exists;
7. V3 crash, V2 crash, partial startup and restart remain non-promoting;
8. V2 bot, START, ACTIVE, HA/ESP control, lease and physical ownership are
   unchanged.

Overall readiness: `DUAL_RUNTIME_SHADOW_READY`, `NOT_READY_FOR_CUTOVER`.

## Explicit non-goals

This EPIC does not replace V2, enable V3 execution, start a second Telegram
handler, renew a lease, write HA/ESP, alter START/ACTIVE or perform physical
output.

