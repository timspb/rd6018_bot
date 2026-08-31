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
from manual_context_v2 import (
    install_manual_context_preprocessor,
    install_manual_context_ui,
)
from production_guardrails_v2 import install_production_guardrails
from rd_control_mode import install_rd_control_mode
from rd_hands_off_release import install_rd_hands_off_release
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
# software session. That retirement is software-only: Output and V/I/OVP/OCP are left
# exactly as they were while the edge lease is positively disarmed.
install_rd_hands_off_release(_legacy, _rd_control_mode)

_legacy_main = _legacy.main


async def main() -> None:
    await init_v2_storage()
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
