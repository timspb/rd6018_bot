# Pb Recovery Controller V2

## Status

V2 is now the production code path on this branch, not a shadow-only experiment.

- `bot.py` is a small production entrypoint.
- the previous monolithic Telegram/HA runtime is preserved byte-for-byte as `bot_legacy.py`;
- `ProductionChargeControllerV2` is installed by default;
- `ChargeControllerV2` is actuator-authoritative for non-Custom Main/Mix transitions;
- `v2_bot_ui` provides battery registry, intent selection, program preview and mode-specific evidence cards;
- hardware enable is transactional/fail-closed;
- raw evidence/trace capture and replay remain available for calibration.

`main` is not changed by this document; deployment/merge remains a separate operational decision.

## Design principle

Chemistry, charge intent, battery condition and safety are independent dimensions.

A generic `AGM` label does not say whether the battery is healthy, dry, rehydrated or whether the operator wants a normal charge versus recovery.

```text
Physical Battery + Lifecycle
          |
          v
Chemistry + Intent + Condition
          |
          v
Recipe Envelope
          |
Telemetry -> SignalAnalyzer -> V2 Authority
          |                     |
          |                     v
          +--------------> Stage decision
                                |
                                v
                  ProductionChargeControllerV2
                                |
                                v
                    non-bypassable HA safety
                                |
                                v
                             RD6018
```

AI remains explanation-only and cannot own actuator decisions.

## Domain

### Chemistry

- AGM
- EFB
- Ca/Ca
- Flooded
- Custom

### Intent

- Normal
- Recovery
- Conditioning
- Diagnostic

### Condition

- Unknown
- Healthy
- Sulfated suspected
- Dry suspected
- Rehydrated
- Overwet suspected
- Stratified suspected
- Degraded

Examples:

- `AGM + HEALTHY + NORMAL`
- `AGM + REHYDRATED + RECOVERY`
- `EFB + STRATIFIED_SUSPECTED + CONDITIONING`

These are deliberately different controller contexts.

## Authority boundary

### V2-owned

For non-Custom profiles V2 owns:

- Main evidence interpretation;
- AGM Main stage advancement;
- permission/denial of Desulfation;
- permission/denial of Mix/HV;
- Mix CV `Imin -> ΔI` finish evidence;
- Mix CC `Vmax -> ΔV` finish evidence;
- sticky 2h finish hold;
- abnormal plateau / thermal / voltage-instability stop-and-diagnose decisions.

### Legacy scaffold retained

The old FSM still supplies mature common mechanics:

- basic telemetry validation;
- temperature safety and Cooling;
- hard Main timeout;
- SAFE_WAIT mechanics;
- session persistence / restore;
- watchdog-compatible state;
- existing logging/statistics surfaces.

During V2-authoritative Main/Mix, legacy transition triggers are masked so they cannot independently escalate voltage or finish the stage.

### Custom

Custom remains the explicit operator-defined legacy contract. It is not silently reinterpreted as Pb Recovery V2.

## Signal model

The controller reasons about trajectories, not single thresholds:

- `dU/dt`
- `dI/dt`
- `dT/dt`
- CV current minimum (`Imin`)
- current plateau
- CV current reversal after Imin
- CC voltage maximum (`Vmax`)
- CC voltage reversal after Vmax
- voltage stability during current reversal
- thermal acceleration

A current rise after a well-defined CV minimum is not automatically a fault. It can be normal end-of-charge evidence when target voltage remains stable and temperature behavior is benign.

Conversely, current rise plus thermal acceleration and/or inability to hold U is suspicious. In CC, voltage fall plus thermal acceleration is suspicious; regulated current is not used as an independent finish signal.

## Main -> HV policy

High voltage is an explicitly authorized recovery tool, not a chemistry default.

