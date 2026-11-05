# RD6018 — adaptive Recovery plateau (shadow design, 2026-11-05)

## Operator decision

Current operating session: **EFB / 65 Ah / Recovery**, externally confirmed battery
temperature 24 °C at the point of discussion. Do not substitute Ca/Ca 72 Ah.
Goal: evaluate low-current stagnation before intermediate recovery; low current
alone must not prove balanced cells or end recovery.

- Observation minimum: **90 min** continuous qualifying near-target CV.
- Observation extension: **up to 120 min** on weak or ambiguous decline.
- Compare medians of the first and last 15-minute segments rather than
  restarting on each 0.01 A new minimum.
- **Demonstration parameters**, subject to calibrated dry-run acceptance:
  drop <= 0.01 A over observed window: evidence of plateau after 90 min;
  drop > 0.02 A: meaningful progress, no plateau request;
  0.01 < drop <= 0.02 A: observe to 120 min, then inconclusive / no escalation.
- CV, near-target voltage, fresh temperature evidence, monotonic timestamps
  and no >10-minute holes are required. Missing data means INVALID, not PASS.
- Legacy 0.004C (EFB 65 Ah => 0.260 A) must not suppress plateau evidence.
  This coefficient entered the repo in commit 3535d1b (2026-08-29) as a
  capacity-normalized approximation of historical tail thresholds, **not** as
  a measured bank-balancing endpoint.
- A plateau verdict is **read-only evidence**, not high-voltage authorization.
  The existing stage owner, safety checks, EFB manufacturer limits, budget,
  thermal policy and recipe decide any recovery / MIX transition.
- AGM and ordinary Normal paths unchanged.

## Implementation status

Pure, **not wired to production**, no-actuation module:
`runtime/charge/evidence/recovery_plateau_policy.py`.
Tests: `tests/test_recovery_plateau_policy.py` (8/8 PASS initially).
No node104 deployment or charging setpoint/output change.

Read-only HA102 history replay (last 3 h; 360 current and 38 voltage
history entries): last ~100.5 min and ~116.7 min of the recorded current
yielded `CONFIRMED`, median decline 0.00 A. The 90-minute requested slice
contained only 87 min of available samples and yielded `OBSERVING`.
This replay *assumed* CV and temperature_valid=True to study current trend,
it did not prove those conditions historically and is not a go-live or HV proof.
The HA temperature entity was not freshly updated at the prior inspection,
despite the operator's physical confirmation of 24 °C.

## Next integration boundary

Keep this an isolated recipe-owned evidence policy. Wire it into the existing
MAIN / Recovery owner only after verifying the actually installed node104
version and live session intent/stage, defining timestamp persistence across
restarts, replaying noisy/gapped histories, and obtaining safety review.
Do not create a second controller or auto-enable HIGH-V merely because a
low-current plateau was detected.
