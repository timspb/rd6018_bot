# RD6018 START Boundary Investigation — WORKSTREAM 83

Статус: `START_BOUNDARY_FOUND`

## 1. Writer `manual_session_v2.json`

Canonical writer — `ManualSessionManager` / production subclass
`ProductionManualSessionManager` в `manual_mode.py` / `manual_runtime_v2.py`.

`ManualSessionManager._persist()` атомарно пишет `manual_session_v2.json` через
temporary file + `os.replace`. Основные вызовы находятся в manual lifecycle:

- до safe-enable: ARMING state;
- после failed enable;
- после successful enable;
- STOP/COOLING/phase transitions;
- restore/recovery paths.

`ProductionManualSessionManager` расширяет документ, но не является отдельным
физическим writer.

## 2. Canonical START source

Для Manual path canonical START создаётся только в
`ManualSessionManager.start()`:

1. создаётся identity;
2. состояние переводится в `ARMING`;
3. вызывается `app.hass.safe_enable_output(...)`;
4. только после подтверждённого enable создаётся `EventType.SESSION_STARTED`;
5. затем сохраняется active session.

Отдельный V2 production path в `v2_bot_ui._start_profile()` делает другую
цепочку:

`charge_controller.start()` → `_apply_phase_protection()` → `set_voltage()` →
`set_current()` → `hass.turn_on()` → V2 log event.

Этот path не вызывает `ProductionManualSessionManager.start()`, не пишет
`manual_session_v2.json` и не эмитит Manual canonical `SESSION_STARTED`.

## 3. Boundary finding

Физический Output ON может быть достигнут через V2 UI/controller path, тогда
как Manual session identity/state живут в отдельном manager. Поэтому физическое
событие не является достаточным доказательством canonical Manual START.

Observed result:

- HA output state changed to `1`;
- measured output became approximately `12.84 V / 0.39 A`;
- `manual_session_v2.json` remained `state=stopped`;
- no canonical Manual START/trace/session identity appeared.

Это boundary mismatch, а не synthetic-event gap.

## 4. Timestamp correlation

| Marker | Evidence | Result |
|---|---|---|
| T0 | `ws81-20260915T130058Z`, observer armed | `2026-09-15T13:00:58Z` |
| T1 | exact requested-action timestamp | не exposed by read-only sources |
| T2 | HA output state `last_changed`, code `0 → 1` | примерно `2026-09-15T13:08:46.476Z` |
| T3 | `manual_session_v2.json` / canonical Manual event | отсутствует; state remains `stopped` |

Setpoint readbacks at the delayed sample were `13.0 V / 0.4 A`. They are
configuration/readback evidence, not a canonical session START.

## 5. Scope and safety

Аудит read-only. Runtime, session state, FSM, physical control и ownership не
изменялись. Synthetic events, synthetic identity и reconstructed timeline не
создавались.

Исправление boundary не выполнялось; документ фиксирует источник расхождения
для отдельного migration decision.
