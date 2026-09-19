# RD6018 V2 Functional Audit Before Control Migration — WORKSTREAM 42

## Status

**`FUNCTIONAL_PARITY_AUDIT_COMPLETE`**

Аудит read-only. Runtime, FSM, START/STOP, protection logic, physical
execution и deployment не изменялись.

## 1. Safety audit

| Protection/path | Trigger | Current owner/action | Recovery | V3 representation |
|---|---|---|---|---|
| OVP/OCP | RD protection trip, invalid protection/readback or envelope | `V2RuntimeSafetyGuard` → `SafeOutputCoordinator` → verified OFF; ESPHome protection remains local | fresh readback, confirmed OFF, operator/runtime reauthorization | `SafetySignal(READBACK/TELEMETRY)` → `SafetyDecision` → `ContainmentRequest` |
| OTP, RD internal | `temp_int >= 55°C` | strict/V2 safety guard fail-closed and OFF | fresh temperature and explicit reauthorization | thermal safety signal, containment |
| Battery thermal pause | external temperature `>=40°C` | `ProductionManualSessionManager` enters COOLING, Output OFF | resume at `<=35°C`, fresh safe-enable | domain cooling state plus containment observation |
| Battery critical temperature | external temperature `>=45°C` | Manual manager stops; automatic controller emits emergency/stop path | new authorized session after verified OFF | safety decision/containment |
| External-temp integrity | missing/stale/incoherent sensor during managed HV | `ExternalTempIntegrityMonitor` latches; V2 guard contains | durable fault retirement and fresh reauthorization | latched safety state |
| Stale/invalid telemetry | required channels missing or freshness incoherent | V2 guard fail-closed; complete snapshot loss has `840 s` recovery grace | HA/readback recovery before deadline; otherwise existing containment | telemetry-loss signal, separate from command/lease loss |
| HA/Modbus transport loss | live snapshot exception or stale readback | V2 safety/data path observes loss; no new physical owner | HA/readback recovery; grace applies only to complete transient loss | `TelemetryProvider` failure + `HA_DEGRADED` candidate |
| ESP/lease loss | lease renewal failure, stale Modbus age or TTL expiry | Python fails closed; ESPHome edge dead-man is final local OFF authority | fresh lease state and explicit reauthorization | separate `LeaseSignal`; not telemetry authority |
| Software watchdog | last HA heartbeat older than configured timeout while managed/energized | `soft_watchdog_containment` calls existing hard-stop path, bounded retry | verified OFF; incident latched | watchdog detection → canonical safety decision |
| Emergency | runtime safety, strict safety, V2 safety or controller emergency marker | multiple detection/writer paths converge on SafeOutput/verified OFF | explicit diagnosis/restart authorization | one decision contract, existing V2 execution boundary |
| Manual stop | operator/manual manager stop | `ProductionManualSessionManager.stop()` → OFF confirmation; unconfirmed OFF remains ARMING containment | confirmed OFF, otherwise remain contained | `MANUAL_ACTION` + verification state |

Important separation: HA telemetry loss is not automatically command loss or
lease loss. The ESPHome lease remains TTL `900 s`, with a configured renewal
interval of `300 s`; Python grace is `840 s` and is a different policy.

## 2. V2 charge algorithm

### Automatic FSM

| State/phase | Entry | Exit/decision | Timers/thresholds | Safety override |
|---|---|---|---|---|
| IDLE | no active controller/session | accepted START or remain idle | none | no unmanaged Output ON is accepted |
| PREP | automatic START with battery voltage `<12.0 V` | MAIN after prep conditions | about 12 V plus temperature compensation, low current | telemetry/envelope/temp/protection gates |
| MAIN/CC/CV | normal START, or return from recovery | AGM step, desulfation, MIX, safe completion or diagnostic stop | profile target; Main max `72 h`; tail/plateau evidence | fresh telemetry and readback; temperature and protection can force OFF |
| AGM steps | AGM Main evidence and stage hold | next AGM voltage step or later stage decision | stages `14.4/14.6/14.8/15.0 V`; minimum step hold `15 min`; first-stage hold policy | same Main safety boundary |
| DESULFATION | bounded plateau/recovery decision | MAIN after service stage or diagnostic path | `16.3 V`, about `2 h`; Ca/EFB and AGM attempt budgets differ | `BLOCK_AUTOMATIC_HV` veto; safety overrides |
| MIX | accepted Main/recovery decision or direct Auto Mix | Delta-confirmed finish hold, MIX timeout, or diagnosis | blanking `120 s`; CV `Imin→confirmed ΔI`; CC `Vmax→confirmed ΔV`; 3 confirmations about 60 s apart | max active Mix budget and hard safety |
| FINISH HOLD | confirmed Delta in MIX | SAFE_WAIT/Storage after `2 h` sticky hold | `MIX_DONE_TIMER=7200 s` | timeout without accepted hold is not success |
| SAFE_WAIT | normal completion | Storage/Done after voltage relaxation or max wait | up to about `2 h`; Output OFF during wait | failure path stays OFF |
| DONE/STOP | successful completion, diagnostic stop or operator stop | explicit new authorization required | no automatic resume from DONE | verified OFF required |

Normal automatic recovery is bounded: Ca/Ca and EFB have up to three
desulfation attempts before final Mix; AGM has its separate budget and does not
force Mix after the same condition. Mix completion is strategy evidence, not a
generic timer success.

### Manual FSM

`IDLE → ARMING → ACTIVE → COOLING ↔ ARMING/ACTIVE → STOPPED/FAILED`.

