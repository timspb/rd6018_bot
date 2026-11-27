"""B1057: installed firmware Output API is mandatory before managed START side effects."""
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock

from aioesphomeapi.model import UserServiceArgType
from runtime.physical.transports.esp128 import ESPHomeTransport
from runtime.config.models import PhysicalTransportConfig, ConnectionConfig, RDConfig
from application.execution_port import ExecutionPort

TextSensorInfo = type("TextSensorInfo", (), {})
SwitchInfo = type("SwitchInfo", (), {})

def transport(services=True, status=True):
    cfg = PhysicalTransportConfig(
        name="esp128", type="esphome", enabled=True, priority=1,
        connection=ConnectionConfig("127.0.0.1", 6053),
        entities={"output_command_status": "rd6018_output_command_status"},
    )
    t = ESPHomeTransport(cfg, RDConfig(60.0, 18.0, 1000.0))
    t.client = SimpleNamespace(is_connected=True)
    t.services = (SimpleNamespace(name="rd6018_output_command", args=[
        SimpleNamespace(name="request_id", type=UserServiceArgType.STRING),
        SimpleNamespace(name="enabled", type=UserServiceArgType.BOOL),
    ]),) if services else ()
    if status:
        info = TextSensorInfo()
        info.object_id = "rd6018_output_command_status"
        t.entities = (info,)
    else:
        info = SwitchInfo()
        info.object_id = "output"
        t.entities = (info,)
    t._ensure_connected = AsyncMock()
    return t

class NativeOutputContractTests(unittest.IsolatedAsyncioTestCase):
    async def test_missing_api_service_fails_without_actuation(self):
        t = transport(services=False)
        t.command_output_with_receipt = AsyncMock()
        with self.assertRaisesRegex(RuntimeError, "rd6018_output_command absent"):
            await t.verify_output_command_contract()
        t.command_output_with_receipt.assert_not_awaited()

    async def test_wrong_action_arguments_fail_before_actuation(self):
        t = transport()
        t.services[0].args[0].type = UserServiceArgType.INT
        with self.assertRaisesRegex(RuntimeError, "action arguments incompatible"):
            await t.verify_output_command_contract()

    async def test_duplicate_action_fails_closed(self):
        t = transport()
        t.services = (t.services[0], t.services[0])
        with self.assertRaisesRegex(RuntimeError, "absent/ambiguous"):
            await t.verify_output_command_contract()

    async def test_switch_is_not_an_api_action_or_receipt(self):
        t = transport(status=False)
        with self.assertRaisesRegex(RuntimeError, "receipt status TextSensor absent"):
            await t.verify_output_command_contract()

    async def test_ready_contract_permits_only_read_only_inventory(self):
        t = transport()
        t.command_output_with_receipt = AsyncMock()
        await t.verify_output_command_contract()
        t.command_output_with_receipt.assert_not_awaited()

    async def test_disconnected_native_transport_rejected(self):
        t = transport()
        t.client = SimpleNamespace(is_connected=False)
        with self.assertRaisesRegex(RuntimeError, "transport disconnected"):
            await t.verify_output_command_contract()

    async def test_execution_port_delegates_to_single_adapter_owner(self):
        checker = AsyncMock()
        owner = SimpleNamespace(adapter=SimpleNamespace(verify_output_command_contract=checker))
        port = ExecutionPort(owner)
        await port.verify_managed_start_output_contract()
        checker.assert_awaited_once_with()

    async def test_execution_port_fails_closed_without_adapter(self):
        port = ExecutionPort(SimpleNamespace())
        with self.assertRaisesRegex(RuntimeError, "lacks Native Output contract checker"):
            await port.verify_managed_start_output_contract()
