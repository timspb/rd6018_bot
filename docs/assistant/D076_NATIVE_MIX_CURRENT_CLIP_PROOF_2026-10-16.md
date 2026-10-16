# D076 — native MIX current-cap evidence (software-only)

**Scope:** EFB/Ca/Ca MIX; no production deployment or charging command.

D075 separated ordinary CC voltage Delta from potential voltage sag caused by a
lowered adaptive Iset ceiling, but production lacked trustworthy evidence of
when that ceiling had been reached. D076 adds a **read-only pure classifier**
under `runtime/charge/strategy/mix_current_evidence.py`.

Positive `proved_clipped` requires ALL of the following:

- a typed, committed, session/battery-bound *lowered* MIX current limit,
  supplied by an already reconciled execution owner after verified hardware
  Iset readback (a proposal is not proof);
- fresh, coherent and post-commit native register-18 **Output ON**, register-17
  **CC**, and register-9 **Iset** matching that acknowledged lower limit;
- fresh native measured current, explicit HA `last_reported` per source
  (raw metadata, not the legacy switch / `is_cc` compatibility view);
- no contradictory source identity/status, skew, stale or pre-commit sample;
- a positively advanced native heartbeat relative to the last consumed native
  report timestamp, preventing repeated snapshots from accumulating Delta proofs.

A native **CV** observation with the same validated cap is `not_clipped`.
Absent, inconsistent or stale authority is `unknown`. An **active** adaptive
ratchet with `unknown` evidence conservatively censors unconfirmed CC Delta,
without stopping, writing to, or disabling RD6018. Ordinary CC without an
adaptive ratchet continues normal Delta evaluation.

The boolean `current_limit_clipped` is now propagated through the pure
`ChargeStrategy`, `StrategyEngine` and `ChargeEngine` boundaries to D075's
`MixPolicy`; it is still not automatically fed by live V2 production. No
automatic Iset adjustment, electrical trip threshold, OCP/OVP change or extra
hardware/credential is introduced.

**Outstanding:** owner-issued persisted MIX cap receipt, real native readback
provenance checks on the installed firmware, calibration of safe current
headroom and approved physical Iset readback trial at the established bench
voltage limit. Test-only evidence is not hardware acceptance.

**Unchanged:** ESPHome 900-second dead-man lease, all existing production
charging recipes and AGM logic. No node104, HA or ESPHome changes.
