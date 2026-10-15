# D068a — ProductionChargeController continuation serialization

Status: SOURCE-ONLY / SOFTWARE PASS / OWNER LOCK STILL OPEN.
Extends accepted D067 single-write charge-session baseline without deploying.

## Discovered owner gap

D067 made ManagedChargeController.save_session atomic, but the real
ProductionChargeController._save_session still executed THREE further
independent JSON rewrites after the base save:
- v2_cooling_pause;
- runtime_signal and CV/CC extrema;
- MIX Delta finish marker, mode and finish evidence.

A crash between those writes could expose a partially updated session or
erase/lose an already persisted MAIN Guard checkpoint. This was an actual
source-level continuation consistency gap, not a claim of physical failure.

## Changes

The subclass now supplies a pure _session_document_extensions hook. The
canonical session_atomic.complete_session_document composes all continuation
fields into the ONE atomic charge/trace/optional-MAIN-Guard JSON write.

Metadata requirements preserve the accepted rules:
- cooling pause is persisted only when present;
- runtime_signal only for the current, fresh, correctly bound MIX CV/CC state;
- Delta hold state only with finite real finish timer, confirmed Delta mode and
  session identity; finish_evidence only when valid for that mode and session.
Unknown or stale contexts do not become recovery proofs.

Offline tests use the real ProductionChargeController to prove exactly ONE
writer call, persisted cooling pause/trace identity, valid MIX continuation,
and refusal to retain stale Output status as a runtime signal. Full WSL2
regression includes the existing D061/D063/start/restore tests.

The restore source now recognizes an existing session-bound guard journal and
restores its tighter ceiling/revision rather than silently recreating I0.
However it is NOT YET a finished production resume/enable contract: the
execution owner still needs to reconcile real current/OCP and lease evidence
before any Output ON command, including manual, START and recovery pathways.
Do not mark that gate PASS until end-to-end tests prove it.

## Explicit remaining safety gates

1. One owner-wide lock across main 30-second loop, session writes, START,
   manual commands, lifecycle, recovery and output transaction.
2. Crash/restart and pending-transaction reconciliation with native Iset,
   OCP, Output register-18 and live lease before any possible ON.
3. Unknown/long telemetry gaps must not be treated as proven MAIN active time.
4. D061 physical adopted child SIGKILL: separate HOLD until an independently
   lock-owning supervisor and OFF proof are established; the 900s edge lease
   alone does not meet the accepted 45s containment bound.
5. Physical Iset/OCP verification only within separately authorized 15.5V;
   MIX >16.5V experiments NOT authorized. AGM unchanged.

This PR is safe to publish as code only, not as permission to deploy on node104.
