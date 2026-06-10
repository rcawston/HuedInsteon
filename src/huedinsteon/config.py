# SPDX-License-Identifier: Apache-2.0
"""Configuration loading and validation."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import tomllib
from typing import Any


@dataclass(frozen=True)
class SerialConfig:
    port: str
    baudrate: int = 115200


@dataclass(frozen=True)
class InsteonConfig:
    port: str


@dataclass(frozen=True)
class BridgeSettings:
    optimistic_hue_updates: bool = True
    echo_suppression_ms: int = 750


@dataclass(frozen=True)
class BankConfig:
    id: str
    name: str
    endpoint: int
    insteon_address: str
    default_level: int = 254


@dataclass(frozen=True)
class AppConfig:
    zigbee: SerialConfig
    insteon: InsteonConfig
    bridge: BridgeSettings
    banks: tuple[BankConfig, ...]

    @property
    def bank_by_endpoint(self) -> dict[int, BankConfig]:
        return {bank.endpoint: bank for bank in self.banks}

    @property
    def bank_by_id(self) -> dict[str, BankConfig]:
        return {bank.id: bank for bank in self.banks}


class ConfigError(ValueError):
    pass


def load_config(path: str | Path) -> AppConfig:
    config_path = Path(path)
    with config_path.open("rb") as fp:
        data = tomllib.load(fp)
    return parse_config(data)


def parse_config(data: dict[str, Any]) -> AppConfig:
    try:
        zigbee_data = data["zigbee"]
        insteon_data = data["insteon"]
        bank_data = data["banks"]
    except KeyError as err:
        raise ConfigError(f"missing required config section: {err.args[0]}") from err

    if not isinstance(bank_data, list) or not bank_data:
        raise ConfigError("banks must contain at least one bank")

    bridge_data = data.get("bridge", {})
    config = AppConfig(
        zigbee=SerialConfig(
            port=_required_str(zigbee_data, "port", "zigbee"),
            baudrate=int(zigbee_data.get("baudrate", 115200)),
        ),
        insteon=InsteonConfig(port=_required_str(insteon_data, "port", "insteon")),
        bridge=BridgeSettings(
            optimistic_hue_updates=bool(bridge_data.get("optimistic_hue_updates", True)),
            echo_suppression_ms=int(bridge_data.get("echo_suppression_ms", 750)),
        ),
        banks=tuple(_parse_bank(item, index) for index, item in enumerate(bank_data, start=1)),
    )
    _validate_config(config)
    return config


def _parse_bank(data: dict[str, Any], index: int) -> BankConfig:
    section = f"banks[{index}]"
    return BankConfig(
        id=_required_str(data, "id", section),
        name=_required_str(data, "name", section),
        endpoint=int(data["endpoint"]),
        insteon_address=_required_str(data, "insteon_address", section),
        default_level=int(data.get("default_level", 254)),
    )


def _required_str(data: dict[str, Any], key: str, section: str) -> str:
    try:
        value = data[key]
    except KeyError as err:
        raise ConfigError(f"missing required key {section}.{key}") from err
    if not isinstance(value, str) or not value.strip():
        raise ConfigError(f"{section}.{key} must be a non-empty string")
    return value


def _validate_config(config: AppConfig) -> None:
    endpoints: set[int] = set()
    bank_ids: set[str] = set()
    addresses: set[str] = set()

    if config.zigbee.baudrate <= 0:
        raise ConfigError("zigbee.baudrate must be positive")
    if config.bridge.echo_suppression_ms < 0:
        raise ConfigError("bridge.echo_suppression_ms must be >= 0")

    for bank in config.banks:
        if bank.endpoint < 1:
            raise ConfigError(f"bank {bank.id} endpoint must be >= 1")
        if bank.endpoint in endpoints:
            raise ConfigError(f"duplicate endpoint: {bank.endpoint}")
        endpoints.add(bank.endpoint)

        if bank.id in bank_ids:
            raise ConfigError(f"duplicate bank id: {bank.id}")
        bank_ids.add(bank.id)

        normalized_address = bank.insteon_address.upper()
        if normalized_address in addresses:
            raise ConfigError(f"duplicate Insteon address: {bank.insteon_address}")
        addresses.add(normalized_address)

        if not 1 <= bank.default_level <= 254:
            raise ConfigError(f"bank {bank.id} default_level must be in the range 1..254")

