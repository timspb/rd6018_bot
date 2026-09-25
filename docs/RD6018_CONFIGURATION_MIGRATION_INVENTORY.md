# RD6018 configuration migration inventory

Статический инвентарь источников конфигурации для Phase 6.3. Документ не
является новым runtime-loader и не меняет ни одного действующего значения.

## Правила классификации

| Категория | Значение |
|---|---|
| `KEEP` | Для параметра найден один действующий источник в пределах своей ответственности. |
| `MERGE` | Есть несколько источников одного назначения без доказанного расхождения; перед миграцией нужен единый DTO/loader. |
| `CONFLICT` | Источники задают разные значения, единицы или семантику. Нельзя выбирать значение автоматически. |
| `REMOVE` | Источник является legacy-дубликатом после отдельного подтверждения эквивалентности и migration cutover. Сейчас не удалять. |

## Authority boundary

Кандидатами на владельцев являются доменные и инфраструктурные границы,
описанные в `RD6018_CONFIGURATION_AUTHORITY_MODEL.md`. В этом инвентаре
`Owner candidate` означает будущего владельца, а не текущий runtime-owner.
`config/**/*.yaml` — наиболее явный tracked configuration source; Python,
environment и persisted state пока остаются фактическими источниками,
которые требуют постепенной нормализации.

## Charge/profile inventory

| Parameter | Current sources | Current value(s) | Owner candidate | Conflict | Migration action | Category |
|---|---|---|---|---|---|---|
| Chemistry/profile names | `config/charge/chemistry.yaml:profiles` | AGM, EFB, CA_CA, FLOODED, CUSTOM | Profile Domain | `recipes.yaml` содержит только AGM/EFB/CA_CA | Сохранить полный registry; отдельно решить FLOODED recipe gap | `CONFLICT` |
| AGM recipe voltage/current | `config/charge/recipes.yaml:7,10` | 15.0 V / 8.0 A | Profile Domain | Legacy strategy/constants могут ограничивать иначе | Сверить с V1/V2 golden behavior, затем сделать recipe canonical | `MERGE` |
| EFB recipe voltage/current | `config/charge/recipes.yaml:14,17`; strategy docs | 14.8 V / 7.0 A; generic EFB upper policy 16.5 V | Profile + Safety Domain | Recipe target и outer safety envelope имеют разные роли; нельзя смешивать | Развести target/envelope типами | `MERGE` |
| CA_CA recipe voltage/current | `config/charge/recipes.yaml:21,24` | 14.7 V / 7.0 A | Profile Domain | Runtime legacy constants/limits также участвуют | Сопоставить с strategy envelope без изменения значения | `MERGE` |
| FLOODED recipe | `chemistry.yaml:profiles` | Profile объявлен, recipe отсутствует | Profile Domain | Неполное определение профиля | До миграции пометить недоступным для execution; не создавать значения | `CONFLICT` |
| Manual MAIN voltage/current/minimum/hold | `config/charge/manual.yaml:main` | 14.7 V / 5.0 A / 0.30 A / 0 h | Manual Profile/Strategy Domain | Persisted/manual UI state может иметь отдельные значения | Сделать schema источником, runtime parsing — отдельной задачей | `MERGE` |
| Manual MAIN confirmations | `config/charge/manual.yaml:main` | count 3; interval 60 s | Manual Strategy Domain | Legacy confirmation logic имеет hardcoded timing | Сверить семантику подтверждения и единицы | `CONFLICT` |
| Manual MIX voltage/current/delta/hold | `config/charge/manual.yaml:mix` | 16.5 V / 1.5 A / ΔV 0.03 V / ΔI 0.03 A / 2 h | Manual Strategy Domain | `charge_logic.py` также задаёт delta/hold constants | Связать только после parity review | `CONFLICT` |
| Automatic Mix delta-I | `charge_logic.py` constants `MIX_DELTA_I_RATIO`, `MIX_DELTA_I_MIN` | ratio 0.30; minimum 0.03 A | Strategy Domain | YAML manual ΔI 0.03 A имеет другую область применения | Развести automatic/manual strategy parameters | `MERGE` |
| Automatic Mix delta-V | `charge_logic.py:DELTA_V_EXIT` | 0.03 V | Strategy Domain | Может пересекаться с manual `delta_voltage_v` | Развести automatic/manual names and owners | `MERGE` |
| Mix finish hold | `charge_logic.py:MIX_DONE_TIMER`; `rd_live_adoption.py:MIX_FINISH_HOLD_S`; docs strategy | 2 h / 7200 s | Strategy Domain | Same semantic value in multiple code paths and units | Canonical duration DTO in seconds, UI conversion at edge | `MERGE` |
| Mix maximum age | `charge_logic.py` | CA/Ca 20 h; EFB 20 h; AGM 10 h | Strategy Domain | Current docs/decision policy says EFB 24 h | Resolve explicitly against accepted strategy before migration | `CONFLICT` |
| First-stage holds | `charge_logic.py` | AGM 2 h; generic 3 h | Profile/Strategy Domain | Profile-specific and generic constants overlap | Map by profile and remove fallback only after parity tests | `CONFLICT` |
| Session max age | `charge_logic.py:SESSION_MAX_AGE` | 24 h | Session Domain | Persisted session/recovery may apply separate age checks | Make one session recovery policy | `MERGE` |

