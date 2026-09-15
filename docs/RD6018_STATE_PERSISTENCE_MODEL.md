# RD6018 state and persistence ownership model (Phase 5.4)

Статус: analysis + contracts only. Это не меняет DB, writers, FSM, runtime,
START, ACTIVE или physical execution.

## Ownership rules

1. У каждого состояния ровно один authoritative owner.
2. Reader не становится owner только потому, что отображает состояние.
3. Persistence хранит данные, но не получает права управления actuator.
4. После restart никакой persisted value не может сама включить output или
   возобновить заряд без свежей telemetry, safety/preflight и требуемой
   operator authorization.
5. Derived state пересчитывается из authoritative inputs; его нельзя принимать
   за источник истины.

## State inventory

| State | Owner | Lifetime | Persistence | Recovery after restart |
|---|---|---|---|---|
| FSM/phase state | Charge Domain | session | may persist as continuity snapshot | validate against fresh measurements; invalidate on mismatch; no actuator authority |
| charge session identity/lifecycle | Session Domain | session | must persist while active, subject to bounded retention | restore metadata only; require fresh preflight and operator action before resume |
| active profile/chemistry | Profile Domain | session | may persist as selected profile; canonical recipe remains config | restore only if profile and battery identity still match; otherwise invalidate |
| active targets | Strategy/Profile Domain | session | may persist as audit/preview; must not be sole execution authority | recalculate from validated recipe and fresh state |
| telemetry history | Telemetry/History subsystem | durable | may persist for diagnostics/history | read as historical only; never restore live state from it |
| domain safety state | Safety Domain | transient/session | may persist as evidence/audit, not as authority | recalculate from current measurements, limits and phase |
| infrastructure safety state | Runtime safety owner | transient/session | may persist incident record only | re-establish from live HA/ESP/lease/watchdog state |
| containment state | SafeOutput/physical safety owner | transient until verified | may persist observation/audit; physical state must not be inferred from file | verify actual OFF/containment; unresolved state remains conservative and requires operator action |
| actuator state/setpoints | V2 physical execution owner | transient/derived | must not persist as executable state | read fresh hardware state/readback; never replay stale commands |
| UI/dashboard state | UI Module | transient or presentation preference | may persist layout/filter preferences; must not persist runtime authority | rebuild from current snapshot; stale controls are invalidated |

## Existing storage mapping

The existing files/stores remain unchanged in this phase:

- `charge_session.json`: legacy charge/session continuity; advisory until
  validated by current owner.
- `manual_session_v2.json`: V2 manual session continuity; not physical
  authority.
- `manual_off_state.json`: manual containment evidence; requires fresh OFF
  verification.
- `operator_pause_state.json`: operator/UI pause intent; not FSM ownership.
- `rd_control_mode_v2.json`: outer ownership mode; must be reconciled with
  current runtime and hardware state.
- SQLite/history/log stores: historical evidence and diagnostics, not live
  domain or actuator authority.

Each store must eventually have one writer and an explicit authoritative,
advisory or historical reader classification. That normalization is future work.

## Restart matrix

| Category | Action | Operator action |
|---|---|---|
| Domain/session metadata | bounded restore candidate | reauthorize before physical resume |
| Profile/targets | recalculate/validate | confirm if identity or recipe changed |
| Telemetry history | retain for display/audit | none; never treat as live |
| Safety/containment | invalidate/recalculate and verify | required when OFF is unknown or lease is ambiguous |
| Actuator state | invalidate and read hardware | required before any new command |
| UI state | rebuild/invalidate stale actions | refresh panel |

## Forbidden ownership

- UI does not own FSM, session, profile, target, safety, containment or
  actuator state.
- HA/ESP transport does not own domain state; it only reports/executes through
  an approved boundary.
- Persistence files do not own runtime state and cannot authorize START/ACTIVE.
- Telemetry history does not own current telemetry authority.

## Open decisions

- canonical session restore/reauthorization policy after process restart;
- exact retention and schema migration for legacy JSON/SQLite stores;
- reconciliation order between `rd_control_mode_v2.json`, lease state and
  physical readback;
- single future writer for manual pause/off state.

No decision here authorizes runtime wiring or changes current recovery behavior.
