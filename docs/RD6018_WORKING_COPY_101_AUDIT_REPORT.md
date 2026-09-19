# RD6018 Working Copy 101 Audit

Дата аудита: 2026-09-15  
Режим: read-only; node 101; без restart, checkout, pull, записей, команд управления и физических действий.

## Итог

Статус: **BLOCKED** для вывода рабочей копии 101 как ожидаемой V3-архитектуры.

Причина: V3 charge/program modules в рабочей копии присутствуют, но штатный production service запускает V2 entrypoint и V2 controller. Кроме того, фактическая charge-program authority распределена между legacy FSM/constants, recipe envelope, battery registry и Manual profile; единый V3 resolver не является production owner.

## 1. Repository state

Наблюдение на node 101:

- service: `rd6018-bot.service`, `active (running)`;
- working directory: `/root/rd6018_bot`;
- interpreter: `/opt/rd6018-bot-venv/bin/python`;
- entrypoint: `/root/rd6018_bot/bot.py`;
- HEAD: `10af870f7d3ac69ed948ca023318f61827aefa33`;
- branch: detached HEAD;
- working tree: modified `config/charge/manual.yaml`; изменений в runtime-коде по `git status` не обнаружено;
- service unit описывает deployment как `RD6018 Telegram Bot V3 dry-run boundary`, но это только label: фактический entrypoint остаётся V2.

### V3-модули, реально присутствующие

В tree есть `runtime/charge`, `runtime/config`, `runtime/diagnostics`, `runtime/telemetry`, `runtime/output`, `runtime/physical`, `runtime/safety`, `runtime/replay`, `runtime/ui`, а также `application` и `runtime/app.py`.

В `runtime/charge` присутствуют отдельные `ChargeProgram`, `ProgramRegistry`, `ProfileRegistry`, chemistry/profile/strategy/program modules и shadow comparison. Это подтверждает наличие V3 skeleton, но не его production wiring.

### Что реально запускается

`bot.py` импортирует `runtime.v2_lifecycle`, `charge_logic.ChargeController`, `charge_controller_v2.ChargeControllerV2`, `HassClient` и legacy/V2 safety/UI installers. `runtime/app.py` является пассивным V3 контейнером и не используется как production composition root текущего service.

## 2. Charge-program architecture

### Фактическая цепочка production

```text
Telegram / manual input / battery callback
        |
        +--> profile + intent + capacity + battery_id
        |
        +--> ChargeControllerV2 / ProductionChargeControllerV2
        |        |
        |        +--> legacy FSM and charge_logic constants
        |        +--> recipe envelope bounds
        |        +--> SafeOutputCoordinator / runtime safety
        |
        +--> ProductionManualSessionManager
                 |
                 +--> manual.yaml profile and persisted manual session
                 +--> manual FSM/timers/delta/hold
```

### FOUND: modes and program sources

| Mode/program | Selection source | Current owner | Inputs | Result |
|---|---|---|---|---|
| AUTO Normal | V2 Telegram quick profile or selected battery intent | `ProductionChargeControllerV2` / `ChargeControllerV2` | profile, Ah, battery identity, intent, condition, telemetry | legacy Main → evidence/Desulfation/Mix → Safe Wait/Done |
| AUTO Recovery / Conditioning | operator intent plus V2 recovery gates | V2 controller + recovery/first-stage evidence | profile, Ah, condition, evidence | bounded recovery/main/HV path; not an independent V3 program |
| AUTO Diagnostic | V2 diagnostic intent/guardrails | diagnostic/V2 controller safety boundary | profile, telemetry, diagnostic gates | no-new-automatic-HV authority / diagnostic path |
| AUTO Mix | V2 phase transition after Main/Desulf evidence | V2 controller/FSM | chemistry, Ah, Vmax/ΔV or Imin/ΔI evidence, timers | Mix target and finish hold/timeout |
| MANUAL staged | `MANUAL` text command and saved profile | `ProductionManualSessionManager` | `manual.yaml`, optional battery_id, operator request | Manual MAIN → verified OFF/cooling → MIX |
| MANUAL custom/legacy adapter | manual text compatibility path | `ProductionManualSessionManager` | explicit V/I, stop conditions, optional reach targets | operator-defined Manual stage; safety envelope still applies |
| HANDS_OFF | RD ownership/control mode | `RdControlModeManager` and edge lease contract | ownership state, lease/readback | ownership mode, not a charge program |

### MISSING

- Нет одного production `ChargeProgramResolver`, который получает `Battery + Mode` и возвращает каноническую программу для всего V2 runtime.
- V3 `ProgramRegistry`/`ProfileRegistry` существуют, но production service их не использует.
- Manual program и AUTO program имеют разные owners и разные parameter stores.
- `FLOODED` присутствует в YAML/domain mapping, но отдельного production recipe в `config/charge/recipes.yaml` нет; в V3 chemistry mapping он сводится к calcium.

## 3. AUTO program audit

### Battery → chemistry → parameters → FSM

