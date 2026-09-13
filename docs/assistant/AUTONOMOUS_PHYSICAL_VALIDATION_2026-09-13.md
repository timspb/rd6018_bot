# AUTONOMOUS physical validation — 2026-09-13

## Result

`PARTIAL`: A01 completed successfully. C–E require operator-controlled local
PSU access, an independent physical observer, and an approved ESP-only reboot
procedure; those capabilities were not available through the execution
channel. No inferred physical PASS is recorded.

## Tested identity

- Target: node 101 (`192.168.1.101`), explicitly authorized for this run
- Hostname: `Deb11`
- Bot SHA: `b360533516b8cbd3098f617e84074430f87e55fc`
- ESPHome firmware: already deployed firmware used; no flash or firmware change
- Service: `rd6018-bot.service`
- Test backup: `/root/rd6018-bot-backups/physical-validation-20260913T051724Z/`
- Initial service PID: `2255909`
- Final service PID: `2419126`
- Final service state: active/running

## A — preflight

### Evidence

- API/readback reachable through HA (`HTTP 200`), with fresh Modbus age about
  5 seconds.
- `rd_control_mode`: `pb_managed`
- `output_state_code_v2`: `0.0`; Output: `off`
- Protection code: `0.0`
- Autonomous: `off`
- Lease: `armed=false`, `tripped=false`, `boot_quarantine=false`, remaining
  `0.0 s`, generation `14`
- No active AUTO/Manual/adoption session was reported by the physical-test
  status path.
- Programmed values were read as `15.14 V / 7.20 A / OVP 16.70 V / OCP 12.00 A`.

### Result

`PASS` for software/edge preflight evidence. Physical load identity and
independent front-panel observation were not available in this channel.

## B — AUTONOMOUS entry

### Actions and evidence

The only transition path used was:

```text
python tools/physical_test_autonomous_client.py enter
python tools/physical_test_autonomous_client.py status
```

The returned entry result recorded:

- `edge_autonomous=true`
- `rd_control_mode=hands_off`
- `output=off`
- `output_state_code_v2=0.0`
- generation `14 -> 15`
- lease unarmed, remaining `0.0 s`
- protection code `0.0`
- `rd_actuator_writes_injected=0`

The following status readback matched: edge autonomous `true`, manager edge
autonomous `true`, Output OFF, canonical register-18 OFF, lease clean and
protection normal.

### Result

`PASS` for the A01 entry contract.

## C — local generic PSU control

`BLOCKED_NO_LOCAL_CONTROL_SURFACE`: the execution channel had no physical
RD6018 front-panel/local control access. No Output ON command was sent through
Telegram, HA, or the physical-test socket, and no battery chemistry session was
started.

## D — Wi-Fi/HA loss with Output ON

`BLOCKED_NO_INDEPENDENT_OBSERVER`: Output was deliberately not enabled because
the required independent physical observer and a controlled reversible network
isolation mechanism were unavailable. No outage was induced.

Actual outage duration: `0`

## E — ESP-only reboot persistence

`BLOCKED_NOT_DETERMINISTIC`: no approved ESP-only reboot method was available
through the execution channel. No reboot, OTA, flash, or firmware change was
performed.

## F — AUTONOMOUS exit

After A01, Output was still confirmed OFF, so the same physical-test control
plane was used:

```text
python tools/physical_test_autonomous_client.py exit
python tools/physical_test_autonomous_client.py status
```

Evidence: autonomous `true -> false`, manager edge autonomous `true -> false`,
generation `15 -> 16`, `rd_control_mode=pb_managed`, Output OFF,
`output_state_code_v2=0.0`, protection code `0.0`, lease unarmed, remaining
`0.0 s`, actuator writes injected `0`.

Result: `PASS` for safe exit/cleanup transition.

## Cleanup

- AUTONOMOUS exited through the physical-test client.
- Final Output/readback remained OFF (`0.0`).
- Final autonomous state was OFF; generation `16`.
- Final lease was unarmed/not tripped; boot quarantine was false.
- Temporary `RD6018_PHYSICAL_TEST_CONTROL=1` systemd drop-in was removed.
- Service was restarted with the original unit configuration and is active.
- Physical-test socket is absent.
- Final service PID: `2419126`.
- No ESPHome flash or configuration change was performed.

## Residual gates

| Phase | Result | Evidence / blocker |
|---|---|---|
| A preflight | PASS | Fresh readback, canonical OFF, clean lease/protection |
| B entry | PASS | ACK, generation advance, autonomous manager/edge state |
| C local PSU | BLOCKED | No local physical control surface |
| D network loss >=6 min | BLOCKED | No independent observer; Output never enabled |
| E ESP reboot | BLOCKED | No approved deterministic ESP-only reboot method |
| F exit | PASS | Safe OFF-only exit and status |
| Local intrinsic safety | PENDING | No approved safe procedure to provoke faults |
| Managed lease-loss repeat | NEEDS_REVALIDATION | Not repeated in this run |

## Classification

No software, firmware, hardware, or operator defect was proven. The blocked
phases are execution-capability/evidence blockers, not failures of the tested
runtime contract.
