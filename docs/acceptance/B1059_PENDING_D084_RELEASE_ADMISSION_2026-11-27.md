# B1059 — recover one D084-quarantined START_PENDING through existing owners

2026-11-27. **Source-only PASS; node104 production unchanged, P3/P8 HOLD.**

## Source-matched real hardware observations
- B1056 D144 slot24 COMMITTED, active systemd MainPID428021 after one operator-authorized restart; no repeat of failed restart.
- One exact valid `START_PENDING`, sha256 `54e0a0cde00458510ad391806bfd98671eedb898bf8ae880cdf6886ea1c0138d`, generation1, previous_exists=false, candidate session `c4039339274b4a90a133beb8429dcbea` and battery `Leoch_72Ah`.
- Existing durable D084 journal schema1 exact incident `6a5fbb67-193b-4c7e-b863-94ba6af0e379`, reason `start_enable_off_receipt_invalid`, matching session/battery.
- New ESP AD051 Native API action present; read-only receipt TextSensor showed target=false, state=APPLIED, observed_r18=0. Fresh Native R18=0, output 0V/0A, R16=0, 900s lease unarmed; D151 immutable collector independently proved both HA+ESP OFF with active_session=true.
- B1056 startup recovery returned RuntimeError (no durable state change). D137 read-only admission refused `durable retirement and verified-OFF identity do not agree`, because it did not recognize START_PENDING plus active durable quarantine, not because Output was ON.

## Precise fixes, not bypasses
1. B1058 startup owner waits a bounded 10s for a typed **post-OFF/APPLIED**, same-Native-generation R18=0 callback, preserving exact CAS rollback and fail-closed timeout.
2. B1059 `application/controller_session_retirement.py` recognizes ONLY valid `START_PENDING previous_exists=false` whose candidate identity equals durable D084 incident. Existing private `/recovery_clear` remains the sole authenticated operator workflow. `OperatorRecoveryClearanceService` first executes existing ExecutionPort verified OFF then exact `finish_start_pending(ROLLBACK)` and then journal `retire`. Power loss between pending and journal retirement is handled by exact absent-session incident identity with a fresh second OFF, never by automatic clearance.
3. B1059 `tools/d137_observed_preimage.py` preserves both exact pending and quarantine bytes under an authenticated fresh D142/D151 independent ESP+HA OFF witness. Its single shared strict witness validator is used for the existing guarded-MAIN path as well. This is **read-only source release admission**, NOT charging admission or a bypass of D144. Wrong identity, previous_exists=true, missing proof, lease armed, stale source, changed PID, duplicated nonce, nonzero current all refuse.
4. D142 and D144 continue to collect fresh independent physical proof for each phase. No direct Output, V/I, lease/Modbus commands, no session/journal writes in the source preflight, no second Output writer, no crypto theater.

## Source tests and release status
- D137/D142, operator clearance and integration: 60 tests + 32 subtests PASS.
- Wider D137/D138/D142/D144 plus recovery: 96 tests + 39 subtests PASS.
- `git diff --check` required and source-paired GitHub CI required before release.
- **No physical deployment or D084 clearance yet.** Production safe OFF, source work pending release. Controlled D144 cutover must preserve state byte-for-byte; only after installed source recovers START_PENDING and operator confirms one private `/recovery_clear` with an actual OFF proof may durable D084 retire. Single supervised START/STOP remains future P3.

