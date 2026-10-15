# D063 node104 standalone voltage-relaxation observer acceptance — 2026-10-15

Status: **INSTALLATION PASS; POSITIVE REAL SAFE_WAIT CAPTURE OPEN**.

Optional independent EFB/Ca-Ca observer installed from branch feat/voltage-relaxation-20261015.
Main rd6018-bot.service was NOT changed, stopped, reloaded or restarted.
AGM, MIX chemistry recipes, voltages, currents and ESP protection were NOT changed.

## Software verification
- Full WSL2 unittest suite: **1777 tests, OK**, duration 67.564 seconds.
- Pure engine: runtime/charge/observability/voltage_relaxation.py.
- Standalone reader: tools/voltage_relaxation_sidecar.py.
- Optional service: tools/rd6018-voltage-relaxation.service.
- Dedicated positive/negative provenance and restart tests: PASS.
- Production runtime/production_runtime.py unchanged relative to origin/main.

## Physical node104 installation proof
- Unit: rd6018-voltage-relaxation.service ACTIVE PID 62502; NRestarts=0, Result=success.
- Code: /opt/services/rd6018-bot/optional/voltage_relaxation.
- Independent database: /opt/services/rd6018-bot/state/voltage_relaxation.db.
- SHA-256 install bundle fingerprint: bd226ffd1e15f97c67.
- Engine SHA-256: 2346d23b70b4da36ef38a1d9a8a46b04d43c19356ce0220abb7e0b6640a57cd2.
- Reader SHA-256: f2108289a8b422b45528f59e3c53ffdf8a294de54c26542c09357d7c836adc51.
- Unit SHA-256: 1d00bc08ec2cf5a41a76080198944b57339e7b656774d4e19f58cd6a4c510a45.
- Staging and installed checksums PASS, systemd-analyze verify PASS.
- Live observer polls 2026-10-15 10:53:46 and 10:54:16: no_eligible_safe_wait.
- Current durable charge_session.json absent, diagnostic DB has 0 runs and 0 samples.
- This is the correct negative proof; no fake SAFE_WAIT was fabricated.

## Unchanged production acceptance
- Main rd6018-bot.service ACTIVE PID 59725, NRestarts=0, unchanged across install.
- HA and independent native ESP output OFF; 0 V, 0 A; Vset 13.57 V; Iset 0.10 A.
- OVP 14.07 V, OCP 0.20 A; PSU 29 C; battery terminal voltage about 13.06 V.
- Edge safety lease DISARMED; no hardware command issued by observer.

## What remains open
Real EFB/Ca-Ca SAFE_WAIT must occur naturally with fresh canonical Output OFF and
durable session evidence. Only then can the system record verified 5–15 and 15–60
minute voltage relaxation slopes; early SAFE_WAIT exit leaves windows incomplete.
AGM cannot generate samples. Physical voltage ceiling 15.5 V remains unchanged.

## Independent rollback
Disable only rd6018-voltage-relaxation.service using systemctl disable --now.
Do not stop or restart rd6018-bot.service to manage this optional observer.
