# SPDX-License-Identifier: Apache-2.0
"""Bridge orchestration between Zigbee commands and Insteon events."""

from __future__ import annotations

import asyncio
import logging
import time

from .adapters import InsteonAdapter, ZigbeeAdapter
from .config import AppConfig
from .models import InsteonEvent, LightState, ZigbeeCommand

LOGGER = logging.getLogger(__name__)


class BridgeError(RuntimeError):
    pass


class HuedInsteonBridge:
    def __init__(
        self,
        config: AppConfig,
        *,
        insteon: InsteonAdapter,
        zigbee: ZigbeeAdapter,
    ) -> None:
        self.config = config
        self.insteon = insteon
        self.zigbee = zigbee
        self._bank_by_endpoint = config.bank_by_endpoint
        self._endpoint_by_bank = {bank.id: bank.endpoint for bank in config.banks}
        self._state_by_bank = {
            bank.id: LightState(on=False, level=bank.default_level, source="startup")
            for bank in config.banks
        }
        self._recent_hue_updates: dict[str, tuple[float, LightState]] = {}

    @property
    def state_by_bank(self) -> dict[str, LightState]:
        return dict(self._state_by_bank)

    async def start(self) -> None:
        await self.insteon.start()
        await self.zigbee.start()

    async def stop(self) -> None:
        await self.zigbee.stop()
        await self.insteon.stop()

    async def run(self) -> None:
        await self.start()
        try:
            await asyncio.gather(self._consume_zigbee(), self._consume_insteon())
        finally:
            await self.stop()

    async def handle_zigbee_command(self, command: ZigbeeCommand) -> LightState:
        bank = self._bank_by_endpoint.get(command.endpoint)
        if bank is None:
            raise BridgeError(f"unknown Zigbee endpoint: {command.endpoint}")

        previous = self._state_by_bank[bank.id]
        next_state = self._apply_zigbee_command(previous, command)
        self._state_by_bank[bank.id] = next_state

        LOGGER.info(
            "hue command bank=%s endpoint=%s command=%s on=%s level=%s seq=%s",
            bank.id,
            command.endpoint,
            command.command,
            next_state.on,
            next_state.level,
            command.seq,
        )
        await self.insteon.set_light(bank.id, next_state)
        self._recent_hue_updates[bank.id] = (time.monotonic(), next_state)

        if self.config.bridge.optimistic_hue_updates:
            await self.zigbee.report_state(command.endpoint, next_state)
        return next_state

    async def handle_insteon_event(self, event: InsteonEvent) -> LightState:
        endpoint = self._endpoint_by_bank.get(event.bank_id)
        if endpoint is None:
            raise BridgeError(f"unknown Insteon bank: {event.bank_id}")

        state = event.state.with_updates(source="insteon")
        self._state_by_bank[event.bank_id] = state

        if self._is_echo(event.bank_id, state):
            LOGGER.debug("suppressed echo bank=%s endpoint=%s", event.bank_id, endpoint)
            return state

        LOGGER.info(
            "insteon event bank=%s endpoint=%s on=%s level=%s seq=%s",
            event.bank_id,
            endpoint,
            state.on,
            state.level,
            state.seq,
        )
        await self.zigbee.report_state(endpoint, state)
        return state

    async def _consume_zigbee(self) -> None:
        async for command in self.zigbee.events():
            try:
                await self.handle_zigbee_command(command)
            except Exception:
                LOGGER.exception("failed to handle Zigbee command")

    async def _consume_insteon(self) -> None:
        async for event in self.insteon.events():
            try:
                await self.handle_insteon_event(event)
            except Exception:
                LOGGER.exception("failed to handle Insteon event")

    def _apply_zigbee_command(self, previous: LightState, command: ZigbeeCommand) -> LightState:
        if command.command == "on":
            return previous.with_updates(on=True, source="hue", transition_ms=command.transition_ms, seq=command.seq)
        if command.command == "off":
            return previous.with_updates(on=False, source="hue", transition_ms=command.transition_ms, seq=command.seq)
        if command.command == "toggle":
            return previous.with_updates(
                on=not previous.on,
                source="hue",
                transition_ms=command.transition_ms,
                seq=command.seq,
            )
        if command.command == "level":
            return previous.with_updates(
                on=True,
                level=command.level,
                source="hue",
                transition_ms=command.transition_ms,
                seq=command.seq,
            )
        if command.command in {"move", "step", "stop"}:
            LOGGER.warning("received unimplemented level-control command: %s", command.command)
            return previous.with_updates(source="hue", transition_ms=command.transition_ms, seq=command.seq)
        raise BridgeError(f"unsupported command: {command.command}")

    def _is_echo(self, bank_id: str, state: LightState) -> bool:
        recent = self._recent_hue_updates.get(bank_id)
        if recent is None:
            return False
        timestamp, hue_state = recent
        window_s = self.config.bridge.echo_suppression_ms / 1000
        if time.monotonic() - timestamp > window_s:
            return False
        return hue_state.on == state.on and hue_state.level == state.level
