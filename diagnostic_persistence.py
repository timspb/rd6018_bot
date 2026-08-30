from __future__ import annotations

import json
import os
import time
import uuid
from dataclasses import asdict, dataclass
from enum import Enum
from typing import Any, Dict, Iterable, List, Optional

from diagnostic_probe import ControlledCurrentProbe, ProbePlan, ProbeResult


DIAGNOSTIC_ACTION_FILE = "diagnostic_actions_v2.json"
DIAGNOSTIC_ACTION_VERSION = 1


class DiagnosticActionKind(str, Enum):
    PROBE = "probe"
    OPERATOR_CONFIRMATION = "operator_confirmation"
    EXPERT_HV_AUTHORIZATION = "expert_hv_authorization"
    REST_OBSERVATION = "rest_observation"
    FAULT_VERIFICATION = "fault_verification"


class DiagnosticActionStatus(str, Enum):
    RUNNING = "running"
    PENDING = "pending"
    ACTIVE = "active"
    COMPLETED = "completed"
    FAILED = "failed"
    ABORTED_RESTART = "aborted_restart"
    EXPIRED_RESTART = "expired_restart"
    REVOKED_RESTART = "revoked_restart"
    EXPIRED = "expired"
    CANCELLED = "cancelled"


_TERMINAL_STATUSES = frozenset(
    {
        DiagnosticActionStatus.COMPLETED,
        DiagnosticActionStatus.FAILED,
        DiagnosticActionStatus.ABORTED_RESTART,
        DiagnosticActionStatus.EXPIRED_RESTART,
        DiagnosticActionStatus.REVOKED_RESTART,
        DiagnosticActionStatus.EXPIRED,
        DiagnosticActionStatus.CANCELLED,
    }
)


@dataclass(frozen=True)
class DiagnosticActionRecord:
    action_id: str
    kind: DiagnosticActionKind
    battery_id: str
    status: DiagnosticActionStatus
    created_at: float
    updated_at: float
    expires_at: Optional[float] = None
    payload: Dict[str, Any] | None = None
    note: str = ""

    def to_json(self) -> Dict[str, Any]:
        result = asdict(self)
        result["kind"] = self.kind.value
        result["status"] = self.status.value
        result["payload"] = dict(self.payload or {})
        return result

    @classmethod
    def from_json(cls, raw: Dict[str, Any]) -> "DiagnosticActionRecord":
        return cls(
            action_id=str(raw["action_id"]),
            kind=DiagnosticActionKind(str(raw["kind"])),
            battery_id=str(raw.get("battery_id") or ""),
            status=DiagnosticActionStatus(str(raw["status"])),
            created_at=float(raw["created_at"]),
            updated_at=float(raw.get("updated_at") or raw["created_at"]),
            expires_at=(
                float(raw["expires_at"])
                if raw.get("expires_at") is not None
                else None
            ),
            payload=dict(raw.get("payload") or {}),
            note=str(raw.get("note") or ""),
        )


