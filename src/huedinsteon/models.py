# SPDX-License-Identifier: Apache-2.0
"""Shared domain models for the bridge."""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Literal

Source = Literal["hue", "insteon", "startup", "reconcile", "test"]


def clamp_level(level: int) -> int:
    """Clamp a brightness level to Hue/Zigbee's practical dimmer range."""
    return min(254, max(1, int(level)))


@dataclass(frozen=True)
class LightState:
    on: bool
    level: int
    source: Source | str = "startup"
    transition_ms: int = 0
    seq: int | None = None

    def __post_init__(self) -> None:
        if not 1 <= self.level <= 254:
            raise ValueError("level must be in the range 1..254")
        if self.transition_ms < 0:
            raise ValueError("transition_ms must be >= 0")

    def with_updates(
        self,
        *,
        on: bool | None = None,
        level: int | None = None,
        source: Source | str | None = None,
        transition_ms: int | None = None,
        seq: int | None = None,
    ) -> "LightState":
        return replace(
            self,
            on=self.on if on is None else on,
            level=self.level if level is None else clamp_level(level),
            source=self.source if source is None else source,
            transition_ms=self.transition_ms if transition_ms is None else transition_ms,
            seq=self.seq if seq is None else seq,
        )


@dataclass(frozen=True)
class InsteonEvent:
    bank_id: str
    state: LightState


@dataclass(frozen=True)
class ZigbeeCommand:
    endpoint: int
    command: Literal["on", "off", "toggle", "level", "move", "step", "stop"]
    level: int | None = None
    transition_ms: int = 0
    seq: int | None = None
    identity: int | None = None
    ieee: str | None = None
    nwk: str | None = None

    def __post_init__(self) -> None:
        if self.endpoint < 1:
            raise ValueError("endpoint must be >= 1")
        if self.identity is not None and self.identity < 1:
            raise ValueError("identity must be >= 1")
        if self.level is not None and not 1 <= self.level <= 254:
            raise ValueError("level must be in the range 1..254")
        if self.transition_ms < 0:
            raise ValueError("transition_ms must be >= 0")
        if self.command == "level" and self.level is None:
            raise ValueError("level command requires level")


@dataclass(frozen=True)
class ZigbeeReport:
    endpoint: int
    state: LightState

    def __post_init__(self) -> None:
        if self.endpoint < 1:
            raise ValueError("endpoint must be >= 1")
