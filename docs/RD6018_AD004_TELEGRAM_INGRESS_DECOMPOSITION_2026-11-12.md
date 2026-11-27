# RD6018 AD-004 — TELEGRAM INGRESS DECOMPOSITION (2026-11-12)
**ОСНОВНОЙ ПРИОРИТЕТ: ПОЛНАЯ ДЕКОМПОЗИЦИЯ И МОДУЛЬНОСТЬ. CHATGPT РЕШАЕТ АРХИТЕКТУРУ И ПРИНИМАЕТ РЕЗУЛЬТАТ. LUNA ИСПОЛНЯЕТ ОГРАНИЧЕННЫЕ ЗАДАЧИ.**

## Source facts
Report `.recipe-studio-local/REPORT_MOD_P6_3_HANDLER_AUDIT_20261112.txt` maps current text_message_handler and four called handlers.
- `off …` (text without slash) arms a FUTURE OFF condition and persists manual_off_state; exact `off` clears condition. Neither immediately switches Output OFF. The wording OFF does not imply physical STOP.
- Quick `V I` programs voltage and current via existing ExecutionPort.program_voltage_current (no ON), reads back HA state and reports per-value errors; conditions and readback tolerate +0.8s. Accepts 12–17V, 0.1–canonical MAX_STAGE_CURRENT. This is not equivalent to a START.
- Quick `V I timer/threshold` programs same V/I then persists delayed-off settings, even if setpoint write was not fully successful; that may be a policy issue but MUST preserve baseline until separately approved. No automatic ON.
- Profile-capacity handler builds OperatorIntent START and delegates to existing V3 production start route; absent route does not legacy-start.
- Custom wizard holds state in three dictionaries, validates steps/large-current confirmation, then submits to ManualUIRoute at completion. Wizard flow may enable Output via guarded Manual route; not from pure parser.
- AI dialog does telemetry/context reads and DeepSeek request, no physical write; optional external dependency and separate error UI.
- Existing CommandValidator / UserCommandAdapter is not currently handling quick numeric setpoint commands; do NOT route through its idle-only update command as it would change active-mode behavior.

## Architect decisions and sequence
1. Preserve exact publicly observed behavior and priority of text dispatch: permission → slash ignore → OFF-condition → quick 3/2 number → Custom wizard → capacity START → LLM.
2. Existing runtime/ui/commands/validation.py owns syntax parsing and pure validation. UI Telegram routing owns message responses; application use cases own command execution and state mutations; physical owner remains existing ExecutionPort. Do not create new framework/dispatcher or second owner.
3. P6-4 first makes **non-actuating contract tests** for quick numeric commands/condition arming and custom wizard: fake message, fake ExecutionPort, fake Hass reads, fake persistence, fake START route. Avoid physical device/network/Telegram bot startup; if fixture cannot avoid side effects, STOP and report. Do not modify production.
4. After P6-4 tests are independently accepted, separate *whole functions* by responsibility with thin backward-compatible imports; leave original dispatch stable until all tests are green. Formal ownership assignments require function-level evidence; do NOT move entire legacy module.
5. Retain all independent physical safety, R16=3 OPP, 900s lease and verified OFF. Never add a new authorization/signature/manual operator gate. No node104 deployment before full release acceptance.

## Acceptance
Report exact tests, false-positive inspection, changed-file allowlist, Windows .venv validation and deterministic UI fake interaction. No environment token in tests. No runtime import just for AST compatibility. Stage changes only after ChatGPT approval.
