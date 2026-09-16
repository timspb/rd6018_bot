# RD6018 Canonical Configuration Model

Status: Phase 2 preparation. This document defines ownership; it does not
change any configuration values or loaders.

## Canonical source proposal

| Domain | Canonical source | Current readers/fallbacks | Migration rule |
|---|---|---|---|
| Chemistry | `config/charge/chemistry.yaml` | `pb_domain.py`, legacy adapters | YAML identity is canonical; Python enums are adapters |
| Recipes | `config/charge/recipes.yaml` | `recipe_engine.py`, V2 strategy | recipe identity and phase data must come from one validated model |
| Physical limits | `config/charge/limits.yaml` | `charge_logic.py`, `config.py` | YAML is source; production envelope remains an explicit policy overlay until parity is proven |
| Safety limits | `config/safety/safety_limits.yaml` | `runtime_safety*.py`, `safe_output.py` | safety YAML is canonical; no silent fallback widening |
| Manual settings | `config/charge/manual.yaml` | `runtime.charge.profiles.manual`, `manual_mode.py` | one typed schema; normalize hold unit before reading |
| Runtime settings | `config/runtime/runtime.yaml` | runtime loaders and service environment | YAML/runtime schema is canonical; deployment env only supplies secrets/endpoint overrides |
| Secrets/endpoints | `.env` / service environment | `config.py`, `hass_api.py` | secrets remain environment-owned and are never persisted into config models |
| Session state | explicit state owner per state map | JSON/SQLite stores | persisted state is not configuration |

## Known normalization gaps

### `hold_seconds` versus `hold_hours`

The manual contract is represented with both second- and hour-oriented names.
Phase 2 must introduce one typed internal unit (seconds is recommended for
runtime arithmetic) while preserving an explicit hour-facing config field and
conversion validation. No value conversion is applied in this phase.

### `limits.yaml` versus production strategy envelope

The YAML envelope is broader than the currently accepted production strategy
envelope. These are distinct concepts and must not be merged by taking the
larger value:

- configured physical ceiling;
- chemistry/recipe target;
- production strategy authorization ceiling.

The narrower authorized strategy remains effective until a reviewed parity
decision changes it.

### `FLOODED` recipe gap

Chemistry identity and recipe availability are separate. `FLOODED` appears in
chemistry configuration, but the production recipe set does not currently
provide the same complete recipe path as AGM, EFB and Ca/Ca. A canonical model
must represent “known chemistry, no executable recipe” explicitly and deny
selection rather than inventing a recipe.

### V2/V3 charge program contracts

V2 owns production execution and its accepted Main/Mix and delta semantics. V3
programs are data/decision contracts and remain shadow-only. In particular,
the V2 CC completion rule is voltage-based (`Vmax` to confirmed `ΔV`); any V3
program that models this differently is a parity issue, not a new authority.

## Proposed typed bundle

```text
ConfigurationBundle
  chemistry_catalog
  recipe_catalog
  physical_limits
  safety_limits
  manual_profile_schema
  runtime_settings
```

The bundle should be immutable after validation and carry source/version
metadata. Existing readers should be adapted incrementally; no writer or
actuator should consume the bundle until Phase 2 parity tests pass.