- `Normal` and `Diagnostic`: automatic HV/Mix is forbidden.
- `Recovery` and `Conditioning`: HV is possible only after V2 evidence.
- a stable moderate plateau may lead to a service Desulfation step;
- a persistent plateau above roughly `1%C` is not auto-promoted to HV;
- invalid telemetry, thermal instability or voltage instability stops automatic escalation.

This preserves practitioner recovery behavior without reducing it to “16.x V is dangerous” or “all old batteries should be pushed to 16.x V”.

## Recipe envelope

`recipe_engine.py` separates requested stage target from chemistry+intent ceilings.
`ProductionChargeControllerV2` applies the envelope to targets after legacy temperature compensation, so compensation cannot silently escape the selected program.

Standard Telegram V2 does not automatically authorize expert EFB >16.5 V. The policy model contains an expert EFB envelope up to 17.5 V for a future explicit expert workflow, but normal V2 UI does not opt into it.

## Output enable invariant

Every new V2 start goes through `HassClient.safe_enable_output()` and `SafeOutputCoordinator`:

1. read complete live telemetry;
2. reject invalid battery voltage/current/temp/input/protection/output state;
3. validate recipe and absolute limits;
4. program OVP;
5. program OCP;
6. program voltage;
7. program current;
8. verify readback;
9. repeat preflight;
10. enable output;
11. verify output ON and protection/temperature/input state;
12. force OFF on any failed step.

A Telegram success message is emitted only after `enabled=True`. Failed programming/readback/enable rolls the controller session back and keeps output OFF.

## Physical battery registry

The V2 UI supports saved physical batteries with longitudinal lifecycle:

- chemistry;
- nominal capacity;
- manufacturer/model;
- condition;
- water added total/per cell;
- refill timestamp;
- cycles since refill;
- measured capacity;
- CCA;
- internal resistance.

Recovery-cycle evidence can then compare a battery primarily with itself over repeated cycles.

## Recovery evidence/history

Persisted evidence includes:

- Main target / Imin / time-to-target / Ah;
- HV target / Imin / reversal;
- temperature start/max/max dT/dt;
- relaxation at 5m/15m/1h/12h/24h;
- measured capacity;
- CCA;
- Ri;
- outcome/notes.

Raw 30-second V2 traces also retain explicit CV/CC mode and frozen thresholds, so historic sessions stay interpretable after analyzer tuning.

## Telegram workflow

Production V2 UI adds:

```text
Modes
  -> chemistry OR saved physical battery
  -> intent
  -> capacity (for ad-hoc profile)
  -> program preview
  -> explicit Start
```

Dashboard additions:

- `🔋 АКБ` — physical battery registry;
- `🧭 V2` — active controller/evidence card.

The active card is mode-specific:

- CV: Imin / ΔI / current trend;
- CC: Vmax / ΔV / voltage trend;
- temperature trend and current V2 decision in both modes.

## Entry point / rollback

Production:

```bash
python bot.py
```

Independent rollback switches:

```bash
V2_UI=0 python bot.py
```

keeps the old Telegram UI while leaving V2 actuator authority at its configured value.

```bash
V2_AUTHORITATIVE=0 python bot.py
```

restores legacy Main/Mix authority while the new UI may remain enabled.

Full emergency legacy presentation + legacy actuator authority:

```bash
V2_UI=0 V2_AUTHORITATIVE=0 python bot.py
```

The preserved monolith can also be run directly for diagnosis:

```bash
V2_AUTHORITATIVE=0 python bot_legacy.py
```

## Testing

CI compiles the repository and runs the complete unittest matrix on Python 3.10, 3.11 and 3.12.

Coverage includes:

- safe output transaction and readback failure;
- V2 Main/Mix authority;
- CV/CC evidence separation;
- sticky finish hold;
- battery registry/idempotent recovery history;
- trace persistence/replay/calibration;
- recipe envelopes;
- production controller target bounding;
- V2 UI formatting/catalog;
- transactional Telegram V2 startup.

Hardware/on-device smoke and real-battery trace review remain operational validation steps, not substitutes for deterministic CI.