class DiagnosticActionJournal:
    """Durable journal for diagnostic *actions*, not derived diagnostic authority.

    Evidence may survive a restart. In-flight actions never do: a current probe is
    aborted, an operator confirmation must be requested again, and an expert-HV grant
    is revoked. A rest-observation window is the only active action allowed to survive
    because it has no actuator authority and cannot energize the charger.
    """

    def __init__(self, path: str = DIAGNOSTIC_ACTION_FILE) -> None:
        self.path = path
        self._records: List[DiagnosticActionRecord] = []
        self._load()

    @property
    def records(self) -> tuple[DiagnosticActionRecord, ...]:
        return tuple(self._records)

    def _load(self) -> None:
        if not os.path.exists(self.path):
            return
        try:
            with open(self.path, "r", encoding="utf-8") as handle:
                document = json.load(handle)
        except (OSError, json.JSONDecodeError, TypeError):
            return
        if int(document.get("version") or 0) != DIAGNOSTIC_ACTION_VERSION:
            return
        loaded: List[DiagnosticActionRecord] = []
        for raw in document.get("actions") or []:
            if not isinstance(raw, dict):
                continue
            try:
                loaded.append(DiagnosticActionRecord.from_json(raw))
            except (KeyError, TypeError, ValueError):
                continue
        self._records = loaded

    def _persist(self) -> None:
        document = {
            "version": DIAGNOSTIC_ACTION_VERSION,
            "saved_at": time.time(),
            "actions": [record.to_json() for record in self._records],
        }
        tmp = f"{self.path}.tmp"
        try:
            with open(tmp, "w", encoding="utf-8") as handle:
                json.dump(document, handle, ensure_ascii=False, indent=2, sort_keys=True)
            os.replace(tmp, self.path)
        except OSError:
            try:
                if os.path.exists(tmp):
                    os.remove(tmp)
            except OSError:
                pass
            raise

    def begin(
        self,
        kind: DiagnosticActionKind,
        *,
        battery_id: str = "",
        status: DiagnosticActionStatus = DiagnosticActionStatus.RUNNING,
        expires_at: Optional[float] = None,
        payload: Optional[Dict[str, Any]] = None,
        now: Optional[float] = None,
    ) -> DiagnosticActionRecord:
        timestamp = float(time.time() if now is None else now)
        record = DiagnosticActionRecord(
            action_id=uuid.uuid4().hex,
            kind=DiagnosticActionKind(kind),
            battery_id=str(battery_id or ""),
            status=DiagnosticActionStatus(status),
            created_at=timestamp,
            updated_at=timestamp,
            expires_at=float(expires_at) if expires_at is not None else None,
            payload=dict(payload or {}),
        )
        self._records.append(record)
        self._persist()
        return record

    def update(
        self,
        action_id: str,
        *,
        status: DiagnosticActionStatus,
        note: str = "",
        now: Optional[float] = None,
    ) -> DiagnosticActionRecord:
        timestamp = float(time.time() if now is None else now)
        for index, current in enumerate(self._records):
            if current.action_id != action_id:
                continue
            updated = DiagnosticActionRecord(
                action_id=current.action_id,
                kind=current.kind,
                battery_id=current.battery_id,
                status=DiagnosticActionStatus(status),
                created_at=current.created_at,
                updated_at=timestamp,
                expires_at=current.expires_at,
                payload=dict(current.payload or {}),
                note=str(note or ""),
            )
            self._records[index] = updated
            self._persist()
            return updated
        raise KeyError(action_id)

    def active(self, *, kind: Optional[DiagnosticActionKind] = None) -> List[DiagnosticActionRecord]:
        result: List[DiagnosticActionRecord] = []
        for record in self._records:
            if record.status in _TERMINAL_STATUSES:
                continue
            if kind is not None and record.kind is not DiagnosticActionKind(kind):
                continue
            result.append(record)
        return result

    def recover_after_restart(self, *, now: Optional[float] = None) -> List[DiagnosticActionRecord]:
        timestamp = float(time.time() if now is None else now)
        changed: List[DiagnosticActionRecord] = []
        next_records: List[DiagnosticActionRecord] = []
        for current in self._records:
            status = current.status
            note = current.note

            if status in _TERMINAL_STATUSES:
                next_records.append(current)
                continue

            if current.expires_at is not None and timestamp >= current.expires_at:
                status = DiagnosticActionStatus.EXPIRED
                note = "expired_by_time"
            elif current.kind is DiagnosticActionKind.REST_OBSERVATION:
                # Observation only: no actuator authority, so it may safely survive.
                next_records.append(current)
                continue
            elif current.kind is DiagnosticActionKind.PROBE:
                status = DiagnosticActionStatus.ABORTED_RESTART
                note = "probe_never_resumes_mid_step"
            elif current.kind in {
                DiagnosticActionKind.OPERATOR_CONFIRMATION,
                DiagnosticActionKind.FAULT_VERIFICATION,
            }:
                status = DiagnosticActionStatus.EXPIRED_RESTART
                note = "fresh_operator_or_evidence_confirmation_required"
            elif current.kind is DiagnosticActionKind.EXPERT_HV_AUTHORIZATION:
                status = DiagnosticActionStatus.REVOKED_RESTART
                note = "expert_hv_authorization_never_survives_restart"
            else:
                status = DiagnosticActionStatus.EXPIRED_RESTART
                note = "unknown_action_requires_fresh_authority"

            updated = DiagnosticActionRecord(
                action_id=current.action_id,
                kind=current.kind,
                battery_id=current.battery_id,
                status=status,
                created_at=current.created_at,
                updated_at=timestamp,
                expires_at=current.expires_at,
                payload=dict(current.payload or {}),
                note=note,
            )
            next_records.append(updated)
            changed.append(updated)

        if changed:
            self._records = next_records
            self._persist()
        return changed


