# B1057 — node104 Native Output ABI: live incident and correction contract

Date: 2026-11-27. Scope: read-only diagnosis; **no firmware flash, hardware commands, service restart or release activation**.

## Production evidence

Installed bot B1056 source 53ad3df, D144 slot24 COMMITTED, service PID 426019 (observed 2026-11-27). Operator START 16:50:27+10 on saved Leoch Ca/Ca 72 Ah Diagnostic profile, target 14.70 V / 7.20 A:
- 16:50:29/30 V/I write calls returned; 16:50:34 programmed readback step returned.
- 16:50:35 managed lease acknowledged armed=true, generation=1, remaining 899.52 s.
- 16:50:35 Native Output ON failed: `ESPHome static output command action is unavailable`.
- 16:50:36/43/46 OFF command paths also reported the same missing action, despite fresh independent R18=OFF observations 16:50:40 and 16:50:45.
- 16:50:42/46 lease disarm confirmed; D084 recovery quarantine `start_enable_off_receipt_invalid` retained.
- Separate fresh D106 `--phase-observation` directly on node104 established Native `output_state_code_v2=0`, `output_voltage=0`, `output_current=0`, each typed SensorState, ages ~0.50–0.56 s. Normal D106 trial refused the active/ambiguous START_PENDING document (expected).

Read-only ESP Native inventory acquired through existing pinned node104 SSH, installed Python 3.11 venv, existing service environment, single temporary ESPHomeTransport connection:
- device firmware: `timspb.rd6018-pb-recovery-v2 / 2.3-ha-canonical` (observed in immediately preceding D106);
- `list_entities_services()`: **services_count=0**.
- Present: `SensorInfo(output_state_code_v2)`, output V/I sensors, `SwitchInfo(output)`, lease buttons and sensors, `TextSensorInfo(firmware_canonical_release)`.
- Missing: required `rd6018_output_command(request_id: string, enabled: bool)` and every other API action.

The installed source `runtime/physical/transports/esp128.py:672-684` explicitly requires `rd6018_output_command` in `self.services`; it rightly refuses to dispatch when absent. Neither a spelling/timeout change nor a `SwitchInfo(output)` fallback can satisfy request-ID-correlated APPLIED/REJECTED terminal receipt semantics.

## Provenance and diagnosis

`esphome/rd6018.yaml` declares `api.actions: rd6018_output_command`, but currently declares project version `2.2-autonomous-authority`, not the installed `2.3-ha-canonical`. Canonical checkpoint section `AD051-R3 final HA102 acceptance — 2026-11-14` records actual HA102 Validate/Compile PASS of a minimal production 2.3 overlay, **firmware install/upload/OTA/flash NOT performed at that gate**. Later actual firmware deployment status must be established from device/install records; the authoritative present-day API inventory alone proves the required command is absent.

Immediate root cause of START failure: **deployed firmware API lacks the mandatory AD051 Output command contract expected by Python B1056**. Contributing integration gap: START proceeds through physical V/I programming and lease arm before rejecting missing mandatory API action; the source's `get_capabilities` does not validate the firmware contract. Absence of correlated OFF/APPLIED receipt explains why physical R18 OFF did not suffice to release D084; do not bypass D084.

## One-owner systemic remediation (not a workaround)

1. Reconcile canonical HA102 2.3 firmware source and generated binary with versioned app-required API contract: name, request_id/target parameters, output status TextSensor, terminal receipt and single-R18 queue/fence; preserve all existing other firmware capabilities and local RD6018 autonomy.
2. Add a minimal contract probe **inside existing ESPHomeTransport/ExecutionPort admission**, before any START setpoint/lease write. Validate live Native service identity and required entity/status inventory, not firmware version string alone. Return a typed unavailable outcome with zero physical writes and no false START_PENDING. No second control implementation, alternate output switch, new manager/store/lease or bypass.
3. Source-test negative cases: zero services, wrong service name/args, no terminal status entity, reconnect/generation changes, OFF/ON receipt cancellation/failure, rollback/quarantine and zero preflight side effects. Existing single owner remains authoritative.
4. Build source-paired HA102 firmware, audit exact 1 MB ESP8266 OTA headroom, rollback/serial recovery, no active session and fresh ESP Native OFF+0V/0A, disarmed lease/R16 safe; **do not OTA while D084 pending remains unresolved**. Source/CI PASS is not hardware acceptance.
5. On authorized supervised firmware acceptance, verify new live Native service inventory and same-owner OFF/ON terminal receipts with exact physical R18 evidence. Reconcile START_PENDING using existing owner, never edit the recovery file directly. Then single operator START and STOP, validate V/I readback, R18, lease and native causal receipts.
6. Close P3/P8 only on actual physical evidence. Until then production remains B1056 slot24, quarantine preserved and no further START.

No OVP/OCP software protection logic change. Lease TTL remains 900s. This document records a release defect, not permission for unattended Output/OTA.