1. Battery может быть выбрана через battery registry (`battery_id`, chemistry, nominal capacity) либо создана как ad-hoc quick profile.
2. Telegram battery path отображает registry records и переводит chemistry в legacy profile: `AGM`, `EFB`, `Ca/Ca`; для unsupported chemistry auto-profile не предлагается.
3. Legacy mapping `Ca/Ca → CA_CA`, `EFB → EFB`, `AGM → AGM`, `Custom → CUSTOM` находится в `legacy_recipe_adapter.py`.
4. `ProductionChargeControllerV2` строит recipe envelope из legacy profile, intent, battery identity и condition; envelope ограничивает targets, но не заменяет FSM.
5. Реальные фазовые решения и targets остаются внутри `charge_logic.py`/`ChargeControllerV2`: PREP, Main, Desulfation, Mix, Safe Wait, Done.

### Параметры AUTO

`config/charge/recipes.yaml` содержит базовые main ceilings: AGM 15.0 V / 8 A, EFB 14.8 V / 7 A, CA_CA 14.7 V / 7 A. `config/charge/limits.yaml` содержит доменные верхние пределы 18 V / 18 A / 55 °C. При этом фактические stage targets, timers, Delta logic, temperature compensation и watchdog constants находятся также в `charge_logic.py` и controller modules.

**Вывод:** battery registry является источником chemistry/capacity identity, но не единственным владельцем charge program. FSM и Python constants по-прежнему определяют значительную часть поведения.

## 4. MANUAL program audit

### Фактическая цепочка

```text
operator text / selected battery
        |
        +--> load_manual_profile(manual.yaml, battery_id)
        +--> ManualChargeRequest
        +--> ProductionManualSessionManager.start()
        +--> ManualSessionState ARMING → ACTIVE
        +--> MAIN tail/hold → verified OFF → MIX
```

`manual.yaml` хранит базовый staged profile и может хранить override под конкретным `battery_id`. `load_manual_profile(..., battery_id="Baic72")` выбирает `manual.profiles.Baic72`, если такой override существует; иначе используется базовый `manual.main`/`manual.mix`.

`ManualChargeRequest` несёт V/I, stop conditions, `battery_id`, optional capacity, profile и stage. `ProductionManualSessionManager` владеет Manual lifecycle, main-tail threshold resolution через battery registry, delta confirmations, hold и переходом MAIN → MIX. OVP/OCP для Manual вычисляются от запроса и ограничиваются safety envelope.

### Persist/restore

`manual_session_v2.json` сохраняет request, stage, started_at, stop/hold fields, reach targets и identity payload. Restore не продолжает старую физическую сессию автоматически: состояние переводится в interrupted/reauthorization path; legacy identity absence классифицируется как ambiguous.

На момент аудита persisted state содержит:

- state: `active`;
- battery: `Baic72`;
- stage: `mix`;
- profile_id: `Baic72`;
- MAIN: 14.1 V / 5.0 A, minimum current 2.3 A, hold 0.001 h;
- MIX: 17.5 V / 3.5 A, ΔV 0.6 V, ΔI 0.6 A, hold 4 h;
- stop_reason: `manual_main_hold_complete`.

Это persisted/runtime evidence, а не независимое подтверждение физического состояния выхода.

## 5. Parameter ownership

| Parameter | AUTO | MANUAL | SAFETY owner | Audit result |
|---|---|---|---|---|
| Voltage | FSM target + recipe envelope; часть targets в `charge_logic.py` | operator/manual profile, bounded by Manual envelope | SafeOutput/runtime safety OVP envelope | split authority |
| Current | Ah-derived target, stage logic, recipe current ceiling | manual profile/request, max stage current | OCP and hardware current bounds | split authority |
| Timers | FSM constants: Main/Mix/Safe Wait/holds | manual profile `hold_hours`, confirmation intervals, stop timer | watchdog/lease timeouts | duplicated sources |
| Delta | AUTO CC ΔV / CV ΔI logic in legacy controller; V3 shadow has separate strategies | Manual profile `delta_voltage_v` + `delta_current_a` | stale/readback gates can veto | semantic divergence risk |
| Hold | AUTO `MIX_DONE_TIMER` plus chemistry windows | Manual MAIN/MIX profile hold | safety can interrupt | separate semantics |
| Temperature limits | compensation and stage behavior | Manual pause/resume/critical thresholds | external battery temp and PSU temp safety | multiple layers |
| Watchdog | legacy `charge_logic.WATCHDOG_TIMEOUT` and service watchdog | not a Manual program parameter | `soft_watchdog_containment`, runtime safety, edge lease | unresolved duplicate values/owners |

### Known conflicts

- EFB Mix window: production controller map uses 24 h, while legacy `charge_logic.py` constants/paths expose 20 h in several places.
- Watchdog: `charge_logic.py` has 300 s, while the soft watchdog path has a 180 s default/incident cadence.
- Manual `MAX_MANUAL_VOLTAGE` is 17.5 V while AUTO legacy ceiling is 16.6 V and EFB AUTO is narrower; this is intentional by current rules but not unified in one authority model.
- `hold_hours` is canonical for manual YAML, while compatibility code accepts legacy `hold_seconds` and converts it.
- KAK is not a first-class canonical label in the code: the effective implementation uses `CA_CA`, `CALCIUM`, `Ca/Ca`, with `FLOODED` mapped to calcium in V3 domain.

