# RD6018 AD-005 — ЕДИНЫЙ ВЛАДЕЛЕЦ СОСТОЯНИЯ OFF-УСЛОВИЙ (2026-11-12)
**Главная задача: полная декомпозиция и модульность RD6018. ChatGPT — единственный архитектор/приёмщик; Codex Luna — исполнитель.**

## Source evidence
- Read-only audit `.recipe-studio-local/REPORT_MOD_P6_7_OFF_STATE_AUDIT_20261112.txt`: six mutable `manual_off_*` globals and non-atomic `manual_off_state.json` writer/loader in `runtime/production_runtime.py`; separate AUTO tick and managed Manual observer read same overlay; `application/off_condition_command.py` preset route calls back into runtime. The file is NOT charge_session.json or manual_session_v2.json.
- AUTO path requests verified OFF, then clears condition; managed Manual path calls its existing stop/disable and clears only after confirmed OFF. Physical output logic stays as-is.
- Nonmapping JSON may crash loader; invalid float fields may propagate. Missing/invalid timestamp semantics differ between AUTO and Manual. Source audit alone is not physical proof.
- Legacy `off …` arms delayed condition and exact `off` clears; neither immediately actuates Output. `V I timer` writes setpoints THEN persists condition (even on partial setpoint failure): existing behavior pinned, not silently rewritten.

## Architect decision
1. Create one compact explicit source of truth for **operator OFF-condition state and its file storage**, distinct from charge-session storage and from managed Manual session state. Candidate ownership: `runtime/operator/off_conditions.py` as ONE cohesive state model + reader/writer, not a framework, service, dispatcher, bus, second controller, authorization layer or new periodic worker.
2. Public data contract stays unchanged: voltage_ge, voltage_le, current_le, current_ge, time_sec, start_time; existing JSON filename and keys preserved for node104 upgrade. State object supplies snapshot/update/clear/load/save and has one authoritative mutable instance wired in production composition.
3. Both AUTO and managed Manual observe that same instance; neither reimplements JSON or independently owns scalar copies. Operator UI, named presets and text commands mutate it through existing application command routes. The physical STOP remains in the currently approved existing physical owner and safety gate, not in the state object.
4. Migration is staged: P6-8 first fake-only baseline tests of the legacy state and AUTO/Manual stop contracts, no production edits; P6-9 implement one owner and adapt callsites under established tests; temporarily compatibility façades if required, but NEVER a second writable copy. If cross-chat WIP conflicts, stop and report rather than overwrite.
5. For malformed JSON restore: preserve safe, unarmed OFF-condition state and log diagnostic; never treat file as physical Output proof or trigger Output ON. For malformed numeric values avoid crashing process at startup. This is explicit architect-approved fail-safe input validation, not an additional authorization gate.
6. Preserve existing timer semantics for this migration; changing wall-clock vs monotonic and AUTO vs Manual missing start timestamp requires separate policy review. Preserve 900s safety lease, R16=3 OPP and 72h charge fuse.

## Acceptance
- Before: exact serialized JSON keys/readback, preset and text grammar, both stop reasons, no premature clearing if verified OFF fails.
- After: exactly one writer and one in-memory truth; zero independent globals in live paths; application/UI no direct file writes; cold restart safe with malformed/valid legacy JSON.
- Tests fake-only, Windows + Linux when appropriate, git diff --check; no node104/HA/ESP/physical operations; no deployment until full release gate.
