# D111: RD6018 ESPHome 2.3 HA-canonical release candidate

This is a source-delivery/provenance release, not a new safety authority or a second RD6018 controller. The existing 900s edge lease, 300s managed renewal cadence, intrinsic RD-local OFF, OFF-only autonomous transitions, and D090 production app deployment gate remain unchanged.

## Source
- Canonical: esphome/rd6018.yaml plus four local packages under esphome/packages/.
- Version: 2.3-ha-canonical; minimum ESPHome builder 2026.9.1 (matches the observed HA builder).
- New read-only ESP Native text entity: Firmware Canonical Release.
- Compared with 2.2, safety packages and actuator code are BYTE-FOR-BYTE unchanged. Do not infer full D065 acceptance.
- Build uses actual HA secrets.yaml. It must not be replaced, exported or committed.

## HA source mirror / anti-downgrade
The authoritative builder source is **/config/esphome/rd6018.yaml**, not a Windows/WSL build artifact. All four !include package files must be mirrored there. The HA ESPHome dashboard will always rebuild this root YAML; merely flashing an OTA binary from WSL would leave the old 2.0 HA YAML and cause a repeat downgrade on next update.

Run the offline release staging utility to generate an immutable SHA256-locked bundle:
python tools/rd6018_ha23_release.py stage --source esphome --stage-dir /some/new/stage
Use its guarded HA-local install only with authorized /config/esphome filesystem access:
python tools/rd6018_ha23_release.py install --stage-dir /some/stage --ha-dir /config/esphome
The install checks existing HA secrets and device YAML, backs up old YAML/packages, does NOT modify secrets, copies packages then root, and finally checks all hashes. No OTA occurs in that tool. Its verify action must PASS before every future compile/update; a stale 2.0 or altered package fails hard.

## OTA gating (not yet closed)
Build exclusively on HA with ESPHome 2026.9.1 or later from validated root, keeping real HA secrets. Do NOT upload the offline validation binary built with throwaway secrets; it has no production Wi-Fi/API credentials.
Before any flash: newly acquire direct ESP Native R18 OFF, measured 0V/0A, R16 NORMAL, Vset<=15.5V, lease disarmed/remaining zero, no autonomous/trip/quarantine, fresh Modbus; check bot session and transaction state. Repeat fresh direct Native checks immediately before OTA and post-reconnect; HA102 only secondary. If Native unavailable, no flash. No unreviewed firmware/downgrade pin overrides.
Current HA REST token returns HTTP 401 for Supervisor add-on APIs; SSH root authentication at 192.168.1.102 denied, and Windows SMB config share absent. Therefore this work has NOT written files to HA or initiated an OTA. Do not mark HA sync/physical release PASS until privileged HA source write and post-flash Native evidence exist.

## Acceptance
Standalone D111 HA source install/downgrade regression tests, esphome config+compile on 2026.9.1 with dummy offline credentials, complete WSL2 Python suite, reviewed GitHub PR. Hardware D064/D065 and D109 1800s remain separate open physical gates.
