# RD6018 — MAIN Guard → MIX incident and guarded handoff candidate
Date: 2026-11-05 (UTC). Scope: EFB 65 Ah, Recovery. Read-only evidence from node104 and HA102.

## Verified physical incident

At 09:35:08 node104 production log records:
- MAIN Charge 14.83 V, 0.24 A, battery 24°C;
- V2 transition `Main Charge -> Mix Mode`, reason `main_tail_hold_complete_recovery_mix`;
- `data_logger: ineligible_charge_stage`, immediately followed by generic
  `Link lost during active charge: emergency shutdown` handling.

At 09:35:16 OFF verified, then hardware safety lease disarmed 09:35:18.
At 10:02 HA102 REST reported output=OFF, current=0.0 A, battery=13.26 V,
safety lease remaining=0, lease_armed=OFF. These are read-only snapshots.

Node104 itself: service active PID 213548, NRestarts=0; workdir is
`/opt/services/rd6018-bot/state`; session preserved as MAIN Charge,
profile=EFB, ah_limit=65, v2_intent=recovery, target voltage=14.82 V,
current limit=1.23 A; control mode `pb_managed`. MAIN Guard journal
revision 481, pending=False, fault=False, ratchet limit approximately 1.23 A.
The adaptive Recovery module was NOT installed on node104. Do not infer
an active physical charge from service uptime or control mode alone.

## Root cause and effect

`runtime/charge/strategy/main_guard_session.py::_identity` rejected
`Mix Mode` because it was not an eligible persisted guarded stage.
The existing one-file `complete_session_document()` then tried to
attach the previously active MAIN Guard journal to the new MIX session
and raised `GuardJournalError(ineligible_charge_stage)`.
The broad data_logger exception handler logged this as apparent link loss
and performed safe emergency OFF. This is a software stage persistence
boundary defect, not evidence that the ESP connection actually dropped.

## Source-only candidate correction

An already validated Guard may be persisted in MIX, preserving its session
identity, segment, current ratchet, revision and hash, **only** with the
previous canonical guarded document in MAIN or MIX and without an unresolved
pending operation. Starting a new Guard in MIX is still forbidden.
The old journal cannot be silently dropped or its current ceiling raised.
No separate writer, new execution authority or new auto-restart path.
The existing guarded restore admission remains fail-closed.

Native recipe EFB recovery plateau opt-in still defaults OFF and is a
separate change; no high-voltage recipe or voltage target was enlarged.

## Test and rollout policy

Offline Linux focused regression: 117 PASS, 984 subtests PASS, including
native recipe parity, session persistence, Guard, and new adaptive policy.
The Windows project venv run gave 113 PASS / 984 subtests and one platform
directory-fsync failure, already resolved in Linux. More focused tests
for unresolved Guard pending and for rising current also pass.
Full Linux repository regression is in progress when this draft is written.

Node104 has NOT been changed. **Do not restart or re-enable charging**
simply because the patch compiles: the preserved pre-incident MAIN session
and guarded restart admission require an explicit, coherent D090 owner path
and live state revalidation. Any release requires current source manifest,
backup/rollback proof, selected recipe configuration and physical acceptance.
