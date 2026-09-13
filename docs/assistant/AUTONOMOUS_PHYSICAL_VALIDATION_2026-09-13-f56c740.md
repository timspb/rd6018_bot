# AUTONOMOUS physical validation — 2026-09-13

## Tested baseline

- Target: node 101, explicitly authorized for this run
- Target authorization: explicitly approved by project owner for this validation run
- Hostname: `Deb11`
- Tested bot SHA: `f56c7407d9838ef9c5ed05e48aa01ad24a01b79b`
- `f56c740` is a descendant of PR #24 `b360533`; the physical-test client,
  control extension and actuator semantics are unchanged between those heads.
- Service: `rd6018-bot.service`
- ESPHome: already deployed firmware; no flash, OTA, YAML or package change
- Initial service PID after deployment: `2422578`
- Final service PID: `2423137`

## A — baseline / preflight

Result: `PASS`.

At the start of the timestamped run (`2026-09-13T06:13:36Z`):

- mode: `PB_MANAGED`
- Output: `off`; canonical `output_state_code_v2=0.0`
- protection code: `0.0`
- AUTONOMOUS: `false`
- lease: `armed=false`, `tripped=false`, `boot_quarantine=false`, remaining
  `0.0 s`, generation `18`
- direct Modbus freshness: about `1.4 s`
- programmed readback: `15.14 V / 7.20 A / OVP 16.70 V / OCP 12.00 A`

No active AUTO, Manual or adopted session was reported by the physical-test
status response. No battery chemistry session was started.

## B — production AUTONOMOUS entry

Commands used:

```text
python tools/physical_test_autonomous_client.py enter
python tools/physical_test_autonomous_client.py status
```

Entry started and was acknowledged at `2026-09-13T06:13:36Z`.

Observed:

- edge AUTONOMOUS: `true`
- manager-observed AUTONOMOUS: `true`
- software mode: `hands_off`
- Output: `off`; canonical readback `0.0`
- generation: `18 -> 19`
- lease: unarmed, untripped, no quarantine, remaining `0.0 s`
- protection code: `0.0`
- V/I/OVP/OCP unchanged
- `rd_actuator_writes_injected=0`

Result: `PASS` for the OFF-only AUTONOMOUS entry contract.

## C — local generic PSU operation

Result: `BLOCKED_NO_LOCAL_CONTROL`.

The execution channel had no physical RD6018 front-panel/local control access.
Output was not enabled through Telegram, HA, or the physical-test socket.

## D — Wi-Fi/HA loss with Output ON

Result: `BLOCKED_NO_INDEPENDENT_OBSERVER` / `BLOCKED_NO_SAFE_NETWORK_ISOLATION`.

Output was not enabled, and no network outage was induced. A continuous
independent physical observer and an approved reversible network-isolation
mechanism were not available through the execution channel. Outage duration:
`0`.

## E — ESP-only reboot persistence

Result: `BLOCKED_NO_APPROVED_ESP_ONLY_METHOD`.

No approved ESP-only reboot method was available through the execution
channel. No reboot, OTA, flash or firmware change was performed.

## F — production AUTONOMOUS exit

Commands used after fresh OFF confirmation:

```text
python tools/physical_test_autonomous_client.py exit
python tools/physical_test_autonomous_client.py status
```

Exit was acknowledged at `2026-09-13T06:13:37Z`.

Observed:

- edge AUTONOMOUS: `true -> false`
- manager-observed AUTONOMOUS: `true -> false`
- software mode: `hands_off -> pb_managed`
- generation: `19 -> 20`
- Output remained OFF; canonical readback `0.0`
- lease remained unarmed/untripped, remaining `0.0 s`
- protection code remained `0.0`
- programmed V/I/OVP/OCP unchanged
- `rd_actuator_writes_injected=0`

Result: `PASS` for safe OFF-only exit.

## Cleanup

- Temporary `RD6018_PHYSICAL_TEST_CONTROL=1` drop-in removed.
- Original service environment restored; `DropInPaths=` is empty.
- Service active/running with one bot PID (`2423137`).
- Physical-test socket absent.
- Final persisted control mode: `pb_managed`.
- No ESPHome or RD firmware change.

## Overall

`PARTIAL`: A/B/F passed. C/D/E remain blocked by missing physical execution
capabilities, not by a proven software, firmware or hardware defect. Local
focused AUTONOMOUS tests passed; the full Windows/Python 3.14 suite retains the
previously observed platform-specific failures and is not physical evidence.

No product defect was proven. Do not claim physical AUTONOMOUS readiness until
C, D and E are rerun with local control, independent observation, controlled
network isolation and an approved ESP-only reboot method.

## Final matrix

```text
A PASS
B PASS
C BLOCKED_NO_LOCAL_CONTROL
D BLOCKED_NO_INDEPENDENT_OBSERVER / BLOCKED_NO_SAFE_NETWORK_ISOLATION
E BLOCKED_NO_APPROVED_ESP_ONLY_METHOD
F PASS
CLEANUP PASS
```

## Evidence integrity and runbook drift

The command responses and service/readback observations were captured during
the run and summarized above. Full raw JSON response files and a separate raw
log bundle were not persisted to the repository; they are not reconstructed
after the fact. The repository runbook still contains an older blanket
prohibition against node 101. For this run that restriction was superseded by
the explicit project-owner authorization recorded above; this does not change
the runbook's other safety requirements.

## Post-run discovery

### ESP-only reboot discovery

Result: `BLOCKED_NO_APPROVED_ESP_ONLY_METHOD`.

Read-only HA inventory found no RD6018/ESP restart or reboot entity. The
ESPHome YAML/package tree contains no restart component or existing reboot
service for this node. OTA/reflash remains prohibited and would not be a clean
ESP-only reboot test. No reboot was performed.

### Independent observer and network isolation discovery

Result: `BLOCKED_NO_INDEPENDENT_OBSERVER` and
`BLOCKED_NO_SAFE_NETWORK_ISOLATION`.

Read-only HA inventory found no camera or independent external measurement
entity. The node has only `eth0` for the relevant LAN path; its nftables input
and output policies are `accept` and no approved reversible isolation rule or
mechanism was found. No network outage was induced.
