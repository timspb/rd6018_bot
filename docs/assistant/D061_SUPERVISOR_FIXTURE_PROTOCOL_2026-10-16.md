# D061 supervisor fixture protocol — 2026-10-16

Status: **offline engineering fixture; no physical or node readiness implied**.

This sprint adds only `tools/acceptance_guard/fixture_supervisor.py` and its
hardware-inert contract tests. It is not imported by production, pairing.py,
the accepted node104 runner, or a systemd unit. It has no HA, ESPHome, SSH,
service-manager, or actuator adapter.

## Lock and child identity contract

The fixture supervisor opens one pre-created regular lock inode, validates its
owner, mode `0600`, and identity across `lstat`/`fstat`, then obtains exclusive
nonblocking `flock`. A production implementation must pin the owner to root
(UID 0); the offline test uses the current test account because it cannot
create a root-owned file. The supervisor retains the EXCLUSIVE locked
file descriptor; the child never inherits that open file description. The child
gets only the checked path and inode numbers, and can open an independent
descriptor without unlocking the supervisor (tested with an attempted LOCK_UN).
Passing a duplicate locked FD would let the child release the supervisor's
flock, so that earlier fixture protocol was corrected. Existing/stale READY
markers fail closed. A competing acceptance attempt must fail on the inode.

The fixture only starts a file named `synthetic_child.py`. It binds the child
PID to `/proc` start ticks, exact argv, cgroup text, and SHA-256 of the staged
script, and rechecks that tuple before its test-only SIGKILL. The regression
then confirms the child exited, the supervisor still owns the lock, and a
contender remains blocked. No production runner or real bot process is
launched or signalled.

## OFF evidence adapter contract

The pure evaluator requires fresh reports with distinct source and report
identities. Both reports must say Output OFF, voltage/current within 0.02 of
zero, and raw protection `NORMAL`. Missing, stale, future, contradictory,
same-source, or malformed reports produce `HOLD` and never call disarm.

Only after dual-source OFF proof may the disarm callback run. It receives an
absolute monotonic cutoff no more than 45 seconds after entry. The independent
lease readback must then be fresh, from a third source, and report disarmed;
otherwise the result remains `HOLD`. Callbacks in a future real adapter must
honor the passed cutoff with transport-level timeouts. This fixture cannot
interrupt an unbounded synchronous adapter and therefore does not establish
an emergency OFF latency.

No independently credentialed OFF/readback adapter is available in this
checkout. This work therefore stops at an inert protocol and fault-injection
tests. OFF-unconfirmed remains HOLD. Physical D061 adopted-child kill/restart
remains blocked until a root-owned independent emergency OFF path is separately
implemented and physically proven within 45 seconds. No fake PASS is issued.

Focused fixture tests: **9/9 PASS** on Python 3.12.3, including a
synthetic child's ineffective independent-descriptor LOCK_UN and stale
handshake-marker rejection. Source compileall and git diff --check: **PASS**.
Separately repeated full WSL2 unittest discovery with the canonical test-only
environment: **1914/1914 PASS (73.391 seconds)**. The earlier timed-out
discovery run is superseded; this remains offline fixture evidence only.

The accepted pairing.py source pins, accepted runner, live service units, and
production owner are unchanged. The 900-second lease contract is unchanged.
