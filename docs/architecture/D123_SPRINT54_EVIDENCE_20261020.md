# D123 Sprint 54 — canonical production restore convergence

Status: source-only from requested clean HEAD
`d6ab0fbe507107c4fcbd9a41d3ac2ca078078a4f` on
`codex/d118-start-lease-repair-20261019`. No node104, ESP, HA, firmware,
service, deployment, GitHub, or physical output was accessed or changed.

## Restore authority order

1. `runtime.charge.persistence.restore_session` reads the canonical raw JSON
   document. Missing, unreadable, corrupt, non-mapping, retired-invalid, and
   over-age documents retain their existing behavior.
2. A document containing `main_current_guard_v1` is held before mutation,
   enrichment, age deletion, or continuation. This fail-closed policy was not
   changed.
3. For admitted unguarded documents, persistence performs ordinary FSM/session
   mutation, terminal normalization, target/time reconciliation, trace identity
   and stage-history restoration, and stores the exact raw document on the same
   host.
4. `ManagedChargeController.try_restore_session` keeps Custom-session rejection,
   DESULFATION clock restoration, recovery/final continuation reconstruction,
   shadow initialization, and canonical enrichment in the prior order.
5. For the production-marked host only, the same method then resets and reads
   any Guard journal from that exact document (identity/generation validation
   remains in `read_guard`) and invokes production extension restoration. That
   restoration retains intent defaults, MIX finish/runtime signal restore,
   target bounds, cooling pause reconstruction and strict cooling validation.
6. Runtime startup, idle-link recovery, output-on adoption and operator-pause
   recovery continue to call `try_restore_session`; existing caller-side gating
   and execution remain unchanged. Restore itself has no physical writer.

Because persistence currently rejects every guarded document before mutation,
the later production Guard reconstruction remains unreachable for guarded
snapshots. It is retained in the canonical owner in the same order so changing
admission later cannot silently skip Guard reconstruction. No admission was
widened.

## Convergence and remaining boundary

| Measure | Sprint 53 before this cut | Sprint 54 after this cut |
| --- | ---: | ---: |
| Production controller declared methods | 1 | 0 |
| Production overrides of ManagedChargeController | 1 | 0 |
| Production subclass declarations/inheritance | 1 | 1 |
| Canonical session writer | 1 | 1 |
| Production restore FSM/session host | 1 | 1 |

The production subclass remains as the existing marker selecting production
extension state and target policy; it owns no methods or state. Removing that
marker-class relationship safely requires a broader production composition
factory change. P4 inheritance elimination is therefore not claimed complete.
P2 remains partial: canonical raw restore handoff and Guard admission stay
fail-closed in persistence pending owner-wide reconciliation authority. P5
release/physical acceptance remains open.

No recipe, algorithm, lease, safety, OVP/OCP, ESP-priority, Manual, or physical
path changed. The canonical session writer in `runtime.charge.session_atomic`
remains unique. Static regression verifies the method removal, single restore
ordering, single writer, single production construction, and no physical writer
in restore.

## Verification

- Focused restore/Guard/controller set from Codex: **97 PASS**.
- Follow-up focused regressions for the two stale structural fixtures: **7 PASS**.
- Codex sandbox full discovery stalled / hit environment limits and is not used as the acceptance gate.
- Canonical direct WSL Python 3.12 discovery outside the Codex sandbox with synthetic TG_TOKEN: **2,453 tests, 3 skipped, PASS**. Full log: /tmp/d123-s54-canonical.log.
- /home/home-pc/rd6018-v3-deploy/.venv/bin/python -m compileall -q .: PASS.
- git diff --check: PASS.
