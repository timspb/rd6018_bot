"""Explicit subclasses call original exact-SHA sinks after supplemental gates.

Canonical turn_off is containment and stays immediate. Ordinary acceptance
stops enter ordinary_off at their typed operation boundary. Direct low-level
OFF calls are ordinary unless canonical containment supplies fault_off.
"""
import time
from datetime import datetime

from hass_api import HassClient
from managed_runtime_safety import ManagedRuntimeSafetyGuard
from physical_test_control import PhysicalTestControl
from runtime.physical.connectors.esp_direct import ESPDirectConnector
from runtime.physical.connectors.ha_esp import HAESPConnector
from runtime.physical.transports.esp128 import ESPHomeTransport
from runtime.physical.transports.ha102 import HA102Transport
from .guard import fault_off, ordinary_off, is_ordinary_off, is_fault_off


class GuardedNativeTransport(ESPHomeTransport):
    def _on_state(self, state):
        super()._on_state(state)
        wanted = self.config.entities.get('output_state')
        for entity in self._entities_by_key.get(int(state.key), ()):
            if str(entity.object_id) == wanted and type(entity).__name__ == 'SensorInfo' and type(state).__name__ == 'SensorState':
                value = getattr(state, 'state', None)
                updated = self._state_updated_at.get(('SensorInfo', int(entity.key)))
                self.guard.observe(value == 1, updated,
                    valid=updated is not None and not getattr(state, 'missing_state', False) and value in (0, 1))

    def _on_connection_closed(self, event):
        self.guard.observe(None, None, valid=False)
        super()._on_connection_closed(event)


class GuardedHATransport(HA102Transport):
    async def _get(self, entity_id):
        data = await super()._get(entity_id)
        if entity_id == self.config.entities.get('output_state'):
            stamp = data.get('last_reported')
            try:
                age = time.time() - datetime.fromisoformat(stamp.replace('Z', '+00:00')).timestamp()
                value = float(data['state'])
                if stamp != getattr(self, '_guard_last_stamp', None):
                    self._guard_last_stamp = stamp
                    self.guard.observe(value == 1, self.guard.clock() - age,
                        valid=value in (0, 1) and 0 <= age <= self.guard.MAX_GAP_S)
            except (ValueError, TypeError, KeyError, AttributeError):
                self.guard.observe(None, None, valid=False)
        return data


class ConnectorGate:
    async def enable_output(self):
        return await self.guard.transition(True, super().enable_output)

    async def disable_output(self):
        return await self.guard.transition(False, super().disable_output)

    async def set_voltage(self, value):
        self.guard.voltage(value)
        return await super().set_voltage(value)

    async def _set_number(self, key, value):
        if key == 'control_voltage':
            self.guard.voltage(value)
        return await super()._set_number(key, value)


class GuardedHAConnector(ConnectorGate, HAESPConnector):
    def __init__(self, config, guard):
        self.guard = guard
        self.transport = GuardedHATransport(config.transports['ha102'], config.rd)
        self.transport.guard = guard


class GuardedESPConnector(ConnectorGate, ESPDirectConnector):
    def __init__(self, config, guard):
        self.guard = guard
        self.transport = GuardedNativeTransport(config.transports['esp128'], config.rd)
        self.transport.guard = guard


class GuardedHassClient(HassClient):
    def __init__(self, *args, guard, **kwargs):
        super().__init__(*args, **kwargs)
        self.guard = guard

    async def _switch_service(self, service, entity_id=None):
        original = super()._switch_service
        if service in ('turn_on', 'turn_off'):
            return await self.guard.transition(service == 'turn_on',
                lambda: original(service, entity_id))
        return await original(service, entity_id)

    async def set_voltage(self, value):
        self.guard.voltage(value)
        return await super().set_voltage(value)

    async def turn_off(self, entity_id=None):
        if is_ordinary_off():
            return await super().turn_off(entity_id)
        with fault_off():
            return await super().turn_off(entity_id)

    async def turn_on(self, entity_id=None):
        # Canonical post-enable rejection uses _switch_service(OFF) directly.
        # Its OFF retains immediate containment; ON still earns the normal gate.
        with fault_off():
            return await super().turn_on(entity_id)

    async def safe_enable_output(self, **kwargs):
        self.guard.voltage(kwargs.get('voltage_v'))
        # SafeOutputCoordinator's turn_off calls are failure rollback only.
        # Keep its original transaction/policy implementation and immediate OFF.
        with fault_off():
            return await super().safe_enable_output(**kwargs)


class GuardedD061Control(PhysicalTestControl):
    async def dispatch(self, request):
        # Adoption may enter canonical ambiguity containment while ownership
        # is still HANDS_OFF. It must not be classified as an operator OFF.
        if isinstance(request, dict) and (request.get('op') == 'd061_adopt_battery'
                or str(request.get('op', '')).startswith('d061_fault_')):
            with fault_off():
                return await super().dispatch(request)
        return await super().dispatch(request)

    async def _verified_stop(self):
        # Reject before canonical coordinator retires software or persists OFF_PENDING.
        original = super()._verified_stop
        with ordinary_off():
            # Keep the one OFF transaction permit through canonical verification
            # and OFF retries. A retry is containment of this command, not a new
            # ordinary flip. Concurrent tasks still cannot reuse its permit.
            return await self.acceptance_guard.transition(False, original)


class GuardedRuntimeSafety(ManagedRuntimeSafetyGuard):
    """Classify ordinary shutdown at the existing canonical owner boundary.

    The canonical install() binds these methods using its own supported
    installation contract. Original safety logic, locks, OFF retries and lease
    verification are inherited intact; only acceptance scopes are added.
    """

    async def turn_off(self, entity_id=None):
        original = super().turn_off
        # Fault cleanup reaches the same API from Manual/adoption background
        # tasks. Only an explicitly typed ordinary operation may earn dwell.
        if is_fault_off() or not is_ordinary_off():
            return await original(entity_id)
        with ordinary_off():
            return await self.acceptance_guard.transition(False,
                lambda: original(entity_id))

    async def _ensure_output_off(self, reason, entity_id=None):
        original = super()._ensure_output_off
        if reason == 'explicit HANDS_OFF Output OFF' and not is_fault_off():
            with ordinary_off():
                return await self.acceptance_guard.transition(False,
                    lambda: original(reason, entity_id))
        if is_ordinary_off() and reason == 'requested output shutdown':
            return await original(reason, entity_id)
        with fault_off():
            return await original(reason, entity_id)


class AcceptanceUpdatesOnly:
    """The D061 socket is the only operator mutation surface in this pairing.

    Use the existing canonical poller, but do not dispatch Telegram updates to
    arbitrary AUTO/Manual/start/stop handlers during the monitored procedure.
    No handler or fault protection is replaced.
    """
    async def __call__(self, handler, event, data):
        return None
