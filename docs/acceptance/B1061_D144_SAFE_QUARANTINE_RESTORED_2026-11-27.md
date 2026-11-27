# B1061 — D144 rollback completion when restored service is deliberately quarantined

Date 2026-11-27. SOURCE TEST PASS, hardware recovery NOT YET RUN.

## Actual interrupted transaction

B1059 was installed through canonical D145/D144 slot25 with full D151 independent OFF proof, but the bot did not emit the expected Telegram polling ready marker because it was blocked by the original exact D084 START_PENDING incident. D144 slot25 remained STARTED. Canonical D145 recover restored the former B1056 app/venv successfully but refused to mark RESTORED because B1056 also cannot reach polling while the durable START_PENDING remains. Repeating execute or deleting the session/journal is prohibited.

## Repair in the existing D144 owner, not a new transaction path

D144 OwnerTransition.recover continues unchanged, including its original D090 owner lock, byte-for-byte before/backup identity, old D090 journal hash, physical OFF snapshots before and after stop, and restored app/venv inventory. The only new case is its existing restored_stable callback: normal polling readiness is preferred; otherwise an exact *safe quarantined restoration* may be positively verified.

That proof requires: one active process with the expected installed bot.py argv and NRestarts=0; original source SHA in .deploy_sha; one valid START_PENDING previous_exists=false, matching a durable D084 start_enable_off_receipt_invalid quarantine session/battery; a fresh pinned D151 independent ESP Native plus HA Output OFF, zero current, unarmed lease, active-session proof bound to the current PID; and post-start logs containing the expected quarantine message without traceback/unauthorized/database lock or a claim to ordinary polling readiness. All conditions must hold at once, or recovery remains blocked.

Successful D144 RESTORED then only means original bytes and safe isolated state returned: NOT Telegram operational readiness, NOT removal of D084, NOT authorization of any Output ON, START or V/I. After that, a new source-paired software release can start via D145 PREPARE/EXECUTE with its own fresh proof. No duplicated actuation code or direct firmware writes.

## Tests

B1061 D144 recovery, entrypoint, D137 and negative identity/lease proof: 52 PASS + 22 subtests; tests assert no changes to original session or durable quarantine bytes. Retain physical P3/P8 HOLD.
