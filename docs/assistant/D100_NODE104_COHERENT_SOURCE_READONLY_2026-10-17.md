# D100 — exact-source D097 candidate and real node104 read-only coordinator acceptance

**Status:** PASS for isolated, non-actuating `autonomous_status` on the full
reviewed source; D097 physical ENTER/EXIT and D065 energized/reboot scenarios
remain **OPEN**.

## Accepted source and reproducible candidate

- Repository: `timspb/rd6018_bot`.
- Exact merged main: `b44476bcd19dbf0f4ac955634f02a4a7f9e51ddc` (PR #120).
- Self-contained Git archive: `E:\CODEX\RD6018_D099_SOURCE_CANDIDATE_b44476bcd19d\source.tar`
- Source archive SHA256: `89bb7a891c590fcd72eeb14fedd6e8405690528b627ff9ce56b91a7a91781294`.
- Canonical inventory: 1022 tracked files in `SOURCE_MANIFEST.json`, SHA256
  `935d6dfdfa73cc5183e37745c7bbce9e5411089696bfe3860b70439c0e4285de`.
- Explicit `README_NOT_DEPLOYABLE.txt` preserves the unfulfilled D090 release gates.
- Full local Python source suite: **2130 tests OK, 2 skipped** (~80s).
- Remote CI: Python 3.10/3.11/3.12 **3/3 PASS**.
- Neither a dirty deployment checkout nor a copy of selected modules was used
  as the source of truth for the final candidate.

## Actual node104 read-only execution

The archive was transferred over host-key-pinned SSH, its uploaded SHA256
checked, then extracted to an isolated `/tmp` directory. No files were
installed under the production application, no firmware update, no systemd
override, no second Telegram polling process, no new control socket.
The accepted `bot.py` was imported exclusively from the extracted source;
the independent installed D091 hardware preflight ran in a **separate process**
to prevent any production-library cache contamination. The test called the
existing `PhysicalTestControlPbMode.autonomous_status()`, not Enter/Exit.

Actual result: **D100_COHERENT_CANDIDATE_STATUS_READONLY_PASS**.

- Production service retained PID **69648**; no restarts.
- Software mode **pb_managed**; explicit `edge_autonomous=false`, manager=false.
- Edge generation **61**, `armed=false`, remaining **0s**,
  `tripped=false`, `boot_quarantine=false`, Modbus age ~5.33s.
- Output `off`, physical register-18=0; raw Protection register-16=0.
- Programmed V=**13.57 V**, I=**0.10 A**, OVP=**14.07 V**, OCP=**0.20 A**.
- `rd_actuator_writes_injected=0`.
- Independent HA102/native ESP128 measured Output OFF, V=0.00 V, I=0.00 A
  both before and after the candidate status call; no active charge session.
- Initial installed bot version retained:
  `8b75cca153f00847d84396aba392472bb7552ad4`.

Raw result: `E:\CODEX\RD6018_D100_COHERENT_SOURCE_STATUS_20261017.log`,
SHA256 `f6b019cac3ff2e8ef597ed394cb0264de413f0f17789b108b6eddb5d347953df`.
Independent eight-field post-proof:
`E:\CODEX\RD6018_D097_EXTENDED_READONLY_20261017.json`,
SHA256 `8870d24e47f7daa5171cfdd5e529e6c37605c6a6486cff3fb021476829db1200`.

## Cleanup and remaining contract

The temporary source tree, uploaded tar and testing script were removed
after testing. Some Python cache files needed an exact-path privileged cleanup;
the final check returned `D100_TMP_CLEANED`, unchanged MainPID=69648,
`NRestarts=0`, service active. Original production remains untouched.

The following conclusions **must not** be inferred from this proof:
- D097 physical production Enter/Exit: **NOT RUN**.
- D065 >900s AUTONOMOUS networking outage, exact-image managed expiry and
  ESP-only reboot: **NOT RUN / OPEN**.
- D064 independent intrinsic protection fault tests and full signed physical
  acceptance: **OPEN**.
- D090 still pins candidate `d29db790bf7140932bc005bddf6bd5988041bfc0`.
  Its reviewed firmware digest and physical signer trust pins are absent.
  This D100 archive is explicitly **NOT deployable through the old D090 release
  transaction**. Do not change its pins or fabricate proof to make activation pass.

Next engineering boundary: separately reviewed bench activation of a coherent
new source candidate with positively checked rollback, exact firmware
provenance and independent physical acceptance; only afterward reconsider D090.
