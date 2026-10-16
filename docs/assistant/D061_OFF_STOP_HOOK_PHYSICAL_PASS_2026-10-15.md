# D061 — real independent systemd ExecStopPost OFF-only PASS (2026-10-15)

**Physical scope:** node104 real RD6018, production untouched; original battery connected. This is a real **already-OFF** fail-unit test, **NOT energized adopted-child SIGKILL**.

At **2026-10-15T02:57:19Z** pinned SSH verified production `rd6018-bot.service` ACTIVE, PID **59725**, NRestarts0; independent HA102/native ESP128 valid Output **OFF 0V/0A**, settings Vset13.57V/Iset0.10A/OVP14.07V/OCP0.20A, protection NORMAL, lease DISARMED (untripped, not quarantined).

Exact acceptance-only transient package **SHA256 `a5065fb4d5c7276dc6dd2d4a559b33e440d8852f0cf22ee9c10278837f09055d`** containing `stop_off.py`, `hardware_off.py`, `bounded.py`, `transient.py` (no production modules replaced) was copied to a root-owned temporary `/run/d061-stop-hook-smoke-...` staging location. A **temporary systemd-run service** `d061-stop-hook-smoke-a5065fb4d5.service` intentionally executed `/usr/bin/false` (ExecMainStatus=1). Its real `ExecStopPost` started a fresh independent root/venv Python process using the actual production `EnvironmentFile`, staged PYTHONPATH and exact node104+run identity, and invoked physical HA OFF and ESP native OFF, fresh dual-source OFF readbacks and native safety lease disarm verification. Real systemd recorded:

- `ActiveState=failed`, `Result=exit-code` (intentional main-process failure);
- `ExecStopPost ... pid=61171; code=exited; status=0`;
- journal text **`D061 independent HA/native OFF and lease disarm verified`**;
- ExecStopPost runtime 02:57:26→02:57:32 UTC.

At **02:57:34 UTC** independent pinned read-only postprobe PASS: production remains **ACTIVE PID59725 NRestarts0**, HA/native Output OFF 0V/0A, original V/I/OVP/OCP intact, lease DISARMED, raw protection NORMAL. Temporary bundle and uploaded tar removed and failed transient unit reset; no persistent systemd unit installed, no production restart or firmware change.

Separate pinned real-hardware direct adapter `hardware_off.py` OFF-only selftest PASS at **02:43 UTC**; its source SHA256 at that run `843becd3da673b19bdd103506a13aa67f4e1d6b6810145169290e223957a4ac9`. Later revised OFF adapter package above is the one actually used in this systemd test. Native disarm firmware does **not** necessarily advance generation; verified via actual ESP firmware contract and real 55→55 idempotent OFF state. The new adapter uses native subscribed `SensorState`, not nonexistent deployed methods.

**Regression:** full WSL2 suite **1765 tests PASS**, 2 root-only skipped in unprivileged full invocation; focused **28/28 PASS** when run as root with no skips. Root-run `systemd-analyze verify` of the uninstalled template **PASS**. Production `rd6018-bot.service` original code and ESP firmware unmodified.

**Still OPEN:** true physical SIGKILL of an **energized, PB_MANAGED adopted test child**, including 19/19 fresh proof at kill edge, sole ownership/FD handover and termination of all child threads/processes, independent OFF+lease generation/readback, orphan ownership retirement and restart verification. The current `acceptance_child.py` is deliberately fail-closed and does not yet implement the actual adopted test. Real hardware OVP/OCP/OPP trips require isolated load, not battery.
