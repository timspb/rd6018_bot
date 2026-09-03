"""D062/D063 extension for the opt-in in-process physical-test control plane.

The production D062/D063 state machine already exists. This module only exposes a
small, conservative test surface through the existing root-only AF_UNIX control
socket so physical validation does not require Telegram callback synthesis.

No operation can turn Output ON or program V/I/OVP/OCP. The only D062 adoption
operation accepts a *remaining* chemistry budget constrained to 30..300 seconds;
it therefore creates an operator-declared prior-age floor near exhaustion and can
only reduce, never enlarge, the normal chemistry Mix budget.
"""

from __future__ import annotations

import math
from typing import Any, Dict, Optional

from battery_registry import get_battery
from ha_history import HomeAssistantHistoryError
from pb_domain import BatteryChemistry
from physical_test_control import (
    PhysicalTestControl,
    PhysicalTestControlError,
    _json_value,
)
from rd_live_adoption import MIX_HARD_LIMIT_HOURS
from rd_managed_mix import (
    ManagedMixPreview,
    PriorMixAge,
    PriorMixAgeSource,
    resolve_prior_mix_age,
)


_D062_OPS = {
    "d063_prior_age",
    "d062_adopt_test_budget",
    "d062_verified_stop",
}
_MIN_REMAINING_BUDGET_S = 30.0
_MAX_REMAINING_BUDGET_S = 300.0


def _enum_value(value: Any) -> Any:
    return getattr(value, "value", value)


