# RD6018 V3 Migration Boundary Baseline

Status: `AUDITED`

Scope: post-WS135 read-only migration boundary inventory. This baseline does
not change V2 behavior, physical ownership, safety, lease semantics, or
deployment.

## Canonical execution flow

`V3 decision`
→ `Safety/approval boundary`
→ `ExecutionIntent`
→ `ExecutionPort`
→ `V2 Physical Owner`
→ `existing adapters`
→ `RD6018`
→ `readback/verification`

V3 creates decisions and intents only. V2 remains the sole production physical
owner. `ExecutionPort` is the V3-to-V2 boundary and does not calculate targets,
phases, or lifecycle state.

## Component ownership

| Component | Role | Status | Boundary decision |
|---|---|---|---|
| `application/charge_program/**` | program domain | keep | pure domain input |
| `application/charge_engine/**` | decision domain | keep | no physical access |
| `application/execution_intent/**` | intent contract | keep | no execution |
| `application/execution_port.py` | V3→V2 port | keep | sole V3 execution boundary |
| `application/manual_phase_lifecycle.py` | manual phase decision | keep | emits intent, no hardware |
| `runtime/v2_runtime.py` + V2 lifecycle/recovery | production execution owner | keep | sole write authority |
| `hass_api.py` / V2 safety guards | owner-controlled adapter/guard | keep | writes only under V2 |
| `runtime/output/**` | contracts, policy, simulation, verification | keep/quarantine | no hardware writes |
| `runtime/output/bridge/PhysicalBridgeExecutor` | former independent executor | quarantine | rejects all write entrypoints |
| `runtime/physical/connectors/**` | read/discovery adapters | keep | read-only in migration tree |
| `runtime/physical/transports/**` | read/health/readback transports | keep | no service/ESPHome writes |
| `physical_test_control*.py` | opt-in validation surface | leave, separately gated | not a V3 production path; delegates to installed V2 managers |
| `bot.py` / `v2_bootstrap.py` | V2 composition | keep | composes preserved V2 owner |
| `bot_legacy.py` | emergency preserved entrypoint | leave | rollback-only legacy path, not normal V3 path |

## Legacy execution paths

### Direct V2 writes — leave

The V2 runtime and its lifecycle/recovery helpers contain direct calls to the
V2 `HassClient` actuator surface. These are not migration bypasses: they are
the preserved owner implementation and retain existing safety/readback and
lease behavior. They must not be moved or duplicated as part of V3 migration.

### Former bridge executor — quarantine

`PhysicalBridgeExecutor` was an old write-capable entrypoint. After WS133 it
is import-compatible only: `execute`, verified-disable, controlled-transition,
and rollback reject before transport access. `verify` remains readback-only.
It must not be reactivated or instantiated as an owner.

### Physical connectors/transports — leave as read-only adapters

ESPHome/HA connector and transport classes retain discovery, health, snapshot,
and readback interfaces. Concrete write methods fail closed and contain no
service calls, ESPHome commands, or transport writes. Keep them only as
observation/verification surfaces until a future V2-owned adapter contract is
reviewed separately.

### Manual/UI paths — leave on the port

`manual_mode.py` routes start, stop, cooling/error shutdown, and phase target
updates through `ExecutionIntent`/`ExecutionPort`. No direct actuator call was
found in `manual_mode.py`, `bot.py`, or the checked UI/Telegram surfaces.

### Opt-in physical test control — separate review

`physical_test_control*.py` is imported by the V2 composition but is disabled
by default and exposes an explicitly opt-in Unix-socket validation surface.
It delegates to installed V2 managers/coordinators and is not a V3 decision
path. Leave unchanged; any future removal or migration requires a dedicated
controlled-test review.

## Forbidden paths

The following are forbidden for new code:

- V3 domain → HA/ESPHome/Modbus/RD;
- UI/manual input → hardware without `ExecutionIntent` and `ExecutionPort`;
- `PhysicalBridgeExecutor` → transport write;
- `runtime/physical` connector/transport → independent hardware ownership;
- synthetic identity, fake lifecycle events, or post-factum execution authority;
- a second execution owner.

## Migration rules

1. Preserve V2 as the only physical owner.
2. Add V3 behavior as domain decision, intent, safety/approval, or audit
   contracts only.
3. Route any future V3 physical request through `ExecutionPort` and the
   existing V2 owner.
4. Keep adapter code transport-specific but decision-free.
5. Treat legacy sessions and missing identity as `UNKNOWN`; never synthesize
   identity or lifecycle.
6. Review safety and lease semantics separately; do not widen their scope for
   convenience.

## Validation rules

- focused ownership and execution-boundary tests must pass;
- no direct actuator calls in V3/UI/manual surfaces;
- `PhysicalBridgeExecutor` must reject without transport calls;
- compileall must pass;
- `git diff --check` must pass for the change under review;
- no merge, deployment, restart, or hardware action is part of this audit.

## Audit result

The canonical ownership model is consistent after WS135. The only retained
write-capable implementation is the V2 owner family. The former independent
bridge and physical connector write surfaces are quarantined/read-only. No
additional code patch was required for this audit.
