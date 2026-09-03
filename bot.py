"""Production entrypoint for the evidence-driven V2 UI/controller.

The previous monolithic Telegram runtime is kept byte-for-byte as bot_legacy.py.
Set V2_UI=0 to keep its UI, and V2_AUTHORITATIVE=0 as the independent actuator
rollback. Running bot_legacy.py directly is also available for emergency diagnosis.
"""
from __future__ import annotations

import asyncio
import os
import sys

import bot_legacy as _legacy
from auto_manual_off_v2 import install_auto_manual_off_contract
from diagnostic_persistence import (
    install_diagnostic_persistence,
    recover_diagnostic_persistence,
)
from live_output_readback_v2 import install_output_state_readback
from manual_context_v2 import (
    install_manual_context_preprocessor,
    install_manual_context_ui,
)
from operator_dashboard import install_operator_graph_dashboard
from operator_destructive_guard import install_operator_destructive_guard
from operator_hmi import install_operator_hmi
from operator_managed_stop import install_operator_managed_stop
from operator_mix_eligibility import install_mix_action_eligibility
from production_guardrails_v2 import install_production_guardrails
from rd_control_mode import install_rd_control_mode
from rd_hands_off_release import install_rd_hands_off_release
from rd_live_adoption import install_rd_live_adoption
from rd_managed_adoption import install_managed_live_adoption
from rd_managed_mix_adoption import install_managed_mix_adoption
from telegram_startup_resilience import install_telegram_startup_resilience
from v2_bootstrap import init_v2_storage, install_v2
from v2_mix_mode import install_mix_only_mode


def _env_enabled(name: str, default: bool = True) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return bool(default)
    return str(raw).strip().lower() not in {"0", "false", "no", "off", "disabled"}


# The battery-bound Manual preprocessor must be registered before the generic numeric
# Manual middleware installed by install_v2(); this gives an explicitly selected
# physical battery ownership of the next numeric message without changing Manual V/I.
install_manual_context_preprocessor(_legacy)

# Production controller + actuator safety are always installed. V2_UI controls only
# presentation, exactly as documented; rolling the Telegram UI back must not remove
# recipe envelopes, verified OFF, telemetry fail-close, or live protection readback.
_v2_ui_enabled = _env_enabled("V2_UI", True)
install_v2(_legacy, install_ui=_v2_ui_enabled)
# Telegram transport is not part of RD/edge safety authority, but a single transient
# DNS EAI_NODATA during aiogram bootstrap must not kill the production runtime before
# its local monitor/watchdog tasks come up. Restrict retry semantics to read-only getMe
# and idempotent setMyCommands; never replay arbitrary Telegram API writes.
install_telegram_startup_resilience(_legacy)
# The public ESPHome Output switch remains the actuator endpoint, but an unchanged
# switch state is not a source heartbeat. Prefer the V2 force-updated read-only
# register-18 sensor for canonical Output value/freshness whenever the matching
# firmware is present; absence remains fail-closed through the legacy path.
install_output_state_readback(_legacy)
# Composition guardrails close historical bot_legacy authority leaks without changing
# the V1 reference file itself: Vin becomes PSU-health-only and Cooling resume requires
# a complete durable V2 continuation token (SAFE_WAIT always remains Output OFF).
install_production_guardrails(_legacy)
install_auto_manual_off_contract(_legacy)
install_diagnostic_persistence(_legacy)
if _v2_ui_enabled:
    install_mix_only_mode(_legacy)
    install_manual_context_ui(_legacy)

