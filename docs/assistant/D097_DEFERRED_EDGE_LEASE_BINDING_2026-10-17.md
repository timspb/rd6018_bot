# D097 — production AUTONOMOUS coordinator deferred lease binding
Date: 2026-10-17. Source branch: fix/d097-deferred-autonomous-edge-lease.

## Observed live failure
The authorized, reversible node104 D097 status preflight returned:
`{"error":"AUTONOMOUS production coordinator unavailable","ok":false}`.
No enter/exit command followed, and the node remained Output OFF / 0 V / 0 A.
The original unit was restored, `DropInPaths=` empty and no test socket remained.
External report: `E:\CODEX\RD6018_D097_D065_PHYSICAL_ACCEPTANCE_REPORT.md`.

## Root cause and corrected owner
`ProductionComposition.compose()` constructs `RdAutonomousModeCoordinator` before
`ProductionComposition.run()` invokes `initialize_runtime()` to bind the
`_DeferredHassClient`. In `RdAutonomousModeCoordinator.__init__()`, an
unbound `StrictRuntimeSafetyGuard.edge_safety_lease` made `.edge=None`.
`StrictRuntimeSafetyGuard.ensure_edge_safety_lease()` can attach the normal
lease after the client is bound, but the coordinator retained its original None.
The root-only physical-test extension rejected `autonomous_status` after merely
checking `.edge`; it never called the coordinator's existing late-resolver.

The fix changes exactly two production modules:
- `rd_autonomous_mode.py`: `_require_edge()` lazily resolves the existing
  StrictRuntimeSafetyGuard lease **only after** its configured edge enforcement
  is active. It never creates a separate or unenforced authority.
- `physical_test_control_pb_mode.py`: before rejecting, status/enter/exit
  resolve the already-composed production coordinator through `_require_edge()`.
  A truly missing coordinator, missing lease or disabled enforcement remains
  fail-closed. No new socket, transition protocol or actuator pathway.

## Regression evidence
Added four tests in `test_rd_autonomous_mode.py` and
`test_physical_test_pb_mode.py` covering deferred binding, blocked enforcement,
successful late-binding status, and fail-closed unavailable status.
Focused local suite: **37 tests PASS**.
Full source suite and multi-Python CI must pass before merge.

## TelegramConflictError clarification
The only matched journal line was an **informational hint** dated 2026-10-14:
'Если появится TelegramConflictError ...'. No actual error was found
in the inspected 2026-10-17 D097 window. One live node104 `bot.py` PID
was observed. This does not prove the absence of other polling instances
on other hosts, but the available evidence does not support an active conflict.

## Release boundary
This change is code only: no node104 deployment, ESP flash, Output enable,
systemd override or D090 activation. D097 must be re-run under the normal
reviewed deployment procedure with fresh independent readbacks (including raw
register-16 and programmed V/I/OVP/OCP), and then the remaining D065/D064
physical gates remain separate. No physical PASS is claimed for this patch.
