# D087 — operator recovery clearance implementation

## Operator workflow

When the durable recovery quarantine is active, an explicitly allowlisted
operator opens a private Telegram chat with the bot and sends `/recovery_clear`.
The route accepts only when the Telegram chat ID equals the sender ID, the
chat type is private, and that numeric ID appears in a nonempty
`ALLOWED_CHAT_IDS`. `ALLOW_ALL_CHATS` and the empty-list sentinel never grant
this action. The command reports an actionable configuration requirement when
admission fails.

The bot displays the incident, session ID, and a single confirmation button.
The nonce expires after 120 seconds and is bound in memory to that user, chat,
and incident ID. It is one-use. Old buttons fail after expiry, restart,
cross-user use, or incident change. The route exists only with the existing
`V2_UI` presentation switch enabled.

## Clearance transaction

The coordinator runs under the app-scoped task-reentrant owner lock and checks
the complete D085 incident identity against the active controller and canonical
`charge_session.json` before touching the PSU. Missing incident IDs (including
legacy D085 records), unknown identity fields, stage mismatch, battery mismatch,
and session mismatch require manual review and issue no physical command.

The canonical `ExecutionPort` invokes its existing `request_verified_off()`
owner operation. It then performs a new post-operation read and accepts typed
`VerifiedOffEvidence` only when native register-18 output state is zero and the
source has explicit freshness metadata no older than 20 seconds. A legacy
`switch=off`, stale cache, missing metadata, or nonzero native state cannot
unlock the quarantine. The normal boolean OFF contract remains unchanged for
all existing callers.

The controller persistence owner verifies the exact session and battery binding
again, fences subsequent same-process session saves, and atomically replaces
the active session document with a terminal `state=retired` record containing
the verified-OFF transaction ID, using file and directory fsync. It verifies
the replaced document before setting the
in-memory controller stage to IDLE. Restore categorically refuses this marker
before mutating controller state. The marker does not authorize a new charge;
START remains a separate operator action.

Only after controller retirement succeeds does the journal owner atomically
replace the incident with the existing schema-2 retirement tombstone. The RAM
guard is released last. A session-retirement or tombstone failure leaves the
guard latched and never issues ON. If the session marker may have committed but
the write/fsync returned an error, the save fence remains set; a later ordinary
save cannot restore the old active record. Such an uncertain transaction needs
manual review/reconciliation and is never auto-restored.

## Validation and remaining acceptance

Offline tests cover private allowlisted admission, group/chat spoofing,
allow-all and empty configuration denial, one-use/expired nonce behavior,
durable session retirement, identity mismatch, and save/fsync failure. Existing
D086 coordinator tests cover typed/stale OFF and journal failure ordering.
Compilation and focused offline unit tests are software evidence only.

No node 104, PSU, Home Assistant, ESPHome, firmware, lease, Output ON, or
production deployment action was performed. Exact ESPHome/lease and native
register-18 behavior still require the project’s separate physical bench
acceptance before this workflow is relied on operationally. The 900-second
lease, 300-second renew cadence, and charge chemistry/MIX/MAIN logic are
unchanged.
