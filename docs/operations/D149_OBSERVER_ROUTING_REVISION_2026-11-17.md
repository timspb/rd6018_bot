# D149 observer-routing correction

Date: 2026-11-17  
Disposition: source routing verified; production and physical acceptance remain HOLD.

## Current source behavior

The current observer router has three roles:

- D147: ordinary PRE_STOP observation.
- D150: ordinary STOPPED and POST_START observations.
- D151: RECOVERY observation.

D145's state-preserving prepare/execute path uses D151 for its four observations. D145 recovery also uses D151. The current D149 router tests cover this routing, including the D151 source relationship.

Historical D145/D149 notes that describe D147/D148 for the current state-preserving route are stale. This correction records the current source behavior; historical evidence is not rewritten as if it described the newer implementation.

## Owner decision — no extra cryptographic machinery

The earlier proposal to pin an acceptance record with a new digest is withdrawn.

Do not add digital signatures, signing keys, PKI, attestation, or new digest-pinned acceptance records. Do not turn ordinary source/release checks into an additional authorization system. Any existing check that adds complexity without protecting an existing transaction or physical invariant should be reviewed for removal.

No code or production state was changed by this correction.

## Execution boundary

The current chat's R7.2 route was inspected through the trusted current-chat inspector. The app's self-test event was confirmed ACKed on its first attempt. No route was created or changed. The prior Codex job in another project was left untouched.

Next: continue the RD6018 modularization plan, first reconciling AD153–AD157 and the P4-14 restore work against the current source, then choose the smallest next owner-boundary extraction. Source-only; no node104, ESP, HA, service, firmware, Output, lease, or physical operation.
