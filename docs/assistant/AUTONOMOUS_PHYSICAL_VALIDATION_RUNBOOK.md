# AUTONOMOUS physical validation runbook

This runbook closes the remaining **physical** evidence gap for the explicit
RD6018 generic-PSU AUTONOMOUS mode. Repository tests are prerequisites, not a
substitute for these checks.

## Scope and hard stops

- Use only the dedicated approved bench. **Never use node 101 as a test bench.**
- Do not connect or charge a live Pb battery for this validation. A no-load or
  already-approved benign bench load is sufficient for the authority/outage
  checks.
- Do not flash or modify ESPHome. If the deployed edge firmware does not expose
  the expected AUTONOMOUS/lease/readback contract, stop with
  `BLOCKED_NEEDS_ESPHOME_AUTHORIZATION`.
- Do not invoke raw Home Assistant `enter_autonomous` / `exit_autonomous`
  buttons for the production transition. Use the bot-side physical-test client
  so the real `RdAutonomousModeCoordinator` and ownership transaction are
  exercised.
- Do not add arbitrary Output, V/I/OVP/OCP, entity, timeout, force, reboot,
  Wi-Fi, or clock parameters to the physical-test control plane.
- Do not provoke OVP/OCP, overtemperature, or electrical faults unless an exact
  previously-approved deterministic procedure already exists for the same
  hardware/firmware. Otherwise report the physical gate as pending.
- At any unexpected state, restore network access if needed, obtain physical
  Output OFF, stop the test, preserve logs/evidence, and do not continue into
  the next phase.

## Required software baseline

The execution host must run the exact reviewed head of PR #24 (or a descendant
that contains it unchanged) together with its stacked dependencies. Record the
full commit SHA before any physical action.

The local physical-test plane remains disabled by default. Enabling
`RD6018_PHYSICAL_TEST_CONTROL=1` is a temporary activation-stage change for the
bench only. Record the previous service environment/configuration before
changing it and restore that configuration during cleanup.

The only AUTONOMOUS client commands are:

```bash
python tools/physical_test_autonomous_client.py status
python tools/physical_test_autonomous_client.py enter
python tools/physical_test_autonomous_client.py exit
```

## Evidence format

For every phase record:

- UTC start/end timestamps;
- exact bot commit SHA;
- deployed ESPHome/device identity and any available firmware/build identity;
- exact command/action;
- client JSON before/after;
- relevant bot/HA/ESP logs;
- independent physical observation when HA/network is intentionally absent;
- outcome `PASS`, `FAIL`, or `BLOCKED`, with the exact reason.

Never infer continuity through an outage solely from the post-recovery state.
If Output continuity cannot be independently observed while HA/network is
unavailable, mark that phase `BLOCKED_NO_INDEPENDENT_OBSERVER`.

## Phase A — baseline/preflight

Before crossing ownership:

1. Prove the target is the approved bench and not node 101.
2. Record the exact repository SHA and CI status.
3. Verify the deployed edge exposes the expected V2 Output readback,
   Protection raw code, lease state/generation and explicit AUTONOMOUS state.
4. Verify no AUTO/Manual/adopted managed session is active.
5. Require canonical Output OFF (`register-18 V2 = 0`), Protection=0 and fresh
   direct Modbus evidence.
6. Record V/I/OVP/OCP readback, edge generation, lease `armed/tripped`, boot
   quarantine and remaining lease time.
7. Run `physical_test_autonomous_client.py status` and save the JSON.

If firmware identity/contract differs from the previously validated edge and
would require an ESPHome change, stop; do not flash it from this procedure.

## Phase B — production AUTONOMOUS entry

Run:

```bash
python tools/physical_test_autonomous_client.py enter
python tools/physical_test_autonomous_client.py status
```

PASS requires all of the following:

- entry uses the production coordinator and returns success;
- canonical Output remains OFF;
- edge AUTONOMOUS is true;
- manager-observed edge AUTONOMOUS is true;
- software ownership is HANDS_OFF/non-PB-actuating;
- edge generation advanced;
- lease is clean/unarmed with zero remaining managed lease;
- V/I/OVP/OCP readback is unchanged;
- no AUTO/Manual/adopted managed session was started.

Any Output ON or setpoint/protection change is an immediate FAIL and stop.

## Phase C — local generic-PSU operation

With explicit AUTONOMOUS already active, use only the RD6018/local edge control
surface to turn Output ON. Do not use Telegram, the bot physical-test socket or
HA to energize Output. Do not change V/I/OVP/OCP unless an already-approved
bench procedure requires it; preserving the existing benign setpoints is
preferred.

While the network is still healthy, confirm that telemetry observes Output ON
and that the bot remains observational rather than adopting PB authority.

This phase validates that AUTONOMOUS is a generic PSU mode, not a Pb charging
mode. No battery chemistry/session claim is permitted.

