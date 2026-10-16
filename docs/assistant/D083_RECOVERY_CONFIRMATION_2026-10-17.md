# D083 — recovery confirmation results

## Change boundary

D083 corrects the result contract at the existing
`application.SessionRecoveryService` boundary. It adds no execution owner,
transaction framework, actuator path, authorization rule, timeout, or hardware
command. Production still holds the same owner lock, chooses the same recovery
route, restores persistence in the same order, and calls the same `ExecutionPort`.
Charge algorithms, targets, timers, watchdogs, and the 900-second edge lease are
unchanged.

Route B (lost-link persisted IDLE) now reports success only after every required
V/I setter and the selected verified Output ON or OFF returns true. A rejected
setter stops the sequence before later setpoints or Output action. A rejected
verified ON/OFF or setter suppresses the RESTORE event, success notice, and
checkpoint advancement. Runtime warns that Output state is unknown and leaves
the pre-existing in-memory lifecycle and lost-link markers untouched. It does
not clear the persisted session, claim that charging stopped, or issue a second
hardware command on denial. Raised execution exceptions continue to the
existing outer `data_logger` error handler, which owns safety containment.

Route C (Output was observed ON before restore) still never requests ON. In
SAFE_WAIT, verified OFF must succeed before V/I programming. Other stages require
both setters to succeed. Success means only that the required restore actions
completed: route C normal does **not** confirm Output ON from the earlier
telemetry observation. A denied prerequisite suppresses success effects while
preserving the pre-existing in-memory lifecycle and persisted session. In normal
route C, success means only that the setters were accepted; it does not confirm
Output.

Route A and its phase-protection -> voltage -> capped-current -> verified-ON
sequence are unchanged. Successful B ordering remains phase protection -> V ->
capped I -> verified ON, or phase protection -> V -> capped I -> verified OFF.
Successful C ordering remains phase protection -> verified OFF -> V -> capped I
for SAFE_WAIT, and phase protection -> V -> capped I otherwise.

## Failure behavior and residual risk

A denied verified OFF means physical Output may remain ON. A false verified ON
also leaves physical state ambiguous: the command may have reached hardware
without positive confirmation. D083 preserves the existing lifecycle and lease
renewal behavior on either boolean denial; it does not treat false as physical
OFF or drop ownership. This avoids abandoning a potentially energized managed
Output, but means the restored stage may remain managed and its periodic tick
may run while recovery is unresolved. The independent edge lease remains in
place. Whether that lifecycle behavior is safe for every stage and failure
timing requires physical acceptance before this behavioral change is rolled out
to production. Do not interpret these offline tests as hardware validation.

No new command is issued in response to a denied result. Execution exceptions
are not converted to normal denials: they propagate to the pre-existing
`data_logger` exception handling and safety containment.

## Evidence

Offline fake-port tests cover B false ON, B SAFE_WAIT false OFF, C SAFE_WAIT
false OFF, false V/I setters on B and C, exceptions, preserved successful
ordering, no route C ON request, and no false ON confirmation from prior
telemetry. Runtime source guards ensure boolean denials preserve lifecycle and
lost-link markers, make no success/checkpoint changes, and emit an accurate
unknown-Output warning without a RESTORE event or stopped-charge claim. No node
104, ESPHome/firmware, HA, credentials, PSU, or battery was accessed.