# RD6018 is a general-purpose PSU above the Pb controller. Install this ownership
# boundary last so HANDS_OFF blocks every already-composed bot actuator path while
# leaving raw telemetry available and preserving the explicit operator-only OFF action.
_rd_control_mode = install_rd_control_mode(_legacy, install_ui=_v2_ui_enabled)
# A deliberate HANDS_OFF request may also release an already-running AUTO/Manual
# software session through the dedicated positively-ACKed live edge release. Ordinary
# edge disarm remains verified-OFF only.
install_rd_hands_off_release(_legacy, _rd_control_mode)
# While HANDS_OFF owns an externally-running RD program, the operator may attach the
# read-only/safety-OFF Mix observer. It imports HA Recorder history as context only;
# all Delta authority starts from fresh post-activation source reports.
_rd_live_mix_observer = (
    install_rd_live_adoption(_legacy, _rd_control_mode)
    if _v2_ui_enabled
    else None
)
# D061 managed live adoption is a different transaction: it can acquire the local
# dead-man around an already-ON Output, re-read the exact live program, and only then
# cross durable HANDS_OFF -> PB_MANAGED as an Adopted Manual. No Output/setpoint write
# occurs at the adoption point, and the captured V/I/OVP/OCP authority can only ratchet
# downward. Install the safety wrappers even with V2_UI disabled so restart containment
# of a previously adopted session cannot depend on presentation mode.
_rd_managed_live_adoption = install_managed_live_adoption(
    _legacy,
    _rd_control_mode,
    install_ui=_v2_ui_enabled,
)
# D062/D063 builds a separate MIX_ADOPTED authority on the physically same D061 edge
# primitive. It never masquerades as Manual/AUTO: prior active Mix time must be proven
# by Recorder or explicitly declared, the remaining Ca/EFB/AGM hard budget is carried
# into the managed session, Delta starts fresh after takeover, and normal completion is
# verified OFF rather than SAFE_WAIT/Storage. Runtime-safety composition is installed
# even with V2_UI disabled; the Telegram workflow itself follows V2_UI.
_rd_managed_mix_adoption = install_managed_mix_adoption(
    _legacy,
    _rd_control_mode,
    _rd_managed_live_adoption,
    install_ui=_v2_ui_enabled,
)
# The semantic L2/L3 operator station is the final presentation layer. It is installed
# after ownership and live-session wrappers so the panel describes their effective
# semantics rather than leaking the underlying composition/debug UI. Managed Stop is
# then converted from the legacy ON/OFF toggle into a session-bound L4 stop-only action;
# the graph-backed transport is composed underneath the final semantic state/controls.
if _v2_ui_enabled:
    install_operator_hmi(_legacy)
    # A second-step adopted-Mix OFF button in an old Telegram message must not remain
    # an indefinitely valid actuator capability. Bind it to the exact current observer
    # epoch before composing the remaining operator actions.
    install_operator_destructive_guard(_legacy)
    install_operator_managed_stop(_legacy)
    install_operator_graph_dashboard(_legacy)
    # Mix affordances are contextual, not generic HANDS_OFF+ON actions. Hide them for
    # setpoints that cannot be high-voltage Mix under any supported chemistry and gate
    # stale Telegram callback messages with the same live rule.
    install_mix_action_eligibility(_legacy)

_legacy_main = _legacy.main


async def main() -> None:
    await init_v2_storage()
    # Neither managed live-adoption authority is resumable. D062 is recovered first
    # because it owns a chemistry HV budget; if it was active/pending at crash, startup
    # may only continue toward verified OFF before any generic managed heartbeat starts.
    await _rd_managed_mix_adoption.recover_startup()
    # D061 Adopted Manual follows the same restart containment rule.
    await _rd_managed_live_adoption.recover_startup()
    # A normal HANDS_OFF observer also never resumes. If it had already committed final
    # OFF_PENDING, only that OFF containment is allowed to continue.
    if _rd_live_mix_observer is not None:
        await _rd_live_mix_observer.recover_startup()
    await recover_diagnostic_persistence(_legacy)
    await _legacy_main()


# Keep one runtime module object. Existing tests and operational helpers import many
# private bot symbols; aliasing preserves their globals/monkeypatch semantics instead
# of copying 180+ KB of names into this shim.
_legacy.main = main

if __name__ == "__main__":
    asyncio.run(main())
else:
    sys.modules[__name__] = _legacy
