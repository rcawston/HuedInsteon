# SPDX-License-Identifier: Apache-2.0
"""Command-line entry points."""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
from pathlib import Path

from .bridge import HuedInsteonBridge
from .config import load_config
from .fake_adapters import FakeInsteonAdapter, FakeZigbeeAdapter
from .models import ZigbeeCommand


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    logging.basicConfig(level=getattr(logging, args.log_level))
    return args.func(args)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="huedinsteon")
    parser.add_argument("--log-level", default="INFO", choices=["DEBUG", "INFO", "WARNING", "ERROR"])
    subparsers = parser.add_subparsers(required=True)

    validate = subparsers.add_parser("validate-config", help="Load and validate a TOML config file.")
    validate.add_argument("config", type=Path)
    validate.set_defaults(func=_validate_config)

    simulate = subparsers.add_parser("simulate-command", help="Run one Hue/Zigbee command through fake adapters.")
    simulate.add_argument("config", type=Path)
    simulate.add_argument("--endpoint", type=int, required=True)
    simulate.add_argument("--command", choices=["on", "off", "toggle", "level"], required=True)
    simulate.add_argument("--level", type=int)
    simulate.add_argument("--transition-ms", type=int, default=0)
    simulate.set_defaults(func=_simulate_command)

    run = subparsers.add_parser("run", help="Run the hardware bridge daemon.")
    run.add_argument("config", type=Path)
    run.set_defaults(func=_run_bridge)

    return parser


def _validate_config(args: argparse.Namespace) -> int:
    config = load_config(args.config)
    print(f"valid config: {len(config.banks)} banks")
    for bank in config.banks:
        print(f"- endpoint {bank.endpoint}: {bank.id} ({bank.insteon_address})")
    return 0


def _simulate_command(args: argparse.Namespace) -> int:
    if args.command == "level" and args.level is None:
        raise SystemExit("--level is required when --command level")
    return asyncio.run(_simulate_command_async(args))


async def _simulate_command_async(args: argparse.Namespace) -> int:
    config = load_config(args.config)
    insteon = FakeInsteonAdapter()
    zigbee = FakeZigbeeAdapter()
    bridge = HuedInsteonBridge(config, insteon=insteon, zigbee=zigbee)
    command = ZigbeeCommand(
        endpoint=args.endpoint,
        command=args.command,
        level=args.level,
        transition_ms=args.transition_ms,
    )
    state = await bridge.handle_zigbee_command(command)
    print(
        json.dumps(
            {
                "state": {
                    "on": state.on,
                    "level": state.level,
                    "source": state.source,
                    "transition_ms": state.transition_ms,
                },
                "insteon_commands": [
                    {"bank_id": bank_id, "on": item.on, "level": item.level}
                    for bank_id, item in insteon.commands
                ],
                "zigbee_reports": [
                    {"endpoint": report.endpoint, "on": report.state.on, "level": report.state.level}
                    for report in zigbee.reports
                ],
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


def _run_bridge(args: argparse.Namespace) -> int:
    from .insteon_pyinsteon import PyInsteonAdapter
    from .zigbee_serial import SerialZigbeeAdapter

    config = load_config(args.config)
    bridge = HuedInsteonBridge(
        config,
        insteon=PyInsteonAdapter(config.insteon),
        zigbee=SerialZigbeeAdapter(config.zigbee),
    )
    asyncio.run(bridge.run())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
