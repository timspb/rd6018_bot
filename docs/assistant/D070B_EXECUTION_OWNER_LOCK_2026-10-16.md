# D070b — In-process execution-owner lock primitive

**Scope:** software-only, not installed in production. Owner-wide locking and
physical acceptance are still OPEN.

## Reason

The currently accepted charge runtime has several independent paths that
mutate output and charging state: the background 30-second controller tick,
START, Telegram/manual setpoints, operator pause and resume, startup/deferred
restore, and safety-related shutdown. The existing RdControlMode transition
lock and runtime-safety OFF lock protect their own distinct domains; neither
covers the entire lifecycle/guard-journal/current/OCP transaction.

A regular asyncio.Lock passed as the new MAIN Guard execution lock is
insufficient if the same task calls another normal lock-taking port method
inside the protected transaction: it deadlocks. This module implements one
**task-reentrant** asyncio.Lock subclass with strict ownership, recursion
depth accounting, cancellation cleanup and cross-task exclusion. It can
satisfy the existing bound-lock type contract without silently creating a
different independent lock at each call.

It is NOT process-wide, not a PID/cgroup supervisor, and does not change
D061 physical acceptance ownership. The unbound production port remains
unchanged until a later approved integration explicitly binds this lock and
proves every relevant caller actually uses the same instance.

## Safety invariant

Urgent, independently verified physical OFF must NOT queue behind a
possibly stalled ordinary setter transaction. Tests demonstrate that an
emergency callback can run without the lock, but this is MOCK evidence,
not a measured OFF latency on node104. Do not bind the ordinary lock to the
standalone emergency OFF/Edge Safety mechanism.

## Next acceptance gates

1. Locate the single real runtime composition root. Bind one instance to
   controller/session/actuator owner, not separately to each route.
2. Wrap background stage decision, session save, normal setpoints, START,
   manual and recovery under this owner while avoiding nested deadlocks.
3. Prove restore-before-ON, native Iset/OCP freshness and verification,
   pending proposal disposition, and crash/restart safety with faults.
4. Keep independently verified physical OFF and Edge lease protection
   outside potentially blocked normal command scheduling.
5. D061 adopted PB_MANAGED child SIGKILL must be completed separately.
   Physical authorization max 15.5 V; AGM and MIX unchanged.