## Safety and limits

| Parameter | Current sources | Current value(s) | Owner candidate | Conflict | Migration action | Category |
|---|---|---|---|---|---|---|
| Charge voltage/current domain limits | `config/charge/limits.yaml`; `config/safety/safety_limits.yaml` | 18 V / 18 A in both | Safety Domain | Duplicate same-purpose sources | Keep one safety authority; retain source provenance during migration | `MERGE` |
| RD physical limits | `config/physical/rd6018.yaml` | 60 V / 18 A / 1080 W | Transport/Physical capability boundary | 60 V capability is not a charge-domain entitlement; 18 A overlaps safety | Type as hardware capability, never substitute for safety limit | `MERGE` |
| Device max temperature | charge/safety YAML | 55 °C | Safety Domain | Legacy warning/pause/critical thresholds are 35/40/45 °C | Keep 55 as outer device limit; model staged runtime thresholds separately | `MERGE` |
| Temperature warning/pause/critical | `charge_logic.py` | 35 / 40 / 45 °C | Safety Domain | Not represented in YAML | Inventory into typed staged policy; do not infer new values | `CONFLICT` |
| Temperature rise rule | `charge_logic.py` | 2 °C over 300 s | Safety Domain | No YAML counterpart | Add explicit candidate fields after behavior review | `MERGE` |
| Temperature compensation | `charge_logic.py` | ref 25 °C; max ΔV 0.60 V; slopes 0.018/0.016/0.018 V/°C; update 300 s; ΔT 0.5 °C | Strategy/Safety Domain | Hardcoded and profile-specific | Extract as typed profile strategy parameters | `MERGE` |
| OVP/OCP offsets | `charge_logic.py` | 0.1 V / 0.1 A; desulf OCP margin 1.0 A | Safety/Execution Domain | `bench.yaml` has 0.50 V / 0.10 A margins | Different context and units/semantics | Name by context before migration | `CONFLICT` |
| Maximum stage current | `charge_logic.py` / runtime safety | 12.0 A | Safety Domain | YAML max current is 18 A | Preserve distinction stage vs outer limit | `MERGE` |
| Input voltage minimum | Python legacy/runtime safety | source constant `MIN_INPUT_VOLTAGE` | Safety Domain | No tracked canonical YAML field located | Add inventory entry and source test before migration | `MERGE` |

## Telemetry, verification and containment

| Parameter | Current sources | Current value(s) | Owner candidate | Conflict | Migration action | Category |
|---|---|---|---|---|---|---|
| Telemetry poll interval | `config/runtime/runtime.yaml` | 5 s | Telemetry Provider | Other runtime loops poll at 5/30/0.5 s depending on purpose | Separate telemetry, observer and readback polling | `MERGE` |
| Cross-source snapshot tolerances | `config/runtime/runtime.yaml` | V 0.06; I 0.06; timestamp 10 s | Telemetry Authority | No equivalent canonical source elsewhere found | Keep YAML and expose typed telemetry config | `KEEP` |
| Setpoint verification tolerances | `config/runtime/runtime.yaml` | V 0.01; I 0.05; protection 0.05 | Execution/Verification | Legacy readback paths use different windows | Separate tolerance from timeout and map each path | `MERGE` |
| Physical readback timeout/poll | runtime YAML; `rd6018_telemetry.py`; `runtime/output/bridge/executor.py` | 15 s / 0.5 s; current proof 10 s; executor default 5 s | Execution Boundary | 15/10/5 s timeout drift | Inventory each operation and choose owner only after parity test | `CONFLICT` |
| OFF confirmation poll | `runtime_safety.py` | 0.50 s | SafeOutput/Containment owner | Other output bridge polling defaults exist | Canonicalize after containment mapping | `MERGE` |
| OFF/orphan grace | `runtime_safety.py` | 45 s | Containment owner | No YAML counterpart located | Add explicit policy field, retain current behavior until cutover | `MERGE` |
| Watchdog timeout | `charge_logic.py` | 300 s | Runtime Safety | `runtime/v2_runtime.py:SOFT_WATCHDOG_TIMEOUT` is 180 s | Resolve owner and precedence; no automatic selection | `CONFLICT` |
| High-voltage fast timeout | `charge_logic.py` | 60 s above 15 V | Runtime Safety | No YAML counterpart | Extract with explicit scope | `MERGE` |
| Transition settle timeout/poll | `runtime_safety_strict.py` | 6.5 s / 0.20 s | Verification/Containment | Other readback windows overlap | Keep operation-specific field | `MERGE` |
| Transition settle margins | `runtime_safety_strict.py` | V 0.05 / I 0.05 | Verification | Runtime YAML tolerances differ | Preserve semantic names; do not merge by numeric equality | `MERGE` |

## Lease and transport

