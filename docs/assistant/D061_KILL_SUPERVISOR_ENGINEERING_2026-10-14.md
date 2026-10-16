# D061 active adopted SIGKILL — supervisor engineering and OFF-channel physical validation

**Status: ENGINEERING PASS / ENERGIZED SIGKILL PHYSICAL HOLD.** This is not approval to kill an adopted charging session. No installed node104 production bot/firmware or battery settings were modified.

## Completed on the dedicated WSL2 worktree

Branch `fix/d061-physical-kill-supervisor-20261014`; isolated source `/home/home-pc/rd6018-d061-kill-supervisor-20261014`.

- New opt-in `tools/acceptance_guard/kill_supervisor.py`: exact existing-inode root-owned 0600 `flock` ownership; rejects changed PID/cmdline/start tick/cgroup/staged file hash and production bot identity; stages `PREARM / ADOPTED_CONFIRMED / KILLED / OFF_PROVED / LEASE_DISARMED / RESTORE_ALLOWED / FAIL_CLOSED`. Exact canonical set of 19 post-adoption proof predicates, not an arbitrary 19 booleans.
- New `tools/acceptance_guard/independent_off.py`: HA and native OFF callbacks plus separate source-fresh 0V/0A proofs, raw protection normal and edge lease disarm/generation proof; returns fail closed otherwise. It currently depends on external callback adapters and does not enforce its own per-callback wall-clock kill.
- New `tests/test_d061_kill_supervisor.py`: 12 hardware-inert tests for exact lock inode exclusivity, symlink rejection, child PID identity/reuse and production guard, real isolated subprocess SIGKILL, OFF/lease proof, stale/mismatched data, no OFF, restoration inhibition and cancellation. Its fake process is *not* node104 or the production bot.
- Worktree full unittest using dedicated WSL2 virtualenv with dummy HA/TG/ESP env: **1749/1749 PASS**. Focused supervisor regression: **12/12 PASS**. Installed production code and the accepted 899-file source/overlay remain unchanged.

## Independently actuated actual hardware OFF test (2026-10-14 15:08:40 UTC)

Separate pinned-SSH temporary script on node104: SHA-256 `17b12494c0782b53ec87e6ff857170ce9d949f6a9744ce070cf4c9b1c9271ed3`. Before any command, independently proved already-OFF via HA102 and native ESP128, 0.00V/0.00A, Vset13.57V/Iset0.10A/OVP14.07V/OCP0.20A, native lease unarmed/no trip/quarantine, original production ACTIVE PID59725/NRestarts0. Sent *real* HA `switch/turn_off` and real ESP native `switch_command(off)` using separately connected transport clients (not the production bot connection), then independently re-observed native `SensorState` (age 0s) and HA 0V/0A. All PASSED; after-run independent pinned-SSH repeated unchanged Output OFF, settings/lease and original production PID. No ON command, no charging, no power fault induced. **This proves two real OFF actuation paths in OFF-state; it does not prove OFF latency, availability or disarm after crash while ON.**

The first attempt was blocked before OFF actuation because the installed runtime ESP transport lacks the newer `get_physical_output_report` method. The proven second script uses the actually installed native subscribed `SensorState` callback metadata. Do not substitute GitHub current API for deployed API unverified.

## Remaining physical acceptance gates — not passed

1. **Actual detached independently supervised root service** (e.g. one reviewed systemd unit) must own the same global inode lock **before** Output ON, survive loss of the adopted child's PID, SSH, HOME-PC and bot, and retain ownership through containment. Currently the original acceptance child itself grabs the global lock, so the new parent cannot run concurrently without a separately reviewed same-open-description FD delegation/child handshake. No such runtime integration exists.
2. **Real bound on failures**: synchronous Python callbacks may block indefinitely despite a logical 44-second deadline. All real HA/native commands and fresh proofs require enforceable external timeout boundaries and a watchdog-on-watchdog / independent physical emergency cutoff for supervisor death.
3. **Exact child identity and canonical live adoption** must be verified against the 899-file staged source, live production process inventory and 19/19 freshness predicates in the detached service, not fake-based Python tests alone. All stages need byte-pinned receipt with PID, cgroup, monotonic OFF latency, disarm generation and ownership retirement.
4. **Canonical software ownership recovery** after asynchronous SIGKILL is not wired; only after dual-independent physical OFF, native lease DISARMED and authenticated owner retirement may the normal production service restart. If any check fails, leave it inactive and use emergency cutoff.
5. Actual **electrical OVP/OCP/OPP** register-16 trips require an isolated load, not the connected Leoch battery. OOB upward authority-change checks V/I/OVP/OCP already have separate physical PASS and do not test electrical trip.

**Current disposition:** Keep production node104 safe and operational. Treat the supervisor code as hardware-inert *foundation only*. Do not report an active adopted-bot physical SIGKILL PASS until these exact gates and real transaction succeed.