## 6. Battery binding

### FOUND

```text
BatteryIdentity(battery_id, chemistry, nominal_capacity_ah)
        |
        +--> registry / SQLite batteries
        +--> AUTO profile_for_chemistry() -> legacy profile
        +--> ChargeControllerV2._v2_battery_id + Ah
        +--> recipe envelope and trace context
        +--> recovery/session records
```

For manual selection, the selected registry record is kept in the UI selection map; its `battery_id` is passed into `ManualChargeRequest`. The same ID selects a Manual YAML override when present and is also used by `ProductionManualSessionManager` to resolve the battery-specific main-tail threshold from registry chemistry/capacity.

For `Baic72`, the deployment database contains `chemistry=ca_ca`, `nominal_capacity_ah=72.0`. The current persisted Manual session carries `battery_id=Baic72` and `profile_id=Baic72`, so the binding is present for this session. The actual profile values are from the Baic72 Manual override/effective persisted request, not from the AUTO CA_CA recipe.

### DIFFERENCE

Battery identity and charge-program identity are coupled differently by mode:

- AUTO: battery chemistry/capacity selects a legacy chemistry profile and the V2 FSM derives targets.
- MANUAL: battery_id selects a Manual profile override, while operator values and Manual stage remain authoritative within safety bounds.
- V3: contracts can represent both, but the production graph does not yet make this distinction through one resolver.

## 7. FSM boundary

The production FSM does **not** receive a fully resolved immutable charge program. It still contains:

- AGM/EFB/Ca/Ca branch logic;
- stage target calculations;
- Ah-derived current;
- Mix limits and hold timers;
- Delta evidence/confirmation logic;
- temperature compensation and safety-trigger actions;
- custom target handling.

The V3 tree has a cleaner boundary (`BatteryProfile` + `ProfileRegistry` + `ProgramRegistry` + strategies), but this is not the active production boundary on 101.

## 8. Safety inventory (actual code ownership)

| Protection | Factually present owner/path | Action boundary |
|---|---|---|
| OVP/OCP | `charge_logic.py` creates phase limits; `SafeOutputCoordinator` validates envelope; `runtime_safety_strict.py` performs guarded live protection writes/readback | physical OFF/containment remains V2 safety/output stack |
| OTP / temperature | charge FSM handles external battery temperature warning/pause/critical thresholds; strict runtime handles PSU temperature protection | safety path can request verified OFF |
| stale telemetry / HA loss | soft watchdog, runtime safety and HA recovery/containment paths | V2 containment; not V3 authority |
| Modbus/RD loss | readback/safety freshness checks and watchdog paths | fail-closed/containment through V2 output boundary |
| ESP loss / lease | `edge_safety_lease.py` plus ESPHome local dead-man | edge lease is final physical backstop; current configured TTL is 900 s with renewal path |
| emergency | `ChargeController` action flags, runtime safety variants, `SafeOutputCoordinator`, manual manager containment | multiple detection/request paths, single physical coordinator is intended but legacy writers remain |
| manual stop | `ProductionManualSessionManager.stop()` with verified OFF then lease disarm | Manual owner requests; V2 safety/output executes |

## 9. FOUND / MISSING / DIFFERENCE

### FOUND

- V2 AUTO and MANUAL modes are both production-reachable.
- Battery registry stores `Baic72` as CA_CA/72 Ah and current persisted Manual session binds to it.
- V3 profile/program/strategy modules exist in the working copy.
- V2 production has explicit recipe envelope and safety boundary layers.
- Manual profile supports per-battery overrides and staged MAIN → MIX behavior.

### MISSING

- V3 program resolver is not the active production resolver.
- No single canonical authority owns all AUTO/MANUAL program parameters.
- No separate first-class KAK/Ca/Ca/FLOODED policy object in the deployed production graph.
- No single unified source for watchdog, Mix windows and all Delta/Hold semantics.
- A deployment-level evidence path proving that `runtime/app.py` is the service composition root is absent; service facts show the opposite.

### DIFFERENCE

- Service naming claims V3 dry-run, but `bot.py`/V2 runtime is the active entrypoint.
- V3 has separate `ChargeProgram`/registry abstractions; V2 keeps program selection and much of the algorithm inside legacy FSM/controller.
- AUTO uses registry chemistry → legacy profile; MANUAL uses battery_id → Manual YAML override/effective request.
- Persisted active session is Manual `Baic72/MIX`, not an AUTO `charge_session.json` session.
- Working tree is dirty on deployment (`config/charge/manual.yaml`), so deployed configuration is not a clean repository snapshot.

## 10. No changes

- Node 101: no restart, checkout, pull, write, config change, lease call, START/STOP or physical command was executed.
- Local workspace: only this audit report was created; no runtime code, deployment files or node files were modified.
- No commit was created.

## Final status

**BLOCKED** — the actual 101 working copy is auditable and the current program paths are identified, but the production program authority is still V2/legacy and split across multiple sources. This is not an Architecture/V3 readiness pass and is not a recommendation to migrate control.
