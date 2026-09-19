"""Compatibility export for the single ProgramIdentityRegistry authority."""

from __future__ import annotations

from .identity import ProgramIdentityRegistry


class ProgramIdResolver:
    """Compatibility facade; all resolution delegates to one registry instance."""

    _registry = ProgramIdentityRegistry()

    @classmethod
    def chemistry(cls, external_name: str):
        return cls._registry.chemistry(external_name)

    @classmethod
    def program_id(cls, external_name: str, *, mode: str) -> str:
        return cls._registry.program_id(external_name, mode=mode)


__all__ = ["ProgramIdResolver"]
