# SPDX-License-Identifier: Apache-2.0
"""Newline-delimited JSON protocol between the Pi and CC2652P firmware."""

from __future__ import annotations

from dataclasses import dataclass
import json
from typing import Any

from .models import LightState, ZigbeeCommand, ZigbeeReport


class ProtocolError(ValueError):
    pass


@dataclass(frozen=True)
class HealthQuery:
    seq: int | None = None


@dataclass(frozen=True)
class HealthStatus:
    joined: bool
    endpoints: int
    ieee: str | None = None
    nwk: str | None = None
    seq: int | None = None


InboundMessage = ZigbeeCommand | HealthStatus
OutboundMessage = ZigbeeReport | HealthQuery


def encode_message(message: OutboundMessage) -> bytes:
    if isinstance(message, ZigbeeReport):
        payload: dict[str, Any] = {
            "dir": "pi->zb",
            "type": "report",
            "endpoint": message.endpoint,
            "on": message.state.on,
            "level": message.state.level,
            "source": message.state.source,
            "transition_ms": message.state.transition_ms,
        }
        if message.state.seq is not None:
            payload["seq"] = message.state.seq
    elif isinstance(message, HealthQuery):
        payload = {"dir": "pi->zb", "type": "health?"}
        if message.seq is not None:
            payload["seq"] = message.seq
    else:
        raise TypeError(f"unsupported message type: {type(message)!r}")
    return (json.dumps(payload, separators=(",", ":"), sort_keys=True) + "\n").encode("utf-8")


def decode_line(line: bytes | str) -> InboundMessage:
    if isinstance(line, bytes):
        line = line.decode("utf-8")
    line = line.strip()
    if not line:
        raise ProtocolError("empty protocol line")

    try:
        payload = json.loads(line)
    except json.JSONDecodeError as err:
        raise ProtocolError(f"invalid JSON: {err}") from err
    if not isinstance(payload, dict):
        raise ProtocolError("protocol message must be a JSON object")

    msg_type = payload.get("type")
    if msg_type == "cmd":
        return _decode_command(payload)
    if msg_type == "health":
        return _decode_health(payload)
    raise ProtocolError(f"unsupported message type: {msg_type!r}")


def _decode_command(payload: dict[str, Any]) -> ZigbeeCommand:
    endpoint = _required_int(payload, "endpoint")
    command = str(payload.get("command", "")).strip().lower()

    legacy_type = str(payload.get("command") or payload.get("cmd") or payload.get("type", "")).lower()
    if command in ("", "onoff") and "on" in payload:
        command = "on" if bool(payload["on"]) else "off"
    elif command == "" and legacy_type in {"level", "move_to_level"}:
        command = "level"

    if command == "move_to_level":
        command = "level"

    allowed = {"on", "off", "toggle", "level", "move", "step", "stop"}
    if command not in allowed:
        raise ProtocolError(f"unsupported Zigbee command: {command!r}")

    level = payload.get("level")
    if level is None and "value" in payload and command == "level":
        level = payload["value"]

    return ZigbeeCommand(
        endpoint=endpoint,
        command=command,  # type: ignore[arg-type]
        level=None if level is None else int(level),
        transition_ms=int(payload.get("transition_ms", 0)),
        seq=None if payload.get("seq") is None else int(payload["seq"]),
        identity=None if payload.get("identity") is None else int(payload["identity"]),
        ieee=None if payload.get("ieee") is None else str(payload["ieee"]),
        nwk=None if payload.get("nwk") is None else str(payload["nwk"]),
    )


def _decode_health(payload: dict[str, Any]) -> HealthStatus:
    return HealthStatus(
        joined=bool(payload.get("joined", False)),
        endpoints=int(payload.get("endpoints", 0)),
        ieee=None if payload.get("ieee") is None else str(payload["ieee"]),
        nwk=None if payload.get("nwk") is None else str(payload["nwk"]),
        seq=None if payload.get("seq") is None else int(payload["seq"]),
    )


def decode_report_line(line: bytes | str) -> ZigbeeReport:
    """Decode an outbound report line.

    This is mainly for simulator tests; firmware should normally only need the
    JSON shape documented here.
    """
    if isinstance(line, bytes):
        line = line.decode("utf-8")
    payload = json.loads(line)
    if payload.get("type") != "report":
        raise ProtocolError("expected report message")
    state = LightState(
        on=bool(payload["on"]),
        level=int(payload["level"]),
        source=str(payload.get("source", "test")),
        transition_ms=int(payload.get("transition_ms", 0)),
        seq=None if payload.get("seq") is None else int(payload["seq"]),
    )
    return ZigbeeReport(endpoint=int(payload["endpoint"]), state=state)


def _required_int(payload: dict[str, Any], key: str) -> int:
    try:
        return int(payload[key])
    except KeyError as err:
        raise ProtocolError(f"missing required key: {key}") from err
    except (TypeError, ValueError) as err:
        raise ProtocolError(f"{key} must be an integer") from err
