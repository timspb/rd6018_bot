# AUTONOMOUS pre-bench evidence snapshot

This document freezes the repository-side evidence before the first physical
RD6018 AUTONOMOUS validation. It is an evidence record, not a hardware test
result and does not authorize actuator operation.

## Software

- Git SHA: `2e6f87bf636234d0c2373fb0389fbf95edc2e2ad`
- Branch: `codex/off-authority-audit`
- Working tree at capture: clean
- Snapshot date: `2026-09-10`
- Test status: PASS
- Checks: ownership provenance, AUTONOMOUS mode, edge AUTONOMOUS mode,
  startup authority, soft-watchdog containment, documentation links and
  `git diff --check`

## Architecture evidence

| Contract | Software result |
|---|---|
| Explicit AUTONOMOUS entry | PASS |
| Persistent AUTONOMOUS state | PASS |
| Wi-Fi loss does not trigger managed shutdown in AUTONOMOUS | PASS |
| Wi-Fi restore does not reclaim ownership | PASS |
| Automatic takeover is blocked | PASS |

The repository evidence confirms that `AUTONOMOUS` is explicit persistent
edge authority, distinct from `HANDS_OFF`, and does not bypass intrinsic
physical safety. Managed Pb restore and bot actuator paths remain blocked while
AUTONOMOUS is confirmed.

## Hardware validation pending

These values must be recorded from the exact physical target before or during
the bench run; they are not inferred from repository or CI evidence:

- ESPHome firmware SHA:
- RD firmware:
- RD model:
- Physical node identity:
- Bench date/time:

## Gate statement

Software validation complete.

Physical validation required.

No repository-side evidence in this snapshot replaces exact-node firmware,
readback, protection and bench observations.
