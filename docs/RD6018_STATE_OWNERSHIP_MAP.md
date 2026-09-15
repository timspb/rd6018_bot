# RD6018 State Ownership Map

Status: Phase 2 read-only inventory. No persistence behavior is changed.

| State | Owner | Writer | Reader | Lifecycle | Risk |
|---|---|---|---|---|---|
| `charge_session.json` | legacy charge controller | `charge_logic.py` | startup/recovery and charge logic | active session/restart | relative path and stale restore authority |
| `manual_session_v2.json` | `ProductionManualSessionManager` / `ManualSessionManager` | `manual_mode.py`, `manual_runtime_v2.py` | manual startup, dashboard, recovery | manual session | duplicate legacy/manual readers |
| `manual_off_state.json` | manual containment/recovery | manual runtime paths | manual restart/containment | manual OFF/recovery | OFF semantics can diverge from session state |
| `operator_pause_state.json` | operator pause layer | operator UI/runtime | dashboard and resume logic | pause/resume | pause state independent of session state |
| `rd_control_mode_v2.json` | `RdControlModeManager` | `rd_control_mode.py` | ownership guards/startup recovery | durable PB/HANDS_OFF mode | ownership can outlive process state |
| recovery SQLite stores | recovery/diagnostic subsystem | `recovery_trace_store.py`, `database.py`, `battery_registry.py` | diagnostics, replay, controller evidence | retained history | multiple schemas and retention rules |
| `rd6018.db` sensor/history tables | database subsystem | `database.py` | graphs, diagnostics, history | rolling retention | runtime-relative DB path |
| `charging_history.log` | charging event logger | `charging_log.py` and legacy paths | Telegram logs/operator UI | append/retention policy | Manual and V3 journal events may be absent |

## Required Phase 2 ownership rules

1. A persisted file has one writer owner.
2. Readers must declare whether data is authoritative, advisory or historical.
3. Restart recovery must not grant actuator authority from a stale file alone.
4. Session state, ownership state, safety state and telemetry history must remain
   separate contracts.
5. Relative paths must be replaced by an explicit runtime state directory only
   in a later, behavior-reviewed change.

