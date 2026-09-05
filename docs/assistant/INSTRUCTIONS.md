# Assistant Instructions for RD6018 Pb Recovery V2

Use this directory as durable source of truth. Do not reconstruct current strategy from chat memory when repository documents answer it.

## Read order

1. `V2_DECISION_LOG.md`
2. `V2_OPEN_QUESTIONS.md`
3. `CHARGE_STRATEGY.md`
4. `PB_RECOVERY_V2.md`
5. `V1_BEHAVIORAL_AUDIT.md`

Supporting evidence/gating:
- `V2_VALIDATION_PLAN.md`
- `SG_POLICY_V2.md`
- `BANK_FAULT_CALIBRATION.md`
- `DYNAMIC_LOOP_CALIBRATION.md`

## Branch boundary

Continue V2 on `refactor/pb-recovery-controller-v2`. Keep `main` unchanged until physical/on-device validation and explicit merge approval. PR #2 remains Draft until BENCH/BAT gates pass.

## Do not reopen accepted contracts without new evidence

- `<12V PREP / >=12V MAIN` is atomic before first ON.
- Normal is full AUTO; Diagnostic is no-new-auto-HV.
- Ca/EFB recovery budget 3/session; AGM 4/session and conservative after exhaustion.
- Mix fallback Ca20/EFB24/AGM10; sticky two-hour finish hold.
- SAFE_WAIT max ~2h anti-stall; Done means Storage Output ON.
- Cooling pauses active process clocks.
- Manual is separate operator authority, <=17.5V/12A, derived OVP/OCP, restart -> INTERRUPTED -> explicit reauth.
- AUTO Manual-OFF is a terminal side-condition, not chemistry authority.
- Post-heavy-recovery 24–48h rest is diagnostic recommendation, not lockout.
- Diagnostic actions never resume authority-bearing work mid-crash; derived authority is recomputed.
- SG access is explicit per physical battery; AGM never SG; EFB/Ca/Flooded need SERVICEABLE access.
- Raw SG is primary; hydrometer/correction policy is explicit; never double-correct a compensated hydrometer.
- Generic EFB AUTO/Recovery/Conditioning ceiling is 16.5V. 17.5V remains Manual/Custom outer ceiling, not EFB chemistry permission.
- RD displayed V/I and two-wire dynamic-loop are not battery internal resistance.
- Vout-Vbat is descriptive only; never infer cable/path resistance without separate topology evidence.

## Current genuinely open work

Only these remain open in strategy/calibration:

- Q004: cell-fault/HV-block false-positive/false-negative calibration from real labeled cases;
- Q005: automatic controlled-probe amplitude/timing/eligibility from actual characterization;
- Q013: hypothesis score/level calibration from real labeled cases;
- Q014: RD/ESPHome/HA dynamic-loop cadence/noise/repeatability/reconnection characterization;
- Q015: final physical compatibility/merge validation.

Do not tune Q004/Q013 weights or Q005/Q014 probe parameters from synthetic tests. Use:

```bash
python tools/evaluate_battery_fault.py cases.jsonl --output report.json
python tools/characterize_dynamic_loop.py probe.jsonl --output report.json
```

## Safety/documentation discipline

- AI is advisory only.
- Safety/readback/edge lease is separate from chemistry.
- No diagnostic inference creates HARD_STOP.
- Do not call a first SG imbalance a shorted cell.
- Do not call unavailable SG fault evidence.
- Do not call a fallback window an ETA.
- Do not treat Vin/temp_int as battery chemistry evidence.
- Do not silently infer manufacturer-specific profiles from names.
- If changing accepted behavior: update Decision Log + tests + strategy/docs in the same work stream.
