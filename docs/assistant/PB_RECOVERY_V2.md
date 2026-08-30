# Pb Recovery Controller V2

This document describes the production architecture/authority boundaries. Exact strategy values live in `V2_DECISION_LOG.md` and `CHARGE_STRATEGY.md`; unresolved calibration lives in `V2_OPEN_QUESTIONS.md`.

## 1. Authority layers

```text
Telegram/operator intent
        |
        v
chemistry / AUTO strategy -------------------+
        |                                      |
        | chosen action                        | diagnostic evidence
        v                                      v
recipe envelope                         hypothesis engine
        |                                      |
        +------------- allowed/veto -----------+
                         |
                         v
actuator safety transaction
fresh telemetry -> OVP/OCP -> V/I -> configured readback -> edge lease -> ON -> verify
```

Manual is a sibling authority, not an AUTO stage:

```text
operator Manual request
        -> ManualSession
        -> same immutable actuator safety boundary
```

AI remains advisory and has no actuator authority.

## 2. Chemistry, intent, program and stage are independent

AUTO keeps separate concepts:

- chemistry: AGM / EFB / Ca-Ca / Flooded / Custom;
- intent: Normal / Recovery / Conditioning / Diagnostic;
- entry/program mode: full AUTO vs Auto Mix direct entry;
- stage: PREP / MAIN / recovery / MIX / SAFE_WAIT / Storage etc.;
- condition/evidence: longitudinal diagnostic context.

Normal preserves the complete ordinary automatic chain. Diagnostic is the explicit no-new-auto-HV intent. Auto Mix starts directly in Mix and is not an intent.

## 3. Initial start

Before first Output ON:

```text
Vbat < 12.0 V  -> PREP at small ~0.01C current
Vbat >= 12.0 V -> MAIN directly + PREP_SKIPPED audit
```

No one-tick logical PREP/physical Main mismatch is retained in production V2.

## 4. Main/recovery

Normal-tail evidence and lack-of-progress plateau evidence are separate.

Ca/Ca/EFB:
- three intermediate recovery attempts across the whole session;
- progress does not reset count;
- next confirmed plateau after budget may enter final Mix.

AGM:
- four attempts/session;
- budget exhaustion does not force Mix;
- preserve conservative staged Main behavior.

72h Main is a strategy fallback, not generic hard safety.

## 5. Mix / relaxation / Storage

Mix evidence is regulation-specific:
- CV: Imin -> confirmed current rise;
- CC: Vmax -> confirmed voltage fall.

After spaced confirmations, the two-hour finish hold is sticky. Fallback maxima are Ca20h/EFB24h/AGM10h.

SAFE_WAIT is Output-OFF relaxation with ~2h maximum anti-stall wait. Normal completion ends in managed Storage around 13.8V/1A with Output ON.

## 6. Cooling

Cooling pauses active process time. Exact source stage/program target is preserved. Recovery budget/AGM step/confirmed sticky evidence survive; continuity-dependent incomplete plateau/delta proof is invalidated. Resume uses a fresh safe-enable/readback transaction.

Manual Cooling similarly preserves exact operator V/I but not unfinished continuity proof.

## 7. Manual

Manual is first-class operator authority:

- `0 < V <= 17.5 V`;
- `0 < I <= 12 A`;
- OVP/OCP derived, never weakened by operator;
- no chemistry-created Recovery/Mix/Storage transitions;
- timer/V/I/reach/delta stop rules are operator kill conditions;
- active reconfiguration uses verified OFF -> fresh safe-enable;
- persisted active state restores `INTERRUPTED` and requires explicit re-authorization.

Optional saved `battery_id` is longitudinal metadata only. Saved chemistry/capacity never changes Manual V/I or grants HV permission.

## 8. Generic EFB voltage boundary

The global V2 outer limit of 17.5V is **not** an EFB chemistry entitlement.

Generic EFB AUTO/Recovery/Conditioning is capped at 16.5V. Passing an expert flag cannot enlarge that envelope. Any future automatic EFB >16.5V must be a separate exact model-specific manufacturer-backed recipe.

Manual/Custom may still use the global 17.5V outer limit under immutable safety.

## 9. Diagnostic hypotheses and HV veto

Replace one generic bad-battery score with independent hypotheses:

- cell fault;
- self-discharge;
- sulfation / poor acceptance;
- stratification;
- capacity loss;
- thermal abnormality;
- charger/connection path.

The strategy chooses an action first. Only then may strong diagnostic authority veto a **new** Recovery/Mix escalation. A first SG imbalance, one U/I sample or a legacy score cannot create a block. Inference never creates HARD_STOP; immediate unsafe electrical/thermal states belong to the separate safety layer.

Bank-Fault score calibration is replayed against independently labeled real cases using `BANK_FAULT_CALIBRATION.md`; production weights are not tuned to synthetic tests.

## 10. Specific gravity

Per-cell SG is external evidence.

- raw six positional readings are primary durable data;
- first complete spread >=0.030 -> imbalance/stratification VERIFY evidence, not short-cell proof;
- physical electrolyte access belongs to the exact battery as `UNKNOWN/SERVICEABLE/INACCESSIBLE`;
- AGM never SG;
- EFB/Ca/Flooded chemistry alone does not grant access;
- unavailable SG never raises fault confidence;
- hydrometer mode and correction convention belong to each measurement;
- temperature-compensated instruments are never software-corrected again;
- named manufacturer conventions are explicit and never inferred from manufacturer/model text.

See `SG_POLICY_V2.md`.

## 11. Dynamic-loop evidence

RD displayed `V/I` is not battery internal resistance.

A controlled safer current reduction may produce a two-wire `ΔV_BAT/ΔI` dynamic-loop fingerprint. It includes battery response plus leads/contacts/internal path/polarization and is directly comparable only under unchanged physical connection identity.

`V_OUT - V_BAT` has no assigned resistance meaning. The characterization tool may report the difference descriptively but must not label it cable/path/internal resistance.

Actual cadence/noise/settling/reconnection behavior must be measured per `DYNAMIC_LOOP_CALIBRATION.md` before automatic probe parameters are chosen.

## 12. Persistence

Evidence and action authority are separate:

- completed SG/dynamic-loop/recovery evidence may persist;
- in-flight diagnostic probe -> ABORTED_RESTART + defensive OFF;
- pending operator/fault verification expires;
- expert authorization revokes;
- non-authoritative rest observation may persist until expiry;
- derived diagnostic authority is recomputed from evidence.

No authority-bearing diagnostic action resumes mid-step after crash.

## 13. Hardware safety boundary

Every enable/reconfiguration remains transactional:

```text
fresh telemetry
-> validate recipe/manual envelope
-> program OVP/OCP
-> program V/I
-> configured-value readback
-> edge safety lease
-> Output ON
-> post-enable verification
```

Higher-energy state has shorter allowed blind-operation time. `BAT_MODE` is observation. Vin is PSU-health telemetry, not battery chemistry permission. `temp_int` protects RD/PSU; `temp_ext` is battery thermal evidence/safety.

## 14. Merge boundary

Unit CI only proves software contracts. PR #2 remains Draft until `V2_VALIDATION_PLAN.md` BENCH/BAT gates are satisfied. Q004/Q013 need labeled real fault cases; Q005/Q014 need actual RD/ESPHome/HA characterization. Main remains unchanged until explicit merge approval.
