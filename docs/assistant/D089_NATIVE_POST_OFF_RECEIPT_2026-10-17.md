# D089 — native post-OFF receipt hardening (2026-10-17)

## Change

D087 recovery clearance now accepts `VerifiedOffEvidence` only after the existing
single `request_verified_off()` operation returns successfully and the selected
physical owner reports a new native ESPHome `SensorState` callback for the
physical output sensor. The subscription timestamp must be a finite monotonic
number strictly later than OFF completion; the numeric value must be zero (a
boolean is invalid), status must be `ok`, and both source age and measured
callback age must be at most eight seconds. Polling is bounded to ten seconds.

The canonical `HassClient` delegates this read only when its already-selected
physical backend exposes native reporting. The ESP-direct connector delegates to
its existing ESPHome transport subscription. HA REST, cached `get_all_live()`
data, connector switching, and fallback reads do not qualify. A configured
HA-only backend, missing native reader, malformed/stale callback, or timeout
returns no typed evidence. This preserves the quarantine and controller session.

The boolean OFF API and emergency OFF path are unchanged. The evidence path adds
no actuator write and cannot clear quarantine without positive native proof.
Task-reentrant app-owner serialization remains around the complete OFF/read
transaction.

## Verification and limits

Focused offline tests cover pre-completion callbacks, post-completion native
proof, HA-only/missing readers, wrong native type, malformed timestamps,
boolean values, OFF rejection, one OFF call, and owner-lock reentrancy. Software
verification does not establish physical node/firmware behavior. This change
does not authorize deployment or use on node104; exact ESPHome contract and
bench validation remain separate gates. No node, hardware, service, secret,
lease, AGM, MIX, or MAIN operation was performed.
