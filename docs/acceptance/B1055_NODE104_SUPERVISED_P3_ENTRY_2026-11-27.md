# B1055 node104 P3 supervised battery preflight — 2026-11-27

Disposition: **NATIVE BASELINE OBSERVED; BENCH ENERGIZED GATES NOT RUN / HOLD**. No new deployment or hardware actuation in this capture.

Source of physical telemetry: existing authorized HOME-PC WinSCP site 104, installed B1053 Python-only source `656463fd1e6473708ecddeb0f4e3e0c17a878db4`, D144 slot23 COMMITTED, systemd active and NRestarts=0, MainPID 422174. Existing `node104_d106_live_observer.py` trial OFF PASS at epoch `1795751529.5510907` (fresh Native, firmware `2.3-ha-canonical`, HA autonomous stale advisory preserved). Additional independent fresh read-only ESPHomeTransport subscription at epoch `1795751564.5403082` (2026-11-27T03:52:44.540Z), with D091 direct firmware identity validation and all measurement callback ages <=0.46 s:

| Native field | Observed value | Source/type |
|---|---|---|
| Output R18 | OFF / 0 | ESP Native SensorState |
| Measured U / I | 0 V / 0 A | ESP Native SensorState |
| **Battery voltage** | **12.69 V** | ESP Native SensorState, age 0.015s |
| Vset / Iset | 2.40 V / 1.70 A | ESP Native SensorState (not appropriate START targets) |
| Raw R16 | 0 | ESP Native SensorState |
| Temperature internal / external | 31 C / 25 C | ESP Native SensorState |
| OVP / OCP readback | 0 / 0 | Diagnostic only, not Pb software safety authority |
| Lease armed | false | ESP Native BinarySensorState |
| Lease remaining / TTL / generation | 0s / 900s / 0 | ESP Native SensorState |
| Lease tripped / boot quarantine | false / false | ESP Native BinarySensorState |
| Modbus age | 0.995s | ESP Native SensorState |

Under installed D091 read-only `_session_state`, charge session CLEAR/absent. Independent `_journal_state` recovery-quarantine CLEAR (retired journal present, not active). Current `state/rd_control_mode_v2.json` **`mode=hands_off`**. Verified existing operator HMI `rd_hands_off_disable` callback invokes `manager.return_pb_control()` and responds that Output remains confirmed OFF and old automatic session does not resume. Physical-test AF_UNIX socket absent. No arbitrary shell/ESP/Modbus or physical-test control action is available or used.

User confirmed a person present with emergency disconnect and battery physically connected. Historical accepted bench battery is Leoch Ca/Ca 72 Ah with Vset ceiling 15.5 V, normal 10s+ between ordinary ON/OFF transitions; **exact battery currently attached is not yet independently re-confirmed**. No inference from Vbat 12.69 V about battery model or safe charge target. Prior 2.4V/1.7A settings must not be used for a start. User has been asked to identify same Leoch Ca/Ca 72 Ah and select existing Telegram HMI **Return Pb control** while not pressing START until fresh follow-up proof and approved profile. No energized Gate2/3/4 action, OPP, lease expiry, or test socket activation was performed. Canonical 99/104 remains unchanged (P3 three physical HOLD, P8 two HOLD). This observation is **NOT** a post-command OFF proof.
