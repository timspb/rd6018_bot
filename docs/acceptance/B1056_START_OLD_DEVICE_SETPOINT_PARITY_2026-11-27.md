# B1056 — P3 START parity failure: stale device setpoints

2026-11-27. GitHub issue #186. Disposition: SOURCE FIX TESTED, NOT INSTALLED, PHYSICAL P3/P8 HOLD (99/104).

## Real incident

Node104 B1053, source 656463fd1e6473708ecddeb0f4e3e0c17a878db4, D144 slot23 COMMITTED, PID 422174. Operator supervised Leoch Ca/Ca 72Ah, Output OFF, battery 12.69V, R16=0, lease unarmed, mode pb_managed. Telegram Diagnostic preview MAIN 14.7V/7.2A, 14.7V ceiling. At 2026-11-27 15:34:53 +1000 operator pressed v2_battery_start ONCE and received: START отменён до Output enable: detached/live canonical projection parity mismatch. Journal: two in-process ChargeController START log entries at 15:34:54, then STOP, no Output enable; charge_session.json absent after rollback; service remains active. Do not retry physical START on B1053.

Earlier 15:15 ESP Native TCP6053 connectivity errors are separately observed and are not the direct cause of the 15:34 in-process parity mismatch.

## Root cause reproduced without hardware

application/start_transaction_service.py creates a fresh detached candidate with device setpoint observations unset; existing live controller retains old observed physical OFF Vset/Iset = 2.4V/1.7A. The canonical runtime/charge/session_document_projection.py ordinarily prefers physical observed setpoints over profile target to preserve accurate historical restore. That generic rule incorrectly applies to a NEW pending session, so detached candidate projects requested MAIN target but live controller projects stale 2.4/1.7. Their document equality fails before any Output enable. Isolated FakeApp reproduction of old 2.4/1.7: started=false, persistence=ROLLED_BACK, enable not called, session file absent, identical user-visible error.

## Surgical B1056 code fix

Optional new_start_target=False in canonical projection; only two START_PENDING candidate/live pre-enable calls set it True. It selects the NEW program target, excluding stale old device readback or old session-file fallback. Ordinary persistence/restore retains its previous measured-readback precedence, and live physical observation variables remain untouched. The full live_document != candidate_document parity fail-closed gate, START_PENDING exact rollback, ExecutionPort owner, and safety/lease/Native proof requirements remain unchanged.

Three new regression tests: stale 2.4/1.7 off-device readback no longer blocks a new session and new target persists; a prior session-file target does not contaminate new session; ordinary non-START persistence still keeps physical Vset/Iset. Existing genuine parity mismatch injection still rolls back. Local 52/52 profile tests PASS; broader 232/232 safety/START/PENDING/restore/release tests PASS; git diff --check clean. Isolated fixed FakeApp: started=true, COMMITTED, new EFB70 requested/persisted 14.8V/7.0A and old physical observed 2.4V/1.7A retained. Not a physical START.

## Boundary

Requires GitHub CI, reviewed exact source candidate and safe node104 D145 install/acceptance before supervised physical START can resume. Existing installed B1053 remains unchanged. No service/ESP restart, hardware command, setpoint write, Output ON, or lease actuation occurred during the source investigation. P3/P8 HOLD 99/104.