## Phase D — Wi-Fi / HA loss while AUTONOMOUS Output is ON

Induce a **reversible network isolation** of the ESP/HA path without powering
RD6018 or changing ESPHome configuration. Prefer the existing bench network
isolation mechanism (AP/VLAN/firewall) if one is already approved. If there is
no controlled reversible method, mark the phase BLOCKED rather than improvising
one.

Hold the outage for at least 6 minutes. This crosses the bot's 180 s readback
outage interval and one 5-minute managed renewal cadence; AUTONOMOUS itself must
not depend on either.

During the outage, independently observe the physical RD6018 Output state. PASS
requires Output to remain ON continuously and no local protection trip. Do not
use post-recovery telemetry as proof of uninterrupted ON.

Restore the network, then capture status. PASS after recovery requires:

- explicit AUTONOMOUS still true;
- Output still ON until deliberately turned OFF locally;
- managed lease remains absent/unarmed;
- no boot quarantine/trip was created by the outage;
- no PB controller/manual/adoption session was created;
- no bot-originated physical OFF occurred.

After evidence is captured, turn Output OFF **locally** and wait for fresh
canonical register-18 OFF evidence before the next phase.

## Phase E — ESP reboot persistence while AUTONOMOUS and Output OFF

Precondition: AUTONOMOUS true, canonical Output OFF, clean/unarmed managed
lease, Protection=0.

Perform an ESP-only reboot/power-cycle using the already-approved bench method.
Do not reboot/power-cycle RD6018 itself unless ESP cannot be isolated; a whole
PSU power-cycle is a different experiment and must be labelled as such.

After the edge is reachable again, PASS requires:

- explicit AUTONOMOUS persisted;
- managed session/lease did not become armed;
- managed boot quarantine did not activate in the non-conflicting autonomous
  state;
- Output remains OFF;
- no PB software session auto-restored or energized Output.

Then prove subsequent **local** generic-PSU operation still works by turning
Output ON from the RD6018/local edge surface, observing it independently, and
turning it back OFF locally. Confirm fresh canonical OFF before continuing.

## Phase F — production AUTONOMOUS exit

With canonical Output OFF, run:

```bash
python tools/physical_test_autonomous_client.py exit
python tools/physical_test_autonomous_client.py status
```

PASS requires:

- edge AUTONOMOUS false;
- manager-observed AUTONOMOUS false;
- software ownership returned to PB_MANAGED idle;
- edge generation advanced;
- Output remained OFF throughout;
- lease remains clean/unarmed until a future legitimate managed Output enable;
- V/I/OVP/OCP readback unchanged;
- no saved charging session was implicitly resumed.

## Previously proven managed lease-loss gate

The 2026-09-02 D056 physical evidence already demonstrated fail-closed managed
lease loss on the then-deployed edge: stopping the bot caused real Output OFF at
roughly the 15-minute lease boundary, and service restore did not re-enable the
Output.

Reuse that evidence only if the executor can establish that the relevant
lease/watchdog firmware contract is unchanged. If not, classify the managed
lease-loss gate as needing revalidation. A repeat, if explicitly chosen, must
use the same no-battery/benign-load discipline; do not silently substitute a
live battery test.

## Gates that must not be improvised

### Torn transition / power loss during enter or exit

Do not attempt a hand-timed race or random power cut. Without a deterministic
safe transition hook, classify this as `BLOCKED_NOT_DETERMINISTIC`. A future
hook must be reviewed separately and must not create arbitrary power/actuator
authority.

### Local intrinsic protection at 55C / raw hardware protection

Do not heat the PSU to 55C or intentionally provoke OVP/OCP merely to close a
documentation checkbox. Search for exact-hardware/exact-firmware physical
evidence first. If none exists, leave this gate pending until a separately
approved safe procedure exists.

## Cleanup

Before leaving the bench:

1. obtain and independently verify physical Output OFF;
2. exit AUTONOMOUS if it is still active and verify PB_MANAGED idle;
3. verify no active AUTO/Manual/adopted session;
4. verify managed lease is clean/unarmed;
5. restore all network isolation;
6. disable `RD6018_PHYSICAL_TEST_CONTROL` and restart the bot if activation
   required a service restart;
7. remove/verify disappearance of the AF_UNIX test socket;
8. restore the pre-test service environment/configuration;
9. capture final status/logs.

Do not merge any PR and do not modify/flash ESPHome as part of cleanup.

## Required report

Create a dated evidence document under `docs/assistant/` on a branch based on
the tested PR #24 head. Include a matrix for phases A-F and each residual gate,
with exact evidence and no inferred PASS.

If a product defect is reproduced, first return the bench to the safe cleanup
state. Then report the exact defect boundary. Do not conceal it by increasing
timeouts, weakening fail-closed rules, or adding an alternate actuator path.
