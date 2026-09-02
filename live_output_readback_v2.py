from __future__ import annotations

from typing import Any, MutableMapping

from rd6018_telemetry import finite_float


OUTPUT_STATE_CODE_KEY = "output_state_code_v2"


def promote_output_state_readback(live: MutableMapping[str, Any]) -> MutableMapping[str, Any]:
    """Promote the force-updated read-only register-18 sensor to canonical Output truth.

    The public HA switch remains the actuator endpoint. Its state timestamp is not a
    reliable heartbeat when an unchanged ESPHome switch suppresses duplicate reports.
    The V2 read-only sensor is polled from the same physical register and publishes
    every poll, so it owns the canonical value *and* freshness metadata while present.
    """

    raw = finite_float(live.get(OUTPUT_STATE_CODE_KEY))
    if raw is None or abs(raw - round(raw)) > 1e-9:
        return live
    code = int(round(raw))
    if code not in {0, 1}:
        return live

    live["switch"] = "on" if code == 1 else "off"
    meta = live.get("_meta")
    if isinstance(meta, dict) and isinstance(meta.get(OUTPUT_STATE_CODE_KEY), dict):
        copied = dict(meta[OUTPUT_STATE_CODE_KEY])
        copied["source_key"] = OUTPUT_STATE_CODE_KEY
        meta["switch"] = copied
    return live


def install_output_state_readback(app: Any) -> None:
    hass = getattr(app, "hass", None)
    if hass is None or bool(getattr(hass, "_v2_output_state_readback_installed", False)):
        return

    original = hass.get_all_live

    async def get_all_live() -> dict[str, Any]:
        live = await original()
        return dict(promote_output_state_readback(live))

    hass.get_all_live = get_all_live
    hass._v2_output_state_readback_installed = True
