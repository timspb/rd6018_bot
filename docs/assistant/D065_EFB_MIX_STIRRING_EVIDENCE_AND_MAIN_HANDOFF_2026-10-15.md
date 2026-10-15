# D065 — passive EFB MIX evidence and MAIN execution handoff

Status 2026-10-15: SOURCE BRANCH / NON-ACTUATING / PHYSICAL OPEN.

The implementation lives in runtime/charge/observability/mix_stirring_evidence.py.
It classifies an observational EFB insufficient-stirring-current candidate, and
never decides or commands increased voltage or current. AGM is excluded and
Ca/Ca is observational-only pending its own research/calibration.

## Required MIX observations

Candidate classification requires the real MIX session and epoch, unconfirmed
Delta, fresh telemetry, confirmed Output ON, active CV, verified programmed
voltage readback matching the configured ceiling, and measured battery voltage
also at that ceiling. It further requires first observed ceiling by candidate
25 minutes, verified programmed current about 0.03C, and sustained measured
battery current below candidate 0.02C in three consecutive independent windows.
Gaps, out-of-order points and uncertain electrical/safety evidence cannot pass.

25 min, 0.02C, 0.03C +/- 0.005C, voltage agreement within 0.05V, 3x60-second
windows and max 90-second evidence gap are RESEARCH CANDIDATES, not physically
calibrated production thresholds or an authorization to modify a recipe.

A positive diagnostic code is MIX_STIR_CURRENT_INSUFFICIENT with
actuator_authority=False; it is not proof of electrolyte stratification.
Proving early 16.5V attainment with low current does not prove any particular
voltage >16.5V is needed or safe. The present physical authorization remains
15.5V max. No changes to automatic charge recipes or voltage limits.

## Existing thermal evidence, do not add arbitrary limits

signal_analyzer.py already computes THERMAL_ACCELERATION from coupled
temperature and current increase in CV, or temperature increase and voltage
decrease in CC. Its existing defaults are 0.12 degC/min, 30 degC,
0.005 A/min, and 0.005 V/min, as applicable. These are EXISTING
implementation thresholds, not newly approved EFB operating limits.

Use the real analyzer event on valid and fresh samples, NOT absence of a
stale/unknown event. The candidate classifier treats unknown thermal evidence
as insufficient. Display raw temperature rate for investigation. Normal
CV current reversal and CC voltage decline, without credible accelerating
temperature, are not automatically thermal faults. A confirmed Delta starts
the accepted two-hour MIX finishing hold without artificial current clipping.

## D063 correlation

The first naturally authorized EFB/Ca/Ca SAFE_WAIT remains open (issue #76).
Offline integration PR #77 proved genuine serializer-to-observer compatibility,
not physical evidence. No qualified historical EFB/Ca/Ca relaxations exist yet.

Join valid independent voltage_relaxation_runs to MAIN/MIX received Ah, capacity,
temperature and where independently measurable specific gravity by authentic
session/battery identity. Compare 5-15 min and 15-60 min slopes only when
complete; keep missing windows missing, never zero. No correlation/causation
claim can be made from the AGM-only historical data.

## MAIN Current Guard integration gate

Known local prototype branch feat/main-mix-dynamic-current-20261015 and commit
e58bd998823d8706c1d2a91d453e152cf485e913 were NOT accessible in the
remote GitHub repository during this audit. Preserve that local work and do
not reconstruct or overwrite it while home-PC connector is unavailable.

Canonical target selection is runtime/charge/strategy/main_targets.py;
hardware ownership is application/execution_port.py via its actual execution
owner. application/production_start_execution_port.py only routes START.

Persist MAIN epoch, initial min(0.1C, 12A) ceiling, monotonic guard ceiling,
cumulative verified active MAIN time, 30-min tick, identity and hardware
readback in canonical session state. Cooling, Output OFF and desulfation
must not count toward active time. Resume may never loosen a guard ceiling;
only authenticated desulfation-to-MAIN stage transition can open a new epoch
at the original approved current. Never let process restart do so.

Submit current and OCP changes through existing protected write sequencing,
with canonical set_current_readback_v2 and OCP verification. D061 owner
retirement / SIGKILL semantics must remain intact. Diagnostic modules have
no physical control permissions. Positive physical readback is necessary
before declaring an active integration PASS.

## Acceptance

PASS (prior): D063 PR #75 and #77 merged, 1781 historical local tests.
PASS (new source scope): EFB passive no-actuator classifier and offline tests.
OPEN: new hosted/self-hosted CI; calibration on EFB MIX curves; D063 first
physical SAFE_WAIT; MAIN execution handoff; D061 positive SIGKILL acceptance.
BLOCKED: home-PC gateway returned Session terminated at this audit, so
node104 was not freshly read or physically tested here.
