"""Mutable operator OFF-condition state and its legacy JSON storage."""

from __future__ import annotations

import json
import logging
import math
import os
import tempfile
import time
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class OperatorOffConditions:
    """One explicit in-memory representation of the six legacy OFF fields."""

    voltage_ge: float | None = None
    voltage_le: float | None = None
    current_le: float | None = None
    current_ge: float | None = None
    time_sec: float | None = None
    start_time: float = 0.0

    def apply_preset(self, preset: str, *, now_s: float | None = None) -> str:
        """Apply one supported operator OFF preset to this owned state."""
        if preset == "time_2h":
            document = {"time_sec": 2 * 3600, "start_time": time.time() if now_s is None else now_s}
            text = "✅ Preset применён: выключение через 2 часа."
        elif preset == "i_le_030":
            document = {"current_le": 0.30}
            text = "✅ Preset применён: выключение при I≤0.30 A."
        elif preset == "v_ge_162":
            document = {"voltage_ge": 16.2}
            text = "✅ Preset применён: выключение при V≥16.2 V."
        elif preset == "clear":
            self.clear()
            return "✅ Условие выключения сброшено."
        else:
            self.clear()
            raise ValueError("unknown_off_preset")

        if not self.update_from_document(document):
            self.clear()
            raise ValueError("invalid_off_preset")
        return text

    def has_condition(self) -> bool:
        return any(
            value is not None
            for value in (
                self.voltage_ge,
                self.voltage_le,
                self.current_le,
                self.current_ge,
                self.time_sec,
            )
        )

    def evaluate_reason(
        self, voltage_v: float, current_a: float, *, now_s: float, reach_eps: float
    ) -> str | None:
        """Return the armed OFF reason for one caller-supplied sample."""
        off_reason = None
        # «Достигли» V: оба порога заданы и равны — выкл при |V - value| <= eps
        if (
            self.voltage_ge is not None
            and self.voltage_le is not None
            and abs(self.voltage_ge - self.voltage_le) < 0.01
        ):
            if abs(voltage_v - self.voltage_ge) <= reach_eps:
                off_reason = f"напряжение достигло {self.voltage_ge:.2f} В (сейчас {voltage_v:.2f} В)"
        elif self.voltage_ge is not None and voltage_v >= self.voltage_ge:
            off_reason = f"напряжение {voltage_v:.2f} В ≥ {self.voltage_ge:.1f} В"
        elif self.voltage_le is not None and voltage_v <= self.voltage_le:
            off_reason = f"напряжение {voltage_v:.2f} В ≤ {self.voltage_le:.1f} В"

        # «Достигли» I: оба порога заданы и равны — выкл при |I - value| <= eps
        if off_reason is None:
            if (
                self.current_le is not None
                and self.current_ge is not None
                and abs(self.current_le - self.current_ge) < 0.01
            ):
                if abs(current_a - self.current_le) <= reach_eps:
                    off_reason = f"ток достиг {self.current_le:.2f} А (сейчас {current_a:.2f} А)"
            elif self.current_le is not None and current_a <= self.current_le:
                off_reason = off_reason or f"ток {current_a:.2f} А ≤ {self.current_le:.2f} А"
            elif self.current_ge is not None and current_a >= self.current_ge:
                off_reason = off_reason or f"ток {current_a:.2f} А ≥ {self.current_ge:.2f} А"
        if self.time_sec is not None and (now_s - self.start_time) >= self.time_sec:
            off_reason = off_reason or f"таймер {self.time_sec / 3600:.1f} ч"
        return off_reason

    def clear(self, path: str | os.PathLike[str] | None = None) -> None:
        """Reset memory and, when supplied, safely remove its storage file."""
        self.voltage_ge = None
        self.voltage_le = None
        self.current_le = None
        self.current_ge = None
        self.time_sec = None
        self.start_time = 0.0
        if path is not None:
            try:
                Path(path).unlink()
            except FileNotFoundError:
                pass
            except OSError as exc:
                logger.warning("Could not remove operator OFF-condition state: %s", exc)

    def to_document(self) -> dict[str, float | None]:
        return {
            "voltage_ge": self.voltage_ge,
            "voltage_le": self.voltage_le,
            "current_le": self.current_le,
            "current_ge": self.current_ge,
            "time_sec": self.time_sec,
            "start_time": self.start_time,
        }

    def update_from_document(self, document: Any) -> bool:
        """Atomically accept a legacy mapping, or clear/unarm on invalid input."""
        if not isinstance(document, Mapping):
            logger.warning("Ignoring invalid operator OFF-condition state: expected an object")
            self.clear()
            return False

        names = ("voltage_ge", "voltage_le", "current_le", "current_ge", "time_sec")
        parsed: dict[str, float | None] = {}
        try:
            for name in names:
                value = document.get(name)
                parsed[name] = self._finite_number(value, name) if value is not None else None
            raw_start = document.get("start_time")
            start_time = self._finite_number(raw_start, "start_time") if raw_start is not None else 0.0
            if parsed["time_sec"] is not None and parsed["time_sec"] < 0:
                raise ValueError("time_sec must be nonnegative")
            if start_time < 0:
                raise ValueError("start_time must be nonnegative")
        except (TypeError, ValueError, OverflowError) as exc:
            logger.warning("Ignoring invalid operator OFF-condition state: %s", exc)
            self.clear()
            return False

        self.voltage_ge = parsed["voltage_ge"]
        self.voltage_le = parsed["voltage_le"]
        self.current_le = parsed["current_le"]
        self.current_ge = parsed["current_ge"]
        self.time_sec = parsed["time_sec"]
        self.start_time = start_time
        return self.has_condition()

    @staticmethod
    def _finite_number(value: Any, name: str) -> float:
        if isinstance(value, bool):
            raise ValueError(f"{name} must be a number or null")
        try:
            result = float(value)
        except (TypeError, ValueError, OverflowError) as exc:
            raise ValueError(f"{name} must be a number or null") from exc
        if not math.isfinite(result):
            raise ValueError(f"{name} must be finite")
        return result

    def load(self, path: str | os.PathLike[str]) -> bool:
        try:
            with Path(path).open("r", encoding="utf-8") as handle:
                document = json.load(handle)
        except FileNotFoundError:
            self.clear()
            return False
        except (OSError, json.JSONDecodeError, UnicodeError) as exc:
            logger.warning("Ignoring invalid operator OFF-condition file %s: %s", path, exc)
            self.clear()
            return False
        return self.update_from_document(document)

    def save(self, path: str | os.PathLike[str]) -> None:
        target = Path(path)
        if not self.has_condition():
            self.clear(target)
            return

        temporary_path: str | None = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w", encoding="utf-8", dir=str(target.parent),
                prefix=f".{target.name}.", suffix=".tmp", delete=False,
            ) as handle:
                temporary_path = handle.name
                json.dump(self.to_document(), handle, ensure_ascii=False)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary_path, target)
            temporary_path = None
            if os.name == "posix" and hasattr(os, "O_DIRECTORY"):
                try:
                    directory_fd = os.open(target.parent, os.O_RDONLY | os.O_DIRECTORY)
                    try:
                        os.fsync(directory_fd)
                    finally:
                        os.close(directory_fd)
                except OSError:
                    logger.debug("Could not fsync operator OFF-condition directory", exc_info=True)
        except (OSError, TypeError, ValueError) as exc:
            logger.warning("Could not save operator OFF-condition state: %s", exc)
            if temporary_path is not None:
                try:
                    os.unlink(temporary_path)
                except FileNotFoundError:
                    pass
                except OSError:
                    logger.debug("Could not remove temporary OFF-condition state", exc_info=True)
