# D139 — offline state-preserving transition, crash-boundary acceptance

## Scope and result

The existing D090 transaction's inventory, atomic-journal and durable-directory helpers are reused. D139 is deliberately **an isolated fixture harness only**, not a parallel production deployment owner or a production activation command.

On node104, `tools/d139_offline_transaction.py` and `tests/test_d139_offline_transaction.py` were executed from `/tmp/d139_fixture` with a fake service adapter. **7/7 tests PASS**.

- Candidate `app/` and `venv/` renamed into fixture install directories; original bytes durably copied into a rollback backup first.
- The D139 fixture ledger is separate from the D090 ledger. Its terminal fixture phase `RESTORED` is not a production release commitment.
- A single test covers **11 crash/fault points**, including the four critical intervals between directory renames and the next durable phase record.
- Rollback restores the exact preimage `app/` and `venv/` and leaves `state/` untouched, including data modified **after** simulated candidate service start.
- Legacy `D090_TRANSACTION.json` and `.deploy_sha` are never rewritten.
- Missing/corrupt rollback evidence fails before stopping the fake service.
- Execution requires a path under the host temporary directory, a fixture sentinel, and a service adapter explicitly declaring `d139_offline_fixture=True`. No production CLI route exists.

## Distinction from activation readiness

D138 has separately prepared a candidate (source `d351c208cbf8666f881a4660df6a0b211170e857`, 1209 files, Python 3.11 venv 10140 entries) with candidate identity SHA-256 `45b6ae0e2dc2f42ee76eaca8311178fd76f92e0254b63e60f3d7393ceee1979e` and matched D137 observed preimage `f8fa701e7362490fcdf61c5e2ab84664c950f3599f56c7eb2477434b603f874c`.

**This does not authorize a real cutover.** Production work still needs to integrate the transaction into one canonical owner with a distinct D139 ledger; verify fresh independently sourced electrical OFF, lease and recovery authority; validate exact durable candidate and rollback disk requirements; and prove full process binding. There is no D139 code path that stops the actual service or writes its marker. The historical D090 transaction remains `STARTED`.

Production node104 storage had ~402 MiB free after D138 candidate assembly. Full backup of live app and venv with sufficient rollback reserve has **not** been proved to fit, so no production cutover should occur at this disk level.

Physical RD6018 output and settings were never changed, and the 900-second lease remains unmodified.
