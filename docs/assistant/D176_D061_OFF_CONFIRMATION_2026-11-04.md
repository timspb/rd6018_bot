# D176 — D061 verified-OFF confirmation and physical Mix stop (2026-11-04)

## Verified live evidence (read-only)
- node104 `rd6018-bot.service` remained `active` with zero systemd restarts during the incident investigation.
- `sensor_history` at 2026-11-04 12:44:53 UTC: 16.41 V / 3.06 A (~50.41 W); at 12:45:23 UTC: 16.41 V / 0 A / 0 W; by 12:45:54 UTC: 13.92 V / 0 A.
- `/opt/services/rd6018-bot/state/rd_live_mix_observer_v2.json` persisted `state=off_pending`, `mode=delta_then_off`, status `fresh Delta + 2h hold complete; verified Output OFF pending`.
- Independent subsequent HA readback: physical Output OFF, 0 V / 0 A, protection code 0, regulation code 0. This is post-event evidence, not a historical protection-code sample at the OFF edge.
- Code path `rd_live_adoption.py::_finish_verified_off()` persists `OFF_PENDING` before invoking `manager.operator_output_off`; the time/telemetry and stored state support Delta + two-hour hold initiating the OFF sequence. An exact acknowledgment/physical command trace at the edge was not recovered; do not claim historical readback proved it.

## Corrective code (offline only)
- Fix `rd_live_adoption.py`: `operator_output_off()` must return literal `True` before a `COMPLETED` transition; false/absent confirmation retains durable `OFF_PENDING` with explicit reason. Exceptions keep existing fail-closed behavior.
- Test fake now supports a non-raising `False` confirmation, with a regression that forbids completed state, false completion notice, and authority release.
- Focused `python -m pytest -q tests/test_rd_live_adoption.py`: **9 passed** on HOME-PC Windows Python. WSL system Python lacks aiogram/dotenv; its import failures are environment, not demonstrated code failures.

## Deployment and next steps
- Source branch: `fix/d061-off-confirmation`, based on `origin/main` e6a1fe0; separate worktree keeps original dirty checkout untouched.
- No production deployment, Output command, lease operation, service restart, recipe mutation, or direct edit to `off_pending` evidence.
- The live persisted `OFF_PENDING` needs a fresh owner-aware read-only reconciliation of physical OFF and exact D061 recovery behavior before any restart or handoff. Do not clear that file by hand.
- Hybrid Delta D175 (commit 5027ddf) remains an experimental CC/CV read-only algorithm on a separate lineage; compare it against current main before integration. Future full Dry Run must reuse existing recipe engine and emulate RD6018/ESP without actuating hardware.