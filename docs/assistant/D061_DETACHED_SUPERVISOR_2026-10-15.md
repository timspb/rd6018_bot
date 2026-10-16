# D061 detached supervisor integration

Status: **hardware-inert integration work complete; energized SIGKILL remains blocked.** Nothing here authorizes deployment, service installation, systemd invocation, or a physical acceptance run.

## New components

- `tools/acceptance_guard/detached.py` acquires the existing root-owned 0600 lock through `GlobalLock`, passes the same open-file-description FD to its child, and provides a narrow `pairing.node104_acceptance_gate` adapter. The adapter checks FD/path inode, owner and mode and does not reopen/relock. The parent retains its FD until the child exits. No existing accepted D061 file was edited.
- `tools/acceptance_guard/bounded.py` forks an isolated worker for each emergency callback, closes inherited descriptors in the worker, and kills/reaps a callback that exceeds its wall-clock budget. Callback time shares the enclosing deadline through `DeadlineCallbacks`.
- `verify_live_adoption_proof` rejects unknown/missing source keys, boolean-only or duplicate/forged checks, stale/future per-check timestamps, non-increasing epochs, and proofs not bound to PID, start time, argv, cgroup and staged-source hash. `verify_child_at_action` rechecks process and stage identity at the action boundary.
- `rd6018-d061-detached@.service` is an uninstalled opt-in template with systemd watchdog/runtime bounds, `NoNewPrivileges`, restrictive filesystem/process settings and an `ExecStopPost` hook. `KillMode=process` leaves the accepted child for the independent containment path to handle if the supervisor exits. The template has no restart policy and does not launch the production bot.
- `stop_off.py` and `acceptance_child.py` deny by default. The stop helper does not restore production. No physical callback provider, production restoration adapter, or credentials are present.

## Validation and unresolved acceptance gates

The hardware-inert tests exercise exact proof key sets, evidence freshness/epoch monotonicity, callback hard timeout and worker FD closure, systemd template controls, stop-helper denial, and the inherited lock inode remaining exclusive after child exit. Existing accepted tests cover SIGKILL fake-child identity and OFF/lease proof fixtures. **Full WSL2 regression PASS 1757/1757** with 2 root-only tests skipped in the unprivileged invocation; the separate **root invocation PASS 8/8** with no skips, confirming the root-owned lock cases.

This is not yet a runnable physical acceptance transaction. No actual parent service or OFF adapter can be exercised here, and the stop helper intentionally denies even if an environment flag is set. The strict live proof validator is an available integration gate but is not wired into the old `KillSupervisor` API, whose accepted boolean predicate format remains unchanged. A separately reviewed parent bootstrap must call that validator at the action boundary, connect the exact staged proof source, and supply independently authenticated HA/native OFF, fresh OFF evidence, lease disarm/readback and owner-retirement adapters through bounded workers.

Further blockers remain: confirm systemd unit behavior on the exact deployment host; prove the staged adopted child cgroup/process-tree boundary; prove lock FD inheritance and parent-crash behavior under the deployment systemd version; implement reviewed OFF and owner-retirement adapters; then require dual-source OFF + lease + owner proof before any separate production restart mechanism. No claim is made that WatchdogSec itself turns output OFF. No node104, HA, ESP, network, firmware or hardware action was performed.
