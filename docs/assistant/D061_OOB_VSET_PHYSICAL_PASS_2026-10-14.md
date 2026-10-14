# D061 — real out-of-band Vset increase, physical PASS (2026-10-14)

**Result: PHYSICAL PASS for a single bounded external Vset increase only.** This does not close out-of-band Iset, OVP or OCP classes.

- Bench: real RD6018, connected Leoch Ca/Ca 72 Ah, node104, firmware `2.2-autonomous-authority` unchanged.
- Exact canonical source: `aecf602f521025cc4ce1348e96a79bf4548e6f19`, pinned 899-file manifest SHA256 `46c890c70c57e2e665e9fd732d8b357ab557468c192a396d1eb7d39c78c4dc68`, target node104 pairing 899/899 PASS before electrical actuation.
- Separate acceptance-only overlay: `pairing.py` SHA256 `a4f20bebe7f0f35235a5ae0db7582ccf47d69e7b9fa26f801140249a597d10aa`, `takeover.py` SHA256 `2ddde27e85efa8f70f941f13c59f8a818a7a40165973ab6719e7462153dac79f`. Overlay tar actual accepted SHA256 `8a444525afacd83ddfbe4663457801ec6c28feb47242a74abfbd2d7d3f8cc06e`. The old ACK physical runner is unchanged.
- Readiness: original production single-process, HA102+native ESP128 independent OFF, lease disarmed, protection NORMAL, Vset 13.57V, Iset 0.10A, OVP 14.07V, OCP 0.20A, battery temperature 23°C, PSU 29°C.
- Actual sequence: bounded physical ON 13.09V / 0.09A, fully proven PB_MANAGED adoption with **19/19 predicates**; independent external HA REST command elevated ONLY Vset 13.57→13.67V, separately acknowledged by native ESP Vset readback; adopted observer rejected upward authority change, forced verified OFF and disarmed edge. Typed state `adoption_state=failed`, `manual_state=failed`, `rd_control_mode=pb_managed`, Output OFF.
- Executor required the canonical specific `adopted_live_out_of_band_authority_increase` reason; a generic shutdown could not pass. Return Vset to **13.57V only after independent OFF** and verify native readback before restoring production. No change to Iset or OVP/OCP.
- Final receipt UTC `2026-10-14T12:40:33.295082+00:00` **PASS**: `independent_output_off=true`, `edge_lease_disarmed=true`, `ownership_safe=true`, `acceptance_poller_stopped=true`, `production_restored=true`, `containment_complete=true`, `oob_restored=true`, lease generations 37→38 armed→39 HANDS_OFF release→40 disarmed, 0.00V/0.00A, battery 23°C and PSU 30°C.
- Original Windows receipt `C:\Users\HOME-PC\d061-takeover-evidence\d061-aecf-oob-20261014-224034.json`, SHA256 **`f870d8fa58ade86794785173bebbfa2c5dac6223a44f84a10bb5a7ceb7d4ce99`**. Parsed receipt: [JSON](D061_OOB_VSET_PHYSICAL_PASS_2026-10-14.json).
- **Independent postrun, 2026-10-14 12:41:21 UTC:** SSH pinned host-key match, HA102 and native ESP128 VALID, Output OFF 0V/0A, Vset 13.57/Iset 0.10/OVP14.07/OCP0.20, raw protection NORMAL, lease not armed/tripped/quarantined, production ACTIVE exactly one PID **57607**, NRestarts 0, no test socket; root 0600 lock remains.

## Not accepted by this run

External Iset, OVP and OCP mutations, adopted-bot process kill/restart, and actual hardware OVP/OCP/OPP trips remain **OPEN**. This Vset PASS does not prove them. No firmware or production source changes were deployed.
