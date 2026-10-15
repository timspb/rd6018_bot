# D072 — START and manual setter owner serialization

**Source-only. MAIN Current Guard actuator remains disabled.**

Current production includes one app-scoped task-reentrant `GuardExecutionOwnerLock` on `ExecutionPort` (D071), but START controller mutation/preflight occurred before that lock, and the two Telegram manual numeric formats sent voltage/current through two independently locked calls. Both could interleave with another normal port command.

## Change

- `start_profile_transactional` now acquires the SAME application execution lock before inspecting active controller state, source evidence, pause retirement, configure/start, setpoint selection and canonical `ExecutionPort.enable`. Nested port access is task-reentrant; on any cancellation the lock is released. Urgent shutdown still uses its independent path, not the ordinary execution queue.
- The 30-second data_logger now holds the same app owner lock from controller tick and checkpoint through the resulting physical output action batch. An independent verified OFF still does not queue behind it.
- A single `ExecutionPort.program_voltage_current` operation locks the existing setter sequence. Both Telegram numeric variants use it, preserving original voltage-then-current order and individual acceptance results. It creates no ON authority and changes no voltage/current limits.
- Offline tests verify the production controller tick/action pair shares one lock, contended START preflight waits, paired V/I cannot interleave with an unrelated normal setter, urgent OFF is available during a held normal lock, same app lock reused, and both manual input routes use the pair.

## Still OPEN / no physical authorization

This does **not** make every code path one atomic transaction. Other controller mutations and session writes outside the tick/start transactions remain unproven. Startup/deferred/in-memory restore, Manual adoption, and lifecycle/stop also need one demonstrated lock/rollback owner and native readback/lease proof before a guard ratchet may be applied. The guarded-session legacy restore HOLD stays in place. D061 positive adopted-child SIGKILL under independent supervisor and physical current/OCP verification remain OPEN.

No production deploy, node104 change, electrical action, AGM recipe change or MIX >16.5 V change. Authorized physical ceiling remains 15.5 V for separately checked testing. Tests are offline and cannot prove actual OFF latency.
