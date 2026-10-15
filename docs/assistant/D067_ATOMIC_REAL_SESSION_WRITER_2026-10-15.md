# D067 — real controller single-write charge-session serialization

Status: **software gate / source-only**, not node104 deployment.

Previously the controller's normal save operation wrote charge_session.json
directly and subsequently performed a second V2 trace identity os.replace.
That admitted an intermediate document with no real trace identity or MAIN
Guard checkpoint and would erase a previously persisted guard.

## Changed source semantics

- runtime/charge/session_atomic.py composes charge state, existing V2 trace
  identity, SAFE_WAIT continuation and optional MAIN Guard checkpoint in ONE
  document, then writes via same-directory temp, fsync, os.replace and
  directory fsync on Linux. Existing file mode is retained.
- runtime/charge/persistence.py uses this writer. A missing guard for an
  already guarded session is an explicit GuardJournalError; it is never
  silently recreated at initial 0.1C authority.
- charge_controller.py no longer invokes the redundant separate V2 trace
  rewrite after a regular _save_session. The existing restore/migration
  trace path remains separate until a later verified retirement.
- Runtime Guard remains OPTIONAL and has no production constructor,
  executor caller or activation. Ordinary unguarded sessions preserve
  accepted charge/AGM behaviors and continue to serialize trace metadata.

## Verification and limitations

Offline real ManagedChargeController serializer tests prove:
initial trace identity in the first committed document, session/battery
binding, monotonically revisioned guard retention, refusal to erase an
already guarded journal, refusal to import a previous session's guard, and
atomic rollback on failed os.replace. D063 genuine SAFE_WAIT serializer
tests continue to apply in the full regression suite.

**Not yet operationally enabled:** the runtime controller and the
ExecutionPort actuator owner MUST use one global lifecycle/execution lock,
and Guard restore/reconcile MUST happen before Output ON. This change
does not claim to serialize concurrent async output commands by itself.
A physically valid DESULFATION->MAIN reinitialization still requires
a fresh OFF and Iset/OCP hardware readback receipt.

Known physical authorization remains max **15.5V**. No change to MIX
voltages, EFB current chemistry criteria or AGM. D061 positive adopted
PB_MANAGED child SIGKILL and real D063 SAFE_WAIT remain separate OPEN.
