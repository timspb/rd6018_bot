# RD6018 — EFB MIX → SAFE_WAIT → Storage incident, 2026-11-09

## Production evidence (read-only)

Owner Telegram screenshots at 22:46: Delta held two hours, SAFE_WAIT before Storage 13.3 V; at 23:01: unmanaged Output V2 safety, reported 13.61 V/0.99 A. These are historical messages, not present-time native truth.
Used existing pinned ED25519 node104 connection, credentials from existing env.secrets, only remote systemctl, journalctl and session read. Node104 service active, MainPID 237957, NRestarts=0 at inspection.
- 12:46:55 UTC: MIX CC Delta hold completed, hold_seconds=7227.6; transition to SAFE_WAIT.
- 12:46:59 UTC: Output OFF command accepted. 12:47:00 UTC: fresh ESP Native R18 callback confirmed OFF after the command; edge lease disarm allowed.
- 13:00:27 UTC: SAFE_WAIT reached threshold 13.30 V; requested Storage enable after 812.3 seconds.
- 13:00:31 UTC: edge lease arm ACK generation 335, remaining about 899.6 seconds.
- 13:00:35 UTC: data_logger error ineligible_charge_stage. 13:07:13 UTC: soft watchdog while energized, requested bounded OFF containment.
- 13:18:50 UTC: separate fresh ESP Native device identity confirmed timspb.rd6018-pb-recovery-v2 firmware 2.3-ha-canonical; R18=OFF. Strict voltage callback failed native measurement inventory identity mismatch: V; therefore full V/I/lease state NOT proven.
- Persisted node104 charge_session.json remains SAFE_WAIT with v2_final_safe_wait and main_current_guard_v1; no terminal Storage/on commit.

## Reproduced source root cause

Final SAFE_WAIT verified-enable callback sets RAM stage Done then saves canonical storage/on. MAIN Guard journal validation rejects Done (ineligible_charge_stage) after hardware ON: RAM Done, disk SAFE_WAIT, output potentially ON. Unmanaged-output guard subsequently triggers. Disposable HOME-PC replay reproduced MAIN SAVED → MIX SAVED → WAIT SAVED → GuardJournalError ineligible_charge_stage → RAM Done, DISK SAFE_WAIT. MIX Output OFF itself was verified and not the failure.

## Source-only correction, no new owner

- main_guard_session: accept terminal Done only with pre-existing revisioned MAIN Guard and matching canonical terminal storage/on or terminal/off intent; all usual identity, monotone ratchet, guard fault/pending checks remain. Forbid new Guard minting in Done.
- persistence: managed_storage_ownership_proven requires exact durable Done/storage/on with matching session/battery/generation/terminal metadata and original saved MAIN Guard snapshot; restored guard intentionally resets last_output_on, so compare authentic saved snapshot instead of restored object.
- managed_guard: recognize confirmed durable terminal Storage ownership, not arbitrary RAM Done state. Without exact evidence, existing unmanaged-output protection applies.
- controller_action_execution: if Output ON was physically enabled but session commit raises, immediately request verified OFF through existing ExecutionPort. If OFF confirmed, raise a critical operator notice and return failure; if OFF cannot be confirmed, fail closed rather than accept Storage.
- Added EFB guarded end-to-end synthetic path, invalid terminal/foreign identity and safety ownership tests; exception/OFF tests in existing application action suite.

## Validation and release boundary

Focused 40 PASS, 0 FAIL. Extended 16-module terminal/guard/owner/recovery/MIX regression 144 PASS, 0 FAIL, exit code 0; compileall and git diff --check PASS. Full repository suite not run. HOME-PC source only, no node104 deployment, no Output/setpoint/firmware/lease writes, no production DB mutation.
Before deployment under separate approval: fresh direct ESP Native R18, measured V/I, R16, setpoints and OVP/OCP, edge lease, bot session and guard state, verified native sensor identity/freshness; then controlled physical release acceptance.
Disposable inspection/reproduction scripts remain in ignored .recipe-studio-local. Do not push to foreign upstream or force-push owned Git branch.