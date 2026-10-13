"""Supplemental sink gate. Source reports, never fetches, earn dwell."""
import asyncio
from contextlib import contextmanager
from contextvars import ContextVar
import math
import time


class Blocked(RuntimeError):
    pass


_permit = ContextVar('acceptance_sink_permit', default=None)
_fault = ContextVar('acceptance_fault_off', default=None)
_ordinary = ContextVar('acceptance_ordinary_off', default=None)


@contextmanager
def ordinary_off():
    token = _ordinary.set(asyncio.current_task())
    try:
        yield
    finally:
        _ordinary.reset(token)


def is_ordinary_off():
    return _ordinary.get() is asyncio.current_task()


@contextmanager
def fault_off():
    token = _fault.set(asyncio.current_task())
    try:
        yield
    finally:
        _fault.reset(token)


def is_fault_off():
    return _fault.get() is asyncio.current_task()


class Guard:
    DWELL_S = 12.0
    MAX_GAP_S = 8.0  # More than one missed ~6s report earns no credit.

    def __init__(self, *, clock=time.monotonic, voltage_ceiling=14.7):
        self.clock = clock
        if (isinstance(voltage_ceiling, bool) or not isinstance(voltage_ceiling, (int, float))
                or not math.isfinite(voltage_ceiling) or voltage_ceiling <= 0):
            raise ValueError('invalid canonical chemistry ceiling')
        self.voltage_ceiling = min(15.5, voltage_ceiling)
        self.state = self.since = self.last_report = self.last_clock = None
        self.last_observed = None
        self.pending = None
        self.aborted = False

    def now(self):
        now = self.clock()
        if not math.isfinite(now) or (self.last_clock is not None and now < self.last_clock):
            self.state = self.since = self.last_report = None
            self.last_observed = None
            raise Blocked('invalid monotonic clock')
        self.last_clock = now
        return now

    def observe(self, output, report_monotonic, *, valid=True):
        now = self.now()
        if (type(output) is not bool or valid is not True
                or not isinstance(report_monotonic, (int, float))
                or not math.isfinite(report_monotonic)
                or not 0 <= now - report_monotonic <= self.MAX_GAP_S):
            self.state = self.since = self.last_report = None
            self.last_observed = None
            return
        if self.last_report is not None and report_monotonic <= self.last_report:
            # Cached/replayed reports cannot confirm delivery or age dwell forward.
            return
        if (self.state != output or self.last_report is None
                or report_monotonic - self.last_report > self.MAX_GAP_S
                or self.last_observed is None
                or now - self.last_observed > self.MAX_GAP_S):
            # A delayed first report cannot backdate observed stability. Both
            # source continuity and actual observation continuity are required.
            self.since = now
        self.state, self.last_report = output, report_monotonic
        self.last_observed = now
        if self.pending is not None:
            target, issued = self.pending
            if target == output and report_monotonic > issued:
                self.pending = None

    def voltage(self, value):
        if (isinstance(value, bool) or not isinstance(value, (int, float))
                or not math.isfinite(value) or not 0 < value <= self.voltage_ceiling
                or self.aborted or self.pending is not None):
            raise Blocked('voltage outside acceptance/canonical envelope or unresolved command')

    def require_transition(self, target):
        now = self.now()
        if (type(target) is not bool or self.aborted or self.pending is not None
                or self.last_report is None or self.since is None
                or now - self.last_report > self.MAX_GAP_S
                or self.last_report - self.since < self.DWELL_S
                or self.state == target):
            raise Blocked('12s verified monotonic stable evidence required; no pending command')

    async def transition(self, target, invoke):
        task = asyncio.current_task()
        if target is False and _fault.get() is task:
            # No clock, filesystem, report, lock, sleep or journal dependency.
            self.aborted = True
            return await invoke()
        if _permit.get() == (task, self, target):
            return await invoke()
        self.require_transition(target)
        self.pending = (target, self.now())  # Exceptions/cancellation remain ambiguous.
        token = _permit.set((task, self, target))
        try:
            return await invoke()
        finally:
            _permit.reset(token)