class PhysicalTestControlD062:
    """Narrow D062/D063 dispatcher extension over the existing AF_UNIX server."""

    def __init__(self, app: Any, control: PhysicalTestControl) -> None:
        self.app = app
        self.control = control
        self._original_dispatch = control.dispatch
        self._original_status = control._status

    @staticmethod
    def _battery_id(value: Any) -> str:
        if not isinstance(value, str):
            raise PhysicalTestControlError("battery_id is invalid")
        battery_id = value.strip()
        if not battery_id or len(battery_id) > 128:
            raise PhysicalTestControlError("battery_id is invalid")
        return battery_id

    @staticmethod
    def _remaining_budget(value: Any) -> float:
        if value is None or isinstance(value, bool):
            raise PhysicalTestControlError("remaining_budget_s is invalid")
        try:
            parsed = float(value)
        except (TypeError, ValueError) as exc:
            raise PhysicalTestControlError("remaining_budget_s is invalid") from exc
        if (
            not math.isfinite(parsed)
            or parsed < _MIN_REMAINING_BUDGET_S
            or parsed > _MAX_REMAINING_BUDGET_S
        ):
            raise PhysicalTestControlError(
                "remaining_budget_s must be within 30..300 seconds"
            )
        return parsed

    async def _history(self, live: Dict[str, Any]) -> tuple[Optional[Any], str]:
        coordinator = getattr(self.app, "rd_managed_mix_adoption", None)
        reader = getattr(coordinator, "history_reader", None)
        read = getattr(reader, "read_mix_evidence", None)
        if not callable(read):
            return None, "Recorder reader unavailable"
        try:
            return await read(live=live), ""
        except HomeAssistantHistoryError as exc:
            return None, str(exc)

    @staticmethod
    def _history_result(history: Optional[Any], error: str) -> Dict[str, Any]:
        if history is None:
            return {
                "proven": False,
                "reliable": False,
                "started_at_s": None,
                "elapsed_s": None,
                "reason": error or "Recorder age unavailable",
                "fetched_at_s": None,
            }
        output = history.output
        proven = bool(output.reliable and output.elapsed_s is not None)
        return {
            "proven": proven,
            "reliable": bool(output.reliable),
            "started_at_s": output.started_at_s,
            "elapsed_s": output.elapsed_s if proven else None,
            "reason": str(output.reason),
            "fetched_at_s": history.fetched_at_s,
        }

    def _mix_status(self) -> Dict[str, Any]:
        coordinator = getattr(self.app, "rd_managed_mix_adoption", None)
        if coordinator is None:
            return {"available": False}
        return {
            "available": True,
            "state": _enum_value(getattr(coordinator, "state", None)),
            "battery_id": getattr(coordinator, "battery_id", ""),
            "chemistry": _enum_value(getattr(coordinator, "chemistry", None)),
            "prior_elapsed_s": float(getattr(coordinator, "prior_elapsed_s", 0.0) or 0.0),
            "prior_age_source": str(getattr(coordinator, "prior_age_source", "") or ""),
            "adopted_active_elapsed_s": float(
                getattr(coordinator, "adopted_active_elapsed_s", 0.0) or 0.0
            ),
            "total_active_elapsed_s": float(
                getattr(coordinator, "total_active_elapsed_s", 0.0) or 0.0
            ),
            "remaining_budget_s": getattr(coordinator, "remaining_budget_s", None),
            "max_authority": self.control._fingerprint(
                getattr(coordinator, "max_authority", None)
            ),
            "current_authority": self.control._fingerprint(
                getattr(coordinator, "current_authority", None)
            ),
            "finish_hold_started_at_s": getattr(
                coordinator, "finish_hold_started_at_s", None
            ),
            "terminal_reason": str(getattr(coordinator, "terminal_reason", "") or ""),
            "last_status": str(getattr(coordinator, "last_status", "") or ""),
        }

    async def status(self) -> Dict[str, Any]:
        result = await self._original_status()
        result["managed_mix"] = self._mix_status()
        return result

    async def prior_age(self) -> Dict[str, Any]:
        live = await self.control._raw_live()
        history, error = await self._history(live)
        result = self._history_result(history, error)
        result["output"] = live.get("switch")
        result["output_state_code_v2"] = live.get("output_state_code_v2")
        if result["proven"]:
            age = resolve_prior_mix_age(history)
            result["resolved_elapsed_s"] = age.elapsed_s
            result["source"] = age.source.value
        else:
            result["resolved_elapsed_s"] = None
            result["source"] = None
        return result

    async def adopt_test_budget(
        self,
        battery_id_raw: Any,
        remaining_budget_raw: Any,
    ) -> Dict[str, Any]:
        battery_id = self._battery_id(battery_id_raw)
        remaining_budget_s = self._remaining_budget(remaining_budget_raw)

        record = await get_battery(battery_id)
        if record is None:
            raise PhysicalTestControlError("battery is not present in registry")
        chemistry = record.identity.chemistry
        if chemistry is BatteryChemistry.CUSTOM or chemistry not in MIX_HARD_LIMIT_HOURS:
            raise PhysicalTestControlError("D062 test adoption requires supported Pb chemistry")

        manager = getattr(self.app, "rd_control_mode_manager", None)
        if manager is None or not bool(getattr(manager, "hands_off", False)):
            raise PhysicalTestControlError("D062 test adoption requires durable/in-memory HANDS_OFF")

        live = await self.control._raw_live()
        if not self.control._is_on(live):
            raise PhysicalTestControlError(
                "D062 test adoption requires positively confirmed Output ON"
            )

        coordinator = getattr(self.app, "rd_managed_mix_adoption", None)
        d061 = getattr(self.app, "rd_managed_live_adoption", None)
        if coordinator is None or d061 is None:
            raise PhysicalTestControlError("D062 coordinator unavailable")
        conflict = coordinator._conflict()
        if conflict is not None:
            raise PhysicalTestControlError(f"D062 blocked: {conflict}")

        fingerprint = d061._preflight_live(live)
        coordinator._chemistry_preflight(
            chemistry,
            record.identity.nominal_capacity_ah,
            fingerprint,
        )

        history, history_error = await self._history(live)
        hard_limit_s = float(MIX_HARD_LIMIT_HOURS[chemistry]) * 3600.0
        declared_elapsed_s = hard_limit_s - remaining_budget_s
        now = float(coordinator._wall_time())
        prior = resolve_prior_mix_age(
            history,
            declared_elapsed_s=declared_elapsed_s,
            declared_at_s=now,
            now_s=now,
        )
        # The local test operation is intentionally conservative. A Recorder age larger
        # than the near-exhausted declaration may reduce the remaining budget further,
        # but it must never create a new/fresher window.
        preview = ManagedMixPreview(
            token="physical-test:d062-near-budget",
            battery_id=record.identity.battery_id,
            chemistry=chemistry,
            capacity_ah=record.identity.nominal_capacity_ah,
            fingerprint=fingerprint,
            prior_age=prior,
            history=history,
        )
        adopted = bool(await coordinator.adopt(preview))
        return {
            "adopted": adopted,
            "battery_id": record.identity.battery_id,
            "chemistry": chemistry.value,
            "declared_elapsed_s": declared_elapsed_s,
            "requested_remaining_budget_s": remaining_budget_s,
            "accepted_prior_elapsed_s": coordinator.prior_elapsed_s,
            "accepted_prior_age_source": coordinator.prior_age_source,
            "remaining_budget_s": coordinator.remaining_budget_s,
            "recorder": self._history_result(history, history_error),
            "authority": self.control._fingerprint(
                getattr(coordinator, "current_authority", None)
            ),
        }

    async def verified_stop(self) -> Dict[str, Any]:
        coordinator = getattr(self.app, "rd_managed_mix_adoption", None)
        if coordinator is None or not bool(getattr(coordinator, "managed_authority", False)):
            raise PhysicalTestControlError(
                "d062_verified_stop requires active/off-pending MIX_ADOPTED authority"
            )
        ok = bool(await coordinator.stop_by_operator())
        live = await self.control._raw_live()
        if not ok or not self.control._is_off(live):
            raise PhysicalTestControlError(
                "D062 verified stop did not confirm authoritative Output OFF"
            )
        return {
            "stopped": True,
            "output": live.get("switch"),
            "output_state_code_v2": live.get("output_state_code_v2"),
            "state": _enum_value(coordinator.state),
        }

    async def dispatch(self, request: Any) -> Dict[str, Any]:
        if not isinstance(request, dict):
            return await self._original_dispatch(request)
        operation = request.get("op")
        if operation not in _D062_OPS:
            return await self._original_dispatch(request)
        try:
            async with self.control._operation_lock:
                if operation == "d063_prior_age":
                    self.control._require_fields(request, {"op"})
                    result = await self.prior_age()
                elif operation == "d062_adopt_test_budget":
                    self.control._require_fields(
                        request, {"op", "battery_id", "remaining_budget_s"}
                    )
                    result = await self.adopt_test_budget(
                        request["battery_id"],
                        request["remaining_budget_s"],
                    )
                else:
                    self.control._require_fields(request, {"op"})
                    result = await self.verified_stop()
            return {"ok": True, "operation": operation, "result": _json_value(result)}
        except (PhysicalTestControlError, ValueError, TypeError) as exc:
            return self.control._error(str(exc))
        except Exception as exc:
            return self.control._error(
                f"operation rejected: {type(exc).__name__}: {exc}"
            )


def install_physical_test_control_d062(
    app: Any,
    control: PhysicalTestControl,
) -> PhysicalTestControlD062:
    """Compose the D062/D063 test extension without creating another socket."""

    existing = getattr(app, "physical_test_control_d062", None)
    if isinstance(existing, PhysicalTestControlD062):
        return existing
    extension = PhysicalTestControlD062(app, control)
    control._status = extension.status
    control.dispatch = extension.dispatch
    app.physical_test_control_d062 = extension
    return extension
