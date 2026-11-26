"""Explicit, restart-scoped lifecycle for optional RD6018 integrations.

Core Charge/Safety/ExecutionPort are never modules here. A missing optional
package is skipped, while an installed-but-broken package fails visibly.
No runtime hot-unload, dynamic plugin discovery, or second composition root.
"""
from __future__ import annotations

import importlib
import importlib.util
import inspect
import os
from dataclasses import dataclass
from typing import Any


class ModuleUnavailable(RuntimeError):
    """Optional feature is absent or explicitly disabled, not a core failure."""


@dataclass(frozen=True)
class ModuleSpec:
    name: str
    package: str
    installer_module: str
    installer_name: str = "install"
    requires_ui: bool = False


OPTIONAL_MODULES = (
    ModuleSpec("ai", "integrations.ai", "integrations.ai.module", requires_ui=True),
)

_TRUE = {"1", "true", "yes", "on", "enabled"}
_FALSE = {"0", "false", "no", "off", "disabled"}


def configured_enabled(name: str) -> bool:
    """Configuration takes effect on startup; missing means enabled-by-default."""
    value = os.getenv(f"RD6018_MODULE_{name.upper()}")
    if value is None:
        return True
    normalized = value.strip().lower()
    if normalized in _TRUE:
        return True
    if normalized in _FALSE:
        return False
    raise ValueError(f"invalid RD6018_MODULE_{name.upper()} setting")


def package_present(package: str) -> bool:
    """Probe without importing the optional package implementation."""
    try:
        return importlib.util.find_spec(package) is not None
    except ModuleNotFoundError as exc:
        if package == exc.name or package.startswith(f"{exc.name}."):
            return False
        raise


def optional_export(package: str, attribute: str, *, module: str = "ai") -> Any | None:
    """Lazy compatibility resolver. Never turn a broken installed module into a silent skip."""
    if not configured_enabled(module) or not package_present(f"integrations.{module}"):
        return None
    return getattr(importlib.import_module(package), attribute)


def optional_ui_enabled(name: str) -> bool:
    """One read-only availability rule shared by module UI affordances."""
    if not configured_enabled(name):
        return False
    if str(os.getenv("V2_UI", "1")).strip().lower() in _FALSE:
        return False
    return package_present(f"integrations.{name}")


class ModuleManager:
    """Small allowlisted startup installer; does not own application state or hardware."""

    def __init__(self, modules: tuple[ModuleSpec, ...] = OPTIONAL_MODULES) -> None:
        self._specs = {spec.name: spec for spec in modules}
        if len(self._specs) != len(modules):
            raise ValueError("duplicate optional module names")
        self._active: dict[str, Any] = {}

    def status(self, name: str) -> str:
        spec = self._specs[name]
        if not configured_enabled(name):
            return "disabled"
        if not package_present(spec.package):
            return "missing"
        if name in self._active:
            return "installed"
        return "available"

    def statuses(self) -> dict[str, str]:
        return {name: self.status(name) for name in self._specs}

    def installed(self, name: str) -> bool:
        return name in self._active

    def install(self, name: str, app: Any, *, ui_enabled: bool = True) -> bool:
        spec = self._specs[name]
        if self.installed(name):
            return True
        if spec.requires_ui and not ui_enabled:
            return False
        if self.status(name) in {"disabled", "missing"}:
            return False
        module = importlib.import_module(spec.installer_module)
        installer = getattr(module, spec.installer_name)
        if not callable(installer):
            raise TypeError(f"optional module {name} lacks a callable installer")
        installer(app)
        self._active[name] = module
        return True

    def install_all(self, app: Any, *, ui_enabled: bool = True) -> dict[str, str]:
        for name in self._specs:
            self.install(name, app, ui_enabled=ui_enabled)
        return self.statuses()

    async def shutdown(self, app: Any) -> None:
        """Optional stop hooks, reverse order. App shutdown is still owned by composition."""
        for name, module in reversed(tuple(self._active.items())):
            hook = getattr(module, "shutdown", None)
            if callable(hook):
                outcome = hook(app)
                if inspect.isawaitable(outcome):
                    await outcome
            self._active.pop(name, None)


__all__ = [
    "ModuleManager", "ModuleSpec", "ModuleUnavailable", "OPTIONAL_MODULES",
    "configured_enabled", "package_present", "optional_export",
    "optional_ui_enabled",
]



def main(argv: list[str] | None = None) -> int:
    """Read-only operator status. Enable/disable is config + normal restart."""
    import json
    import sys
    args = sys.argv[1:] if argv is None else argv
    if args not in ([], ["status"]):
        raise SystemExit("usage: python -m runtime.optional_modules [status]")
    print(json.dumps(ModuleManager().statuses(), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
