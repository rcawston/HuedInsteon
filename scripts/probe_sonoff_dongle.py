#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Probe local macOS/Linux serial devices for a Sonoff ZBDongle-P."""

from __future__ import annotations

import glob
import platform
import subprocess
from pathlib import Path


COMMON_MATCHES = (
    "SLAB",
    "CP210",
    "usbserial",
    "usbmodem",
    "ttyUSB",
    "ttyACM",
    "wchusbserial",
)


def serial_devices() -> list[str]:
    patterns = [
        "/dev/cu.*",
        "/dev/ttyUSB*",
        "/dev/ttyACM*",
        "/dev/serial/by-id/*",
    ]
    devices: list[str] = []
    for pattern in patterns:
        devices.extend(glob.glob(pattern))
    return sorted(set(devices))


def likely_devices(devices: list[str]) -> list[str]:
    return [device for device in devices if any(match.lower() in device.lower() for match in COMMON_MATCHES)]


def print_usb_summary() -> None:
    if platform.system() != "Darwin":
        return

    try:
        result = subprocess.run(
            ["system_profiler", "SPUSBDataType"],
            check=False,
            text=True,
            capture_output=True,
            timeout=20,
        )
    except (OSError, subprocess.TimeoutExpired):
        return

    lines = result.stdout.splitlines()
    interesting = [
        line
        for line in lines
        if any(token in line.lower() for token in ("cp210", "silicon labs", "sonoff", "itead", "zigbee"))
    ]
    if interesting:
        print("\nUSB summary:")
        for line in interesting:
            print(line.rstrip())


def main() -> int:
    devices = serial_devices()
    likely = likely_devices(devices)

    print("Serial devices:")
    for device in devices:
        marker = "*" if device in likely else " "
        print(f"{marker} {device}")

    if likely:
        print("\nLikely dongle device path:")
        for device in likely:
            print(f"  {device}")
    else:
        print("\nNo likely CP210x/Zigbee serial device found.")
        print("Plug the dongle in, wait a few seconds, then run this script again.")

    print_usb_summary()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

