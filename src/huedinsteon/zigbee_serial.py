# SPDX-License-Identifier: Apache-2.0
"""Serial adapter for the custom CC2652P firmware."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
import logging
from typing import Any

from .config import SerialConfig
from .models import LightState, ZigbeeCommand
from .protocol import HealthStatus, decode_line, encode_message, ZigbeeReport

LOGGER = logging.getLogger(__name__)


class SerialZigbeeAdapter:
    def __init__(self, config: SerialConfig) -> None:
        self.config = config
        self._serial: Any | None = None
        self._write_lock = asyncio.Lock()

    async def start(self) -> None:
        try:
            import serial
        except ImportError as err:
            raise RuntimeError("pyserial is required for SerialZigbeeAdapter") from err

        self._serial = serial.Serial(
            self.config.port,
            baudrate=self.config.baudrate,
            timeout=1.0,
            write_timeout=1.0,
        )
        LOGGER.info("opened Zigbee serial port %s at %s baud", self.config.port, self.config.baudrate)

    async def stop(self) -> None:
        if self._serial is not None:
            self._serial.close()
            self._serial = None

    async def report_state(self, endpoint: int, state: LightState) -> None:
        self._require_started()
        payload = encode_message(ZigbeeReport(endpoint=endpoint, state=state))
        async with self._write_lock:
            await asyncio.to_thread(self._serial.write, payload)
            await asyncio.to_thread(self._serial.flush)

    async def events(self) -> AsyncIterator[ZigbeeCommand]:
        self._require_started()
        while True:
            raw = await asyncio.to_thread(self._serial.readline)
            if not raw:
                continue
            message = decode_line(raw)
            if isinstance(message, ZigbeeCommand):
                yield message
            elif isinstance(message, HealthStatus):
                LOGGER.info(
                    "zigbee health joined=%s endpoints=%s ieee=%s nwk=%s",
                    message.joined,
                    message.endpoints,
                    message.ieee,
                    message.nwk,
                )

    def _require_started(self) -> None:
        if self._serial is None:
            raise RuntimeError("SerialZigbeeAdapter is not started")

