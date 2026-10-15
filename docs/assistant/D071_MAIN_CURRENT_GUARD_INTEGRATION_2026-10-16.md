# D071 — MAIN Current Guard production integration status

**Status: OPEN — shared ExecutionPort serialization is implemented; full owner
and restore proof is still missing.** This note records the D071 source sprint
review at `299a38d8aa0fa062d04b8c99f1cda379bdf31959` and its implementation
follow-up.
No hardware, Home Assistant, service, node, D061 worktree, or remote GitHub
operation was performed.

## Existing safe boundary

The pure ratchet, hashed `main_current_guard_v1` journal, protected downward
Iset/OCP transaction, task-reentrant lock primitive, and MAIN pre-ON assessment
are present. `runtime/charge/persistence.py` currently holds any session that
contains the Guard key before controller mutation or age-based deletion. That
hold includes malformed and pending journals. Keep it until a production owner
can restore and reconcile the exact checkpoint. A Guard checkpoint must never
be deleted or replaced with an initial current limit on failure.

## Exact unproven edge

`get_or_create_execution_port()` now creates/reuses one app-scoped
`GuardExecutionOwnerLock` and binds it to the canonical port. Normal port
transactions (enable, intent, controller action batches, phase protection,
current/OCP operations and individual regular setters) take that same
task-reentrant lock. Nested calls do not deadlock. `request_verified_off()`
remains independent of this potentially occupied lock. The Guard reduction
transaction also enters the same lock through its bound port.

**Static production gate: OPEN.** `execute_main_current_guard_reduction()`
still has no production caller. Do not add one or activate MAIN current
ratcheting yet. The lock covers only mutations that route through this port.
Telegram START/preflight/controller/session mutation and startup restore
reconciliation are not yet one demonstrated transaction with the canonical
session file; shutdown and synchronous controller checkpoint paths also need
owner proof. Manual and recovery must be confirmed to use the exact same
app-scoped port on every write path. The Manual execution boundary now rejects
a raw owner or an unbound port, so it cannot create a private execution port
and imply shared serialization. Any other bypass remains a gate, not inferred
coverage from binding the lock.

Therefore Guard activation could still race an out-of-port state/session path;
the pending journal, physical readback, and subsequent monotone commit would
not be proven indivisible with that owner. Do not activate a Guard proposal
until those paths are brought under and tested against the canonical owner.

The remaining integration must preserve an independent urgent verified-OFF
route, must not apply a Pb guarded-ON veto to explicit `HANDS_OFF` operation,
and must retain D061 live-adoption ownership semantics. A failed or ambiguous
Guard transaction must not erase its journal. MAIN-only EFB/Ca/Ca applicability
does not authorize AGM changes, MIX voltage escalation, or automatic enablement
after restart. Source tests are not physical validation; the separately
authorized physical ceiling remains 15.5 V and was not exercised here.

## Validation evidence

- Focused existing offline Guard/restore suite: 97 tests passed.
- `compileall -q .`: passed.
- The corrected pre-change full-suite baseline is **1893/1893 PASS** with
  `TG_TOKEN=12345678:abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789`
  and `HA_TOKEN=dummy_test_only`.
- Implementation follow-up: focused lock/Guard/execution/START/Manual
  **51/51 PASS**.
- The follow-up full discovery was run with the canonical venv and requested
  dummy credentials. It fails at the autonomous resource-lifetime test: its
  nested composition tests print `ok`, but the child process does not exit
  within its 30-second teardown timeout. Running the nested module directly
  reproduces the timeout. Full suite result is **not PASS**.
- `compileall -q .` and `git diff --check`: PASS.
- CI for this exact branch HEAD is not yet verified; separate Python 3.10/3.11/3.12
  CI and an exact remote-head checkout are required before source-only merge.
- No physical PASS is claimed. Main current-ratchet activation remains OPEN.