| Parameter | Current sources | Current value(s) | Owner candidate | Conflict | Migration action | Category |
|---|---|---|---|---|---|---|
| ESPHome lease TTL | edge/ESPHome contract references and runtime docs | 900 s (15 min) | Lease Authority / ESP dead-man | Must remain aligned with firmware contract | Keep as contract value; verify against exact firmware separately | `KEEP` |
| Lease renewal interval | edge/runtime lease modules and environment-controlled deployment | runtime-derived/contract-specific; no single tracked YAML value found | Lease Authority | No canonical tracked value | Inventory exact deployment source before migration; do not invent default | `CONFLICT` |
| Lease entity names | env variables and edge modules | `RD6018_EDGE_*_ENTITY` family | Lease Adapter | Deployment-specific names are not domain config | Keep in deployment/secret boundary; redact values | `KEEP` |
| Transport selection | `config/physical/transports.yaml`, connectors YAML | default `ha102`; priorities HA 10, ESP 20; connector default `esp_direct` with priorities 20/10 | Transport Authority | Connector and transport registries disagree on default/priority model | Merge into one transport registry with explicit selection semantics | `CONFLICT` |
| HA endpoint | `config/physical/ha102.yaml` | 192.168.1.102:8123, TLS false | HA Adapter | deployment endpoint, not domain setting | Keep adapter config; secret only by `HA_TOKEN` | `KEEP` |
| ESP endpoint | `config/physical/esp128.yaml` | 192.168.1.28:6053, encrypted true | ESP Adapter | deployment endpoint, not domain setting | Keep adapter config; key only by `ESPHOME_API_KEY` | `KEEP` |
| Transport retry/timeout/polling | YAML lacks unified fields; Python/adapters contain defaults | `aiohttp` total 15 s; several adapter polls 0.25/0.5/5/30 s | Transport Authority | Multiple operation-specific literals | Inventory by operation; add typed adapter policy without changing runtime | `CONFLICT` |

## Environment, secrets and persisted state

| Parameter | Current sources | Current value(s) | Owner candidate | Conflict | Migration action | Category |
|---|---|---|---|---|---|---|
| HA/ESP credentials | `.env` when deployed; `token_env`/`key_env` in YAML | Names `HA_TOKEN`, `ESPHOME_API_KEY`; values intentionally not inventoried | Deployment/Secret boundary | Secret values must not enter Configuration Authority | Keep secret references only; never persist/print secret values | `KEEP` |
| Physical execution and manual arm | `config/runtime/runtime.yaml` | false / true | Activation/Execution policy | Separate activation gates also exist in application policy | Keep config as one input; reconcile policy ownership before wiring | `MERGE` |
| Charge session | `charge_session.json` | persisted runtime/session document | Session Domain | legacy controller writer and recovery readers | Treat as legacy persistence; map owner before migration | `REMOVE` |
| Manual session | `manual_session_v2.json` | persisted V2 manual state | Session Domain | separate manual manager and legacy readers | Keep during staged migration, then remove duplicate readers | `MERGE` |
| Manual OFF state | `manual_off_state.json` | persisted containment/condition overlay | Containment/Safety owner | independent side-channel can diverge from session | Keep until containment cutover; never silently merge semantics | `CONFLICT` |
| Operator pause | `operator_pause_state.json` | persisted UI/operator intent | Session/Application boundary | UI state can outlive runtime session | Reclassify as intent, not FSM state | `MERGE` |
| RD control mode | `rd_control_mode_v2.json` | durable PB_MANAGED/HANDS_OFF mode | Ownership/Lease boundary | can outlive process/session state | Keep as outer ownership state; reconcile on restart | `KEEP` |
| SQLite history/state | `rd6018.db` and recovery stores | tables/history/recovery records | Persistence adapter | runtime-relative paths and multiple readers | Define persistence contract; no config values should be read implicitly | `MERGE` |

## Hardcoded literal disposition

The following families are confirmed runtime literals and are not silently
promoted to configuration by this report:

- `charge_logic.py`: finish deltas, holds, temperature thresholds,
  compensation, session age and profile Mix budgets;
- `runtime/v2_runtime.py`: soft watchdog 180 s, HTTP timeout 15 s and
  stabilization delay 0.35 s;
- `runtime_safety.py` / `runtime_safety_strict.py`: OFF/settle windows and
  verification margins;
- adoption and physical-test helpers: observer, proof, step and polling
  windows.

Migration action for each is: preserve behavior, add a named inventory entry,
write a parity test, then move one owner at a time. A literal is not `REMOVE`
until no production path reads it.

## Summary and order of migration

1. `KEEP`: telemetry comparison tolerances, explicit transport endpoints,
   secret references, ESPHome lease contract, outer ownership state.
2. `MERGE`: duplicate YAML limits, manual/session persistence readers,
   verification and polling parameters, activation inputs.
3. `CONFLICT`: EFB Mix budget, watchdogs, readback timeouts, transport default,
   staged temperature policy, OVP/OCP margins, incomplete FLOODED profile and
   lease renewal source.
4. `REMOVE`: only legacy duplicate readers after an ownership cutover; no file
   or runtime literal is removed in Phase 6.3.

No runtime behavior, START/ACTIVE policy, HA/ESP integration, physical call or
configuration value was changed by this inventory.
