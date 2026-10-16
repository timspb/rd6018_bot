# D061 independent supervisor — 2026-10-16 source candidate

Status: **OFFLINE SOFTWARE ONLY / NOT INSTALLED / PHYSICAL HOLD**.

This isolated branch ports the prior D061 supervisor foundation, single inherited root-owned acceptance lock, detached opt-in child launcher, systemd watchdog/ExecStopPost, and the independently constructed HA102 + native ESP128 OFF-only adapter onto current rd6018_bot main.

## Newly resolved
- The SIGKILL wait logic no longer mistakes a transient empty /proc/PID/cmdline for child death. It verifies the matching PID start time and the zombie state, or waits for procfs disappearance under its monotonic deadline.
- A different PID start time is always treated as reuse and fails closed.
- Hardware-inert tests cover persistent live PID, confirmed zombie, PID reuse, normal kill/verified-OFF order and failure containment.
- All of these changes are source-only; no command has been sent to node104 or hardware during this sprint.

## Remaining physical gates
- Install the supervisor and unit only via a separate, reviewed, byte-pinned acceptance bundle; current production and pinned older D061 runner are NOT silently replaced.
- Before any Output ON, establish the independent stop adapter's actual credentials/connectivity, the one global root-owned lock, watchdog ownership and the scoped child/PID/cgroup/source-hash handshake.
- Prove fault response by systemd/service termination and independent HA/native fresh Output OFF, zero physical V/A, raw protection NORMAL, lease disarm and generation, accepted ownership retirement, and exactly one restored production service.
- Demonstrate measured kill-to-confirmed-OFF within the accepted <=45s bound, including killed child, killed supervisor and failure-to-readback branches.
- Physical test authorization remains <=15.5V and requires existing bench cutout and supervision. Source or CI PASS does not count as D061 physical PASS.

No AGM or EFB/Ca/Ca charging recipe change, no Main Current Guard production activation.