class PersistentControlledCurrentProbe(ControlledCurrentProbe):
    """Controlled probe with crash-visible lifecycle journaling."""

    def __init__(self, hass: Any, journal: DiagnosticActionJournal) -> None:
        super().__init__(hass)
        self.journal = journal

    async def run(
        self,
        *,
        battery_id: str,
        stage: str,
        connection_id: str,
        plan: ProbePlan,
        notes: str = "",
    ) -> ProbeResult:
        action = self.journal.begin(
            DiagnosticActionKind.PROBE,
            battery_id=battery_id,
            status=DiagnosticActionStatus.RUNNING,
            payload={
                "stage": stage,
                "connection_id": connection_id,
                "step_current_a": plan.step_current_a,
                "notes": notes,
            },
        )
        try:
            result = await super().run(
                battery_id=battery_id,
                stage=stage,
                connection_id=connection_id,
                plan=plan,
                notes=notes,
            )
        except BaseException as exc:
            self.journal.update(
                action.action_id,
                status=DiagnosticActionStatus.FAILED,
                note=f"probe_exception:{type(exc).__name__}",
            )
            raise

        self.journal.update(
            action.action_id,
            status=(
                DiagnosticActionStatus.COMPLETED
                if result.ok
                else DiagnosticActionStatus.FAILED
            ),
            note=result.reason,
        )
        return result


def install_diagnostic_persistence(
    app: Any,
    *,
    path: str = DIAGNOSTIC_ACTION_FILE,
) -> DiagnosticActionJournal:
    existing = getattr(app, "diagnostic_action_journal", None)
    if isinstance(existing, DiagnosticActionJournal):
        return existing
    journal = DiagnosticActionJournal(path)
    app.diagnostic_action_journal = journal
    app.controlled_diagnostic_probe = PersistentControlledCurrentProbe(app.hass, journal)
    return journal


async def recover_diagnostic_persistence(app: Any) -> List[DiagnosticActionRecord]:
    journal = install_diagnostic_persistence(app)
    changed = journal.recover_after_restart()
    interrupted_probe = any(
        record.kind is DiagnosticActionKind.PROBE
        and record.status is DiagnosticActionStatus.ABORTED_RESTART
        for record in changed
    )
    if interrupted_probe:
        # A crash may have happened after the safer current step but before restoration.
        # Never guess the old setpoint on restart: force Output OFF and require a fresh
        # managed start. The edge lease should already fail closed; this is defense in depth.
        off_confirmed = False
        try:
            off_confirmed = bool(await app.hass.turn_off())
        except Exception:
            logger = getattr(app, "logger", None)
            if logger is not None:
                logger.exception("failed to force Output OFF after interrupted diagnostic probe")

        notify = getattr(app, "_charge_notify", None)
        if callable(notify):
            if off_confirmed:
                notify(
                    "⚠️ Предыдущая диагностическая проба была прервана перезапуском. "
                    "Проба помечена недействительной; Output подтверждён OFF.",
                    critical=True,
                )
            else:
                notify(
                    "🚨 Предыдущая диагностическая проба была прервана перезапуском. "
                    "Проба помечена недействительной, но Output OFF НЕ ПОДТВЕРЖДЁН. "
                    "Не возобновляйте заряд до проверки RD6018/HA; при необходимости "
                    "отключите выход или питание вручную.",
                    critical=True,
                )
    return changed
