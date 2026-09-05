# Assistant History

This file preserves high-value rationale/history that explains why current contracts exist. Current behavior is defined by `V2_DECISION_LOG.md` and `CHARGE_STRATEGY.md`, not by this chronology.

## V1 audit baseline

V1 behavior was audited against `main@8d3e2af9c2f16721f3303579f12d4f39bcc98a13` before production V2 semantics were normalized. The audit established that the old system was not just a stage FSM: Telegram/operator routing, chemistry evidence, physical sequencing, watchdogs, persistence/recovery and legacy side channels all contributed observable behavior.

## Main/recovery strategy decisions

- Ca/Ca and EFB stuck-current recovery uses a session-wide three-attempt budget. Progress after an attempt does not reset it; the next confirmed plateau after exhaustion may enter final Mix subject to safety/diagnostic HV veto.
- AGM is deliberately asymmetric/conservative: four intermediate attempts per session, and another plateau after budget exhaustion does not itself force Mix.
- 72h Main is a chemistry/intent fallback rather than a generic hard-safety timeout.
- Mix evidence is regulation-mode specific and a confirmed delta starts a sticky two-hour finish hold.
- Production Mix fallback maxima were extended to Ca20h/EFB24h/AGM10h.
- SAFE_WAIT is a bounded relaxation wait, not a fault timeout.
- Done means managed Storage/float remains energized around 13.8V/1A.

## Manual normalization

Manual was promoted from legacy unmanaged/overlay behavior into its own first-class authority. Working V/I belong to the operator inside the 17.5V/12A outer safety envelope; OVP/OCP are derived. Pb chemistry cannot unexpectedly promote Manual into Recovery/Mix/Storage. Persisted active Manual restores as `INTERRUPTED` and requires fresh operator authorization plus a complete safe-enable/readback transaction.

Optional saved physical battery identity is history/diagnostic metadata only. Saved chemistry/Ah never rewrites Manual V/I or grants HV authority.

## Diagnostic evidence boundary

The V1 generic bank-fault score was split conceptually into cell-fault, self-discharge, sulfation, stratification, capacity-loss, thermal and charger/path hypotheses. Diagnostic inference may veto a *new* automatic HV transition only at a conservative multi-signal boundary; it never creates HARD_STOP by itself.

Controlled `ΔV_BAT/ΔI` is a two-wire dynamic-loop response, not battery internal resistance. The RD6018 displayed `V/I` is also not battery internal resistance. `V_OUT-V_BAT` must remain descriptive until the internal red/green measurement topology is independently established.

## 2026-08-30 — persistence and Manual identity hardening

- Diagnostic evidence persistence was separated from transient diagnostic action authority. In-flight probe work aborts on restart; expert authorization is revoked; derived HV authority is recomputed.
- Manual can be bound to saved physical battery identity for longitudinal correlation, but restart requires explicit fresh re-authorization.

## 2026-08-30 — SG policy closed

Per-cell SG remains raw primary evidence. Physical electrolyte access is stored explicitly per battery (`UNKNOWN/SERVICEABLE/INACCESSIBLE`); non-AGM chemistry does not imply serviceable cells. AGM is never prompted; EFB/Ca/Flooded require explicit serviceable access.

Hydrometer mode and any temperature-correction convention belong to the individual measurement. A temperature-compensated hydrometer is never corrected twice. Named Trojan-80F and Rolls-25C conventions require an explicitly declared raw hydrometer and electrolyte temperature and are never inferred from manufacturer/model strings.

Routine charge does not nag for SG. Proactive SG is reserved for SG-relevant VERIFY+ diagnostics or a post-corrective retest after prior imbalance. Missing/inaccessible SG does not raise fault confidence.

## 2026-08-30 — generic expert EFB >16.5V rejected

The generic EFB policy originally retained a 17.5V expert ceiling as an unresolved scaffold. Manufacturer/charger research found supported EFB recovery/regeneration guidance around the existing standard 16.5V envelope, but no generic EFB automatic/conditioning basis for 17.2–17.5V.

The generic EFB chemistry envelope is therefore capped at 16.5V even when an `expert_high_voltage` flag is supplied. The global 17.5V outer limit remains available to first-class Manual/Custom authority. Any future automatic EFB recipe above 16.5V must be exact model-specific and manufacturer-backed; the `EFB` chemistry label alone can never grant it.

## 2026-08-30 — calibration must be empirical

Two deterministic offline tools were added without changing production thresholds:

- `tools/evaluate_battery_fault.py` replays labeled real fault cases and reports false/missed automatic-HV blocks separately from hypothesis-level mismatches.
- `tools/characterize_dynamic_loop.py` reports actual sample cadence, noise/span, observed value steps, measured ΔI/ΔV and settling traces from timestamped bench data.

The current Bank-Fault weights/15-35-60-80 level thresholds and controlled-probe amplitude/timing remain open until real independently labeled traces/actual RD6018 characterization justify them. Synthetic test convenience is not a reason to tune production safety behavior.
