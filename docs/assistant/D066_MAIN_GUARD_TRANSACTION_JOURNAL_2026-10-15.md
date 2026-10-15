# D066 — MAIN Guard canonical journal and execution-owner transaction

Status: **SOFTWARE ONLY / NOT CALLED BY PRODUCTION / PHYSICAL OPEN**.
Parent: issue #80. This gate follows merged D065/MAIN policy (PR #78/#79);
it does not supersede D061 physical SIGKILL acceptance or D063 positive SAFE_WAIT.

## 1. Exact owner and safety boundary

The accepted production runtime already creates its sole output execution port
via get_or_create_execution_port; its ordinary stage setpoint path delegates
to ExecutionPort.apply_current_with_ocp. A change to that method alone is not
an authorized MAIN Guard: by itself, it returns no independently durable ACK.

New opt-in ExecutionPort.execute_main_current_guard_reduction delegates to
application/main_guard_transaction.py. There is deliberately NO production
caller, no service change, and no new standalone hardware writer.

The transaction accepts a pending MainCurrentGuard from one explicit EFB/Ca/Ca
MAIN session and a MainGuardAuthority with matching session, battery, segment,
MAIN stage, owner authorization and active Edge Safety Lease. It requires
fresh independent register-18 ON, actual current, current setpoint register,
OCP register and protection-code data. Legacy set_current/ocp mirrors cannot
substitute for stale native V2 readbacks.

It verifies the previous acknowledged ceiling and physical OCP margin BEFORE
any write. It persists the pending proposal before touching Iset/OCP, then
uses the existing ExecutionPort.apply_current_with_ocp protected reduction
sequence (Iset reduction, then OCP reduction), checks native live register
readbacks again, commits MainCurrentGuard only after valid ACK, and persists
the committed ceiling. Failures, readback contradictions, journal failures,
timeout and ambiguous command outcome request verified OFF. Failed OFF is
explicit, not a successful containment receipt. There is no upward-current
or voltage path in this transaction.

The current assumed old/new OCP margin is 0.1 A; it must be verified and
calibrated on the exact hardware against actual noise before actuation.
An active owner-wide lock is REQUIRED. The existing production controller
must actually share that lock across all setpoint and session writes;
supplying an unrelated lock from a caller is not sufficient.

## 2. Canonical, monotone session checkpoint

The new pure module runtime/charge/strategy/main_guard_session.py defines
main_current_guard_v1 nested under existing charge_session.json. It binds
session_id, battery_id, profile EFB/Ca/Ca, capacity, stage, segment, and
versioned revision; checks SHA256 integrity and validates the Guard snapshot.
A missing checkpoint cannot silently create a fresh 0.1C current authority.

Journal replacements are atomic on one filesystem via same-directory
temporary file, fsync, os.replace and parent directory fsync. A caller must
already hold the canonical session/actuator lock. Revision mismatch, identity
change, ceiling enlargement, rewritten pending proposal, erased unacknowledged
pending, sequence rollback and unauthenticated new MAIN segment are rejected.

**IMPORTANT OPEN INTEGRATION:** The current deployed controller's legacy
save_session writer initially overwrites the JSON directly, followed by a
second trace identity rewrite. The new writer is NOT safe to run concurrently
with that legacy writer. Before granting any actuator authority, integrate
all production session commits and output updates into ONE lock and atomic
serialized source-of-truth, and ensure recovery loads the saved guard BEFORE
any new ON decision. Do not replace the production file from a sidecar.

There is intentionally no implicit DESULFATION to MAIN limit reset in the
journal helper. Such a new epoch requires independently verified real Output
OFF, historical guard reconciliation, I0 and OCP readback, plus explicit
owner transition receipt, all in a single ordered transaction.

## 3. Software evidence and remaining gates

Tests cover guarded positive reduction, order and durable pending/ACK,
register freshness, protection fault, wrong session/lease/owner, OCP margins,
ambiguous Iset write, failed OFF, pre/post-write journal exceptions, prior
ceiling mismatch, output ON metadata uncertainty, journal integrity,
revision checks, pending changes, and simulated restart. Tests are offline:
mocked execution owner / temporary session file; **no electrical testing**.

Before production activation:
1. Ensure one locked persistence + execution owner with crash recovery and
   checkpoint bridging into real charge_session.json; no racing old writer.
2. Select a justified maximum observation interval from actual live polling,
   then prove no unknown MAIN time accrual across telemetry gaps.
3. Characterize real Iset/OCP register resolution, transaction timing, and
   OCP margin. Verify fresh raw V2 readback independent of command ACK.
4. Verify D061 adopted PB_MANAGED child SIGKILL/retirement separately.
5. Run controlled physical reduction tests within existing **15.5 V** maximum,
   followed by emergency OFF/lease recovery proof. Never change MIX recipes,
   apply 17-17.3 V or classify software tests as physical PASS.

AGM unchanged. D063 physical SAFE_WAIT remains open. The EFB MIX diagnostic
still cannot authorize greater than standard MIX voltage on its own.
