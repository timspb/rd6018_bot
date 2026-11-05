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

## 2026-11-05 implementation continuation — existing owner/recipe binding

The off-line candidate now integrates into the **existing** MAIN observation tick
at `application/charge_session_tick.py`, using a host-local bounded
`RecoveryPlateauObserver`. The observer records an
`efb_recovery_plateau_shadow` diagnostic result, resets on CV discontinuity,
stage, target, session, telemetry gap or process restart. A single fresh tick
cannot reuse another session's plateau verdict. No second stage controller.

The canonical `decide_main_transition` remains the **only** authority deciding
ENTER_DESULFATION or ENTER_MIX. A pinned EFB Recovery/Conditioning native
recipe can opt in with `charge.recovery_plateau.enabled: 1`, with 90/120
minute and drop thresholds configurable under `charge.recovery_plateau.*`.
Unpinned default is **disabled** (0), preserving existing legacy decisions.
While opt-in is enabled, a confirmed low-current plateau can select the
existing intermediate Recovery effect within the existing attempt budget, or
the existing final Mix when the budget is consumed. A missing, progressing
or inconclusive plateau never creates a new high-voltage request, and the
legacy 40-minute / 0.004C path is bypassed only in this opted-in mode.
Existing timeout, safety veto, stage targets, Main guard, cooling, chemistry
envelope, and charge ownership still apply. A confirmed plateau is not proof
that individual battery cells have equalized.

The 90–120 minute observation state is **process-local only**: after a restart
a fresh full window is required (conservative). It is not falsely restored
from a 15-minute analyzer window. Before production deployment, check actual
node104 code, current EFB Recovery session/intent, and real temperature
source freshness and pre-HV safety. The dry-run/history replay is not
manufacturer endorsement of any high-voltage schedule.

Focused WSL tests on current candidate: **42 passed, 177 subtests passed**,
including native recipe draft/session/provenance and policy parity. A broader
native-recipe regression **did not collect** because the system WSL Python
lacked optional runtime dependencies `aiogram` and `dotenv` (14 collection
errors); not counted as an algorithm regression or a full-suite PASS.
Node104 live read-only SSH verification attempted through the existing
credential source, but authentication failed; installed version and charge
session are thus **not verified in this stage**. No node104 write/restart,
no physical output or charge change, no release activation.

Pending: full production-dependency test environment, fresh node104 inspection,
review of installed runtime delta, coherent candidate release and controlled
rollout preserving current charging state. Deploy cannot be claimed yet.
