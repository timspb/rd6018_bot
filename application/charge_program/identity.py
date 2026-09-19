"""Single authority for canonical program identities and external aliases."""

from __future__ import annotations

from dataclasses import dataclass

from .models import Chemistry


@dataclass(frozen=True)
class ProgramIdentity:
    canonical_id: str
    chemistry: Chemistry
    aliases: tuple[str, ...] = ()
    external_names: tuple[str, ...] = ()


class ProgramIdentityRegistry:
    def __init__(self, identities: tuple[ProgramIdentity, ...] | None = None) -> None:
        identities = identities or (
            ProgramIdentity("CALCIUM", Chemistry.CALCIUM, ("CA_CA", "KAK"), ("Ca/Ca",)),
            ProgramIdentity("EFB", Chemistry.EFB),
            ProgramIdentity("AGM", Chemistry.AGM),
        )
        self._identities = {item.canonical_id: item for item in identities}
        self._aliases: dict[str, str] = {}
        for item in identities:
            if not item.canonical_id.strip():
                raise ValueError("canonical program id is required")
            for name in (*item.aliases, *item.external_names):
                key = self._key(name)
                if key in self._aliases:
                    if self._aliases[key] == item.canonical_id:
                        continue
                    raise ValueError(f"duplicate program alias: {name}")
                if key in self._identities:
                    raise ValueError(f"alias collides with canonical id: {name}")
                self._aliases[key] = item.canonical_id

    @staticmethod
    def _key(value: str) -> str:
        return str(value).strip().upper().replace("/", "_").replace("-", "_")

    def resolve(self, external_name: str) -> ProgramIdentity:
        key = self._key(external_name)
        canonical = key if key in self._identities else self._aliases.get(key)
        if canonical is None:
            raise KeyError(f"unknown program identity: {external_name}")
        return self._identities[canonical]

    def canonical_id(self, external_name: str) -> str:
        return self.resolve(external_name).canonical_id

    def chemistry(self, external_name: str) -> Chemistry:
        return self.resolve(external_name).chemistry

    def program_id(self, external_name: str, *, mode: str) -> str:
        return f"{str(mode).strip().lower()}:{self.canonical_id(external_name).lower()}"

    def canonical_ids(self) -> tuple[str, ...]:
        return tuple(sorted(self._identities))


__all__ = ["ProgramIdentity", "ProgramIdentityRegistry"]
