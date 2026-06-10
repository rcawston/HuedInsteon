# SPDX-License-Identifier: Apache-2.0
"""Test and simulator adapters."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator

from .models import InsteonEvent, LightState, ZigbeeCommand, ZigbeeReport


class FakeInsteonAdapter:
    def __init__(self) -> None:
        self.started = False
        self.commands: list[tuple[str, LightState]] = []
        self._events: asyncio.Queue[InsteonEvent | None] = asyncio.Queue()

    async def start(self) -> None:
        self.started = True

    async def stop(self) -> None:
        self.started = False
        await self._events.put(None)

    async def set_light(self, bank_id: str, state: LightState) -> None:
        self.commands.append((bank_id, state))

    async def emit(self, event: InsteonEvent) -> None:
        await self._events.put(event)

    async def events(self) -> AsyncIterator[InsteonEvent]:
        while True:
            event = await self._events.get()
            if event is None:
                break
            yield event


class FakeZigbeeAdapter:
    def __init__(self) -> None:
        self.started = False
        self.reports: list[ZigbeeReport] = []
        self._events: asyncio.Queue[ZigbeeCommand | None] = asyncio.Queue()

    async def start(self) -> None:
        self.started = True

    async def stop(self) -> None:
        self.started = False
        await self._events.put(None)

    async def report_state(self, endpoint: int, state: LightState) -> None:
        self.reports.append(ZigbeeReport(endpoint=endpoint, state=state))

    async def emit(self, command: ZigbeeCommand) -> None:
        await self._events.put(command)

    async def events(self) -> AsyncIterator[ZigbeeCommand]:
        while True:
            event = await self._events.get()
            if event is None:
                break
            yield event

