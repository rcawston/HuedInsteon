# SPDX-License-Identifier: Apache-2.0
"""Adapter interfaces used by the bridge core."""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Protocol

from .models import InsteonEvent, LightState, ZigbeeCommand


class InsteonAdapter(Protocol):
    async def start(self) -> None:
        pass

    async def stop(self) -> None:
        pass

    async def set_light(self, bank_id: str, state: LightState) -> None:
        pass

    def events(self) -> AsyncIterator[InsteonEvent]:
        pass


class ZigbeeAdapter(Protocol):
    async def start(self) -> None:
        pass

    async def stop(self) -> None:
        pass

    async def report_state(self, endpoint: int, state: LightState) -> None:
        pass

    def events(self) -> AsyncIterator[ZigbeeCommand]:
        pass

