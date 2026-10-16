# D073 — MAIN current guard shadow integration

**Source-only; production actuation and journal persistence remain disabled.**

`data_logger` now calls a production-owned `MainGuardShadow` inside the existing
D072 task-reentrant execution owner lock. The pure adapter observes only native
output current and native Output register-18 supplied by that logger with
jointly fresh source metadata. Missing/unknown register values break continuity;
legacy UI switch state cannot serve as Guard evidence. It uses monotonic time,
the guard's <=90 second continuity bound, and its `current + 1 A` downward
proposal equation after 1800 seconds of evidenced MAIN Output-on time. Pending
proposals survive a snapshot/restore round trip in the offline adapter.

Production requires explicit accepted-session identity attributes before it can
construct the guard. Those attributes are not currently published by the
accepted production session owner, so the hook safely remains inert. No default
session writer permission exists; no sidecar or partial canonical journal is
written. The code does not invoke current/OCP setters, Output ON, or the guard
transaction executor. AGM and MIX are excluded. Existing guarded restore HOLD
and D061 authority are unchanged.

Focused offline tests cover 30-minute proposal calculation, restart retention,
stale and >90 second gaps, cooling/OFF/stage break, wrong chemistry, missing
identity, no default writes, and placement inside the actual locked logger
scope. This proves source integration and pure software behavior only. **OPEN:**
accepted session identity publication, persistence owner authorization, guarded
restore journaling, and execution receipts/readback transaction integration.
No physical or deployment validation is claimed.
