# RD6018 Configuration Drift Report

Status: Phase 1 read-only inventory. Values are not changed by this report.

## Configuration sources

| Source | Examples | Role |
|---|---|---|
| YAML | `config/charge/*.yaml`, `config/safety/*.yaml`, `config/runtime/*.yaml`, `config/physical/*.yaml` | recipes, limits, safety and runtime defaults |
| Python constants | `charge_logic.py`, `edge_safety_lease.py`, `runtime_safety*.py`, `hass_api.py` | fallback limits, timers, entity behavior |
| Environment | `.env`, `config.py`, service environment | credentials, HA/Telegram endpoints and runtime switches |
| Manual config | `config/charge/manual.yaml` | operator-defined MAIN/MIX profile |
| Persisted state | session JSON, SQLite stores, `charging_history.log` | session, diagnostics, history and containment state |

## Known drift to resolve later

- Manual hold naming differs between `hold_seconds` and `hold_hours` contracts.
- `config/charge/limits.yaml` is broader than the production strategy envelope
  (YAML permits up to 18 V / 18 A while production strategy is narrower).
- `chemistry.yaml` includes `FLOODED`, while the production recipe set does not
  provide a matching complete recipe path.
- Native V3 charge programs and V2 production strategy have separate models.
- Relative paths for history and session state depend on the service working
  directory.
- Local and deployed manual configuration must be compared by explicit
  checksum; a deployed copy is not assumed identical to the repository copy.
- Multiple persisted state files describe session, manual, pause, ownership,
  adoption and containment state independently.

## Required Phase 2 action

Introduce a validated typed configuration bundle and preserve compatibility
readers during migration. No value should be changed until a source-of-truth
decision and parity tests exist.
