# RD6018 configuration authority model (Phase 6.2)

Статус: contracts + architecture only. Runtime values and loading behavior are
not changed.

## Canonical authority

`application.configuration_authority.ConfigurationAuthority` is the future
registry contract. Each parameter must have exactly:

- canonical key;
- section and owner;
- Python value type;
- default;
- validator;
- human-readable description.

The contract does not load YAML, env, JSON, SQLite or secrets and is not wired
to production.

## Ownership model

| Section | Canonical owner | Parameters |
|---|---|---|
| Charge | Profile/Charge Domain | chemistry profiles, phases, V/I targets, holds, timers |
| Strategy | Strategy Domain | termination, Delta-I/Delta-V, Vmax, current-drop, confirmations |
| Safety | Safety Domain | OVP/OCP, temperature limits, freshness, watchdog and grace periods |
| Containment | Containment/SafeOutput owner | OFF policy, retries, confirmation and verification |
| Lease | Lease/edge safety owner | TTL, renewal interval and expiry behavior |
| Execution | Execution boundary/V2 owner | rollback, readback and verification windows |
| Transport | Infrastructure adapters | HA/ESP Direct endpoints, retry, timeout and priority |
| UI | UI adapter | presentation/layout/refresh preferences only |
| Persistence | Persistence adapter | retention, paths, schema and history policy |

## Current source inventory and migration status

| Current source | Future authority | Status |
|---|---|---|
| `config/charge/chemistry.yaml`, `recipes.yaml`, `manual.yaml` | Charge/Profile + Strategy | canonical data candidate; values unchanged |
| `config/charge/limits.yaml` | Safety/Charge | canonical limits candidate; compare with strategy envelope |
| `config/safety/safety_limits.yaml` | Safety | canonical safety candidate |
| `config/runtime/runtime.yaml` | Execution/Transport/Persistence | canonical runtime candidate |
| `config/physical/*.yaml` | Transport/Lease/Execution | adapter-owned candidate |
| Python constants in `charge_logic.py`, `runtime/v2_runtime.py` and safety modules | matching section | legacy drift; must not become a second authority |
| env/.env | secrets and deployment-only overrides | never a recipe/safety default source |
| persisted JSON/SQLite | session/history evidence | never configuration authority |

## Required parameter catalogue

The following keys are the minimum catalogue to register before runtime
consumption. Defaults are intentionally described as `current approved source`,
not copied into this contract during Phase 6.2.

| Key | Owner | Type | Validation |
|---|---|---|---|
| `charge.profile.*` | Profile Domain | profile DTO | recipe completeness and envelope |
| `charge.phase.*.voltage_v` | Charge Domain | positive float | within safety envelope |
| `charge.phase.*.current_a` | Charge Domain | positive float | <= configured current limit |
| `charge.phase.*.hold_seconds` | Strategy Domain | non-negative float | bounded duration |
| `strategy.delta_i_a` / `strategy.delta_v_v` | Strategy Domain | positive float | mode-specific evidence |
| `strategy.vmax_v` / `strategy.confirmations` | Strategy Domain | float/int | ordered and positive |
| `safety.ovp_max_v` / `safety.ocp_max_a` | Safety Domain | positive float | hardware envelope |
| `safety.temperature_critical_c` | Safety Domain | float | above warning threshold |
| `safety.telemetry_freshness_s` | Safety Domain | positive float | bounded timeout |
| `safety.watchdog_timeout_s` / `safety.grace_period_s` | Safety Domain | positive float | explicit safety review |
| `containment.off_policy` / `containment.retry` | Containment owner | enum/int | approved containment policy |
| `containment.confirmation_timeout_s` | Containment owner | positive float | verification window |
| `lease.ttl_s` / `lease.renewal_interval_s` | Lease owner | positive float | renewal < TTL |
| `execution.rollback_policy` | Execution boundary | enum | approved rollback |
| `execution.readback_timeout_s` | Execution owner | positive float | bounded window |
| `transport.*.timeout_s` / `retry` / `priority` | Adapter owner | typed transport DTO | adapter-specific validation |
| `ui.*`, `persistence.*` | respective adapters | typed adapter DTO | presentation/retention rules |

## Rules

1. No new magic number, safety threshold, timeout or duplicated default may be
   added outside the authority-owned configuration source.
2. Existing constants are legacy inventory until migrated and are not silently
   changed by this phase.
3. Secrets remain separate from configuration authority.
4. Runtime consumers must receive validated configuration, not read arbitrary
   files or env values directly.
5. A persisted state value cannot override a configuration authority value.

## Safety consumption contract

Safety consumers must declare the exact keys they need and receive validated
values. Missing/invalid safety configuration fails closed at the future
composition boundary; this document does not change current fail-closed paths.

## Explicit non-goals

No loader, default migration, YAML rewrite, env change, START/ACTIVE change,
HA/ESP connection, database change or physical execution is included.