Manual START creates a request, derives OVP/OCP from V/I, invokes the existing
safe-enable transaction, and only then emits active identity/event evidence.
Manual Mix uses a `120 s` blanking window and CV/CC-specific Delta tracking with
three confirmations at a configured interval. Main tail evidence can move a
profiled manual session to Mix; a manual stop is not the same as automatic
chemistry termination.

## 3. Log and event audit

| Source | Contains | Gap found |
|---|---|---|
| `charging_history.log` / `charging_log.py` | session headers, START-like records, stage end, checkpoints, V2 transition markers | flat text, no mandatory `session_id`/`trace_id`; Delta/Hold details are not guaranteed canonical events |
| Python logger / systemd journal | `MANUAL_TRANSITION`, `MANUAL_EVIDENCE`, emergency markers, watchdog and safety diagnostics | separate stream; correlation is timestamp/text based |
| `charge_session.json` | automatic stage, profile, targets, timers, stage history and restore metadata | state is not a complete event log; historical event chain can be reconstructed only partially |
| `manual_session_v2.json` | manual request, state, start/pause/hold timestamps, stop reason and optional identity | legacy files may have no identity; restore is intentionally interrupted/non-authorizing |
| SQLite `sensor_history` | telemetry history | measurements, not lifecycle events or decisions |
| Telegram/UI | filtered current-session events and graph data | filtering uses last START/RESTORE boundary; absent START yields empty/noisy/ambiguous history |
| V3 canonical event contracts | typed event/timeline model | observer-side contract exists, but V2 production does not yet provide a complete live canonical chain |

The main loss points are therefore:

1. START/RESTORE is the current text-log boundary; a missing or legacy START
   prevents reliable session slicing.
2. Phase transitions are split between controller action logs, stage history,
   manual logger records and journal entries.
3. Delta/Hold are often evidence/log messages, not durable canonical events.
4. STOP may be represented by a state file, a V2 diagnostic marker, a manual
   transition or verified physical OFF, with no single event identity.

## 4. Restart, resume and pickup

### Automatic

`charge_logic.py` persists `charge_session.json` with profile, capacity, stage,
targets, timers, stage history, Delta/hold markers and timestamps. Restore is
accepted only within the configured age window (`24 h` in the current code) and
revalidates/clamps targets and stage data. Invalid/expired state is removed;
Output is not silently re-energized by persistence alone.

`ChargeControllerV2` additionally persists its V2 trace seed/session metadata
when available. This improves replay correlation but is not equivalent to a
complete canonical event chain.

### Manual

`ProductionManualSessionManager` persists `manual_session_v2.json`. After a
process restart, an active Manual state becomes `INTERRUPTED` and requires
operator reauthorization; it does not silently re-enable Output. Existing
identity is restored when valid; legacy active state without identity remains
ambiguous. Cooling, pause totals, reach targets and hold timestamps are
retained, but continuity-dependent Delta confirmation is reset across cooling.

### What is lost

- no universal lifecycle identity across all V2 paths;
- no guaranteed trace continuity between journal, flat history and state files;
- no canonical reconstruction of every Delta/Hold/STOP event;
- current sensor history cannot by itself prove an FSM transition.

## 5. Battery binding audit

```text
operator/manual selection
    -> ManualChargeRequest.battery_id / capacity_ah
    -> Manual profile loaded from config/charge/manual.yaml
    -> manual_session_v2.json request
    -> ProductionManualSessionManager
    -> V/I/temperature and stop/Delta logic
```

For automatic V2:

```text
battery/profile selection
    -> ChargeController.battery_type + ah_capacity
    -> ProductionController._v2_battery_id / derived session id
    -> battery_registry record and recovery evidence
    -> profile targets, thresholds and strategy decisions
```

The binding is distributed across request JSON, controller memory, session
files and SQLite registry records. `battery_id` is the strongest link for
Manual and diagnostics; legacy automatic sessions may fall back to a derived
`profile/capacity/time` identity.

## 6. Findings relevant to V3 parity

### Confirmed behavior to preserve

- verified OFF is required for containment and lease disarm;
- ESPHome local dead-man remains final physical safety;
- HA loss, telemetry staleness, command failure and lease expiry are distinct
  concepts;
- CV uses current response (`Imin → ΔI`), CC uses voltage response
  (`Vmax → ΔV`);
- Delta confirmation precedes sticky finish hold;
- restart does not silently re-energize an interrupted Manual session.

### Parity blockers / configuration conflicts

1. **EFB Mix budget conflict:** `charge_logic.py` has `EFB_MIX_MAX_HOURS=20`,
   while current accepted strategy documentation specifies `24 h`.
2. **Watchdog conflict:** `soft_watchdog_containment` defaults to `180 s`,
   while `charge_logic.py` retains a `300 s` watchdog constant. They are not
   the same mechanism, but the effective operator meaning is ambiguous.
3. **Voltage authority drift:** YAML safety/profile limits say `18 V`,
   `config.py` exposes `16.6 V` legacy auto and `17.5 V` Manual, while V2
   strategy further limits automatic EFB to `16.5 V`.
4. **Event identity gap:** V2 has partial trace/session support, but no
   universal mandatory identity for every manual/automatic event source.
5. **Safety writer topology:** multiple runtime safety modules and watchdog
   paths remain active compatibility writers even though the normalized V3
   model names one decision owner.

These are audit findings only. No values or runtime behavior were changed.

## 7. Migration recommendation

Before control migration, freeze the above as explicit V2 oracle behavior,
resolve the three configuration conflicts through an approved decision record,
and require every V2 observed transition to map to a canonical event with
session/trace identity. V3 should consume these observations and represent
safety/lease/containment separately; it should not infer missing events from
telemetry alone.
