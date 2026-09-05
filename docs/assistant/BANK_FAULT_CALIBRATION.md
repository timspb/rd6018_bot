# V2 Bank-Fault Calibration Workflow

Status: **CALIBRATION HARNESS IMPLEMENTED; PRODUCTION WEIGHTS STILL OPEN (Q013)**

The purpose of this workflow is to validate the existing hypothesis scores and authority boundary against labeled real cases without changing thresholds by intuition.

## What is being calibrated

Current production `battery_fault_engine.py` contains deterministic hypothesis weights and level boundaries:

```text
NORMAL   < 15
WATCH    >= 15
VERIFY   >= 35
PROBABLE >= 60
HIGH     >= 80
```

`BLOCK_AUTOMATIC_HV` is intentionally much stricter than a high generic score: it requires explicit external failed-cell confirmation or sufficiently strong multi-class cell-fault evidence. Inference never creates `HARD_STOP`.

These numbers remain unchanged until real labeled observations justify a change.

## Case format

One JSON object per line:

```json
{
  "case_id": "battery-A-post-recovery-2026-09-01",
  "context": {
    "rested_ocv_v": 10.72,
    "fully_charged_before_rest": true,
    "battery_isolated_during_rest": true,
    "recovery_attempts": 3,
    "recovery_response_improved": false,
    "abnormal_thermal_response": false
  },
  "expected": {
    "authority": "block_automatic_hv",
    "hypothesis_levels": {
      "cell_fault": "high",
      "capacity_loss": "watch"
    }
  },
  "notes": "external tester later confirmed failed cell"
}
```

A nested stored SG assessment may be supplied under `context.specific_gravity` with:

```json
{
  "valid_cell_count": 6,
  "minimum": 1.180,
  "maximum": 1.270,
  "median": 1.268,
  "spread": 0.090,
  "low_outlier_cells": [4],
  "high_outlier_cells": [],
  "level": "verify",
  "reason": "cell_specific_gravity_imbalance"
}
```

Do not create expected labels from the same score being evaluated. Labels should come from later independent evidence where possible: external load/conductance test, persistent post-corrective per-cell SG, known isolation/rest behavior, confirmed physical cell fault, measured capacity, or a trusted postmortem.

## Run

```bash
python tools/evaluate_battery_fault.py cases.jsonl
```

Optional report file:

```bash
python tools/evaluate_battery_fault.py cases.jsonl --output bank-fault-report.json
```

The CLI returns exit code `2` when either safety-significant mismatch occurs:

- `unexpected_hv_blocks > 0`: V2 would block automatic HV where the labeled case says it should not;
- `missed_hv_blocks > 0`: labeled case requires block but current engine would not block.

Hypothesis-level mismatches are reported separately. They are calibration evidence, not an automatic instruction to change a score.

## Required calibration set before changing weights

Do not tune on only failed batteries. The dataset should include at least these classes:

1. healthy flooded/Ca battery after normal charge;
2. healthy EFB;
3. healthy AGM (no SG evidence);
4. reversible sulfation that improves after recovery;
5. stratification/SG imbalance that improves after manufacturer-appropriate corrective cycle;
6. persistent one-cell SG abnormality after corrective retest;
7. known self-discharge with battery isolated;
8. parasitic-load case where battery was **not** isolated;
9. charger/clip/path fault that mimics battery degradation;
10. external load/conductance failure;
11. externally confirmed failed/shorted cell;
12. thermal abnormality without failed-cell confirmation.

Repeated measurements from the same physical battery should keep the battery identity visible in notes/case IDs so one battery does not silently dominate the calibration set.

## Acceptance principle

Safety boundary is asymmetric:

```text
false BLOCK_AUTOMATIC_HV
    -> can deny a useful corrective cycle

missed BLOCK_AUTOMATIC_HV
    -> can permit unsafe automatic HV on a genuinely failed cell
```

Both must be visible independently. Do not optimize a single aggregate accuracy number and hide either class.

## Relationship to Q004/Q013

- Q013 owns score/level calibration across all hypotheses.
- Q004 owns the especially conservative cell-fault -> automatic-HV block boundary and false-positive strategy.
- This harness supplies evidence for both; it does not itself authorize threshold changes.
