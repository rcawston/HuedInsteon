# SPDX-License-Identifier: Apache-2.0
import asyncio

import pytest

from huedinsteon.bridge import BridgeError, HuedInsteonBridge
from huedinsteon.config import parse_config
from huedinsteon.fake_adapters import FakeInsteonAdapter, FakeZigbeeAdapter
from huedinsteon.models import InsteonEvent, LightState, ZigbeeCommand


def _config():
    return parse_config(
        {
            "zigbee": {"port": "/dev/ttyUSB0"},
            "insteon": {"port": "/dev/ttyUSB1"},
            "banks": [
                {"id": "bank_a", "name": "A", "endpoint": 1, "insteon_address": "11.22.33"},
                {"id": "bank_b", "name": "B", "endpoint": 2, "insteon_address": "22.33.44"},
            ],
        }
    )


def test_hue_level_command_maps_to_insteon_bank_and_reports_back():
    asyncio.run(_test_hue_level_command_maps_to_insteon_bank_and_reports_back())


async def _test_hue_level_command_maps_to_insteon_bank_and_reports_back():
    insteon = FakeInsteonAdapter()
    zigbee = FakeZigbeeAdapter()
    bridge = HuedInsteonBridge(_config(), insteon=insteon, zigbee=zigbee)

    state = await bridge.handle_zigbee_command(ZigbeeCommand(endpoint=2, command="level", level=128, seq=10))

    assert state == LightState(on=True, level=128, source="hue", seq=10)
    assert insteon.commands == [("bank_b", state)]
    assert len(zigbee.reports) == 1
    assert zigbee.reports[0].endpoint == 2
    assert zigbee.reports[0].state == state


def test_insteon_event_maps_to_zigbee_endpoint():
    asyncio.run(_test_insteon_event_maps_to_zigbee_endpoint())


async def _test_insteon_event_maps_to_zigbee_endpoint():
    insteon = FakeInsteonAdapter()
    zigbee = FakeZigbeeAdapter()
    bridge = HuedInsteonBridge(_config(), insteon=insteon, zigbee=zigbee)

    state = await bridge.handle_insteon_event(
        InsteonEvent(bank_id="bank_a", state=LightState(on=True, level=200, source="test"))
    )

    assert state.source == "insteon"
    assert zigbee.reports[0].endpoint == 1
    assert zigbee.reports[0].state.level == 200


def test_unknown_endpoint_is_rejected():
    asyncio.run(_test_unknown_endpoint_is_rejected())


async def _test_unknown_endpoint_is_rejected():
    bridge = HuedInsteonBridge(_config(), insteon=FakeInsteonAdapter(), zigbee=FakeZigbeeAdapter())

    with pytest.raises(BridgeError):
        await bridge.handle_zigbee_command(ZigbeeCommand(endpoint=9, command="on"))


def test_echo_from_hue_command_is_not_reported_twice():
    asyncio.run(_test_echo_from_hue_command_is_not_reported_twice())


async def _test_echo_from_hue_command_is_not_reported_twice():
    insteon = FakeInsteonAdapter()
    zigbee = FakeZigbeeAdapter()
    bridge = HuedInsteonBridge(_config(), insteon=insteon, zigbee=zigbee)

    await bridge.handle_zigbee_command(ZigbeeCommand(endpoint=1, command="level", level=150))
    await bridge.handle_insteon_event(InsteonEvent(bank_id="bank_a", state=LightState(on=True, level=150)))

    assert len(zigbee.reports) == 1
