#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Interact with the HuedInsteon diagnostic Zigbee firmware."""

from __future__ import annotations

import argparse
import re
import time

import serial


JOINED_STATE_RE = re.compile(
    r"^STATE .* dev=7 .* pan=0x(?!fffe|ffff)[0-9a-fA-F]{4} .* channel=(?!0\b)\d+ "
)


def reset_sonoff(port: str, baud: int) -> None:
    with serial.Serial(port, baud, timeout=0.2) as uart:
        for dtr, rts in [
            (False, False),
            (True, True),
            (False, False),
            (True, False),
            (False, False),
            (False, True),
            (False, False),
        ]:
            uart.dtr = dtr
            uart.rts = rts
            time.sleep(0.15)
    time.sleep(2.0)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("port", help="Serial port, for example /dev/cu.usbserial-1130")
    parser.add_argument("command", nargs="?", default="state")
    parser.add_argument("--baud", type=int, default=115200)
    parser.add_argument("--watch", type=float, default=5.0)
    parser.add_argument(
        "--repeat",
        type=float,
        default=0.0,
        help="Repeat the command at this interval, in seconds.",
    )
    parser.add_argument("--reset", action="store_true")
    args = parser.parse_args()

    if args.reset:
        reset_sonoff(args.port, args.baud)

    with serial.Serial(args.port, args.baud, timeout=0.2) as uart:
        uart.reset_input_buffer()
        next_send = 0.0
        if args.command != "listen":
            uart.write(args.command.encode("ascii") + b"\n")
            print(f"TX {args.command}", flush=True)
            if args.repeat > 0:
                next_send = time.time() + args.repeat

        deadline = time.time() + args.watch
        buffer = bytearray()
        while time.time() < deadline:
            if args.command != "listen" and args.repeat > 0 and time.time() >= next_send:
                uart.write(args.command.encode("ascii") + b"\n")
                print(f"TX {args.command}", flush=True)
                next_send = time.time() + args.repeat

            data = uart.read(512)
            if not data:
                continue
            buffer.extend(data)
            while b"\n" in buffer:
                line, _, buffer = buffer.partition(b"\n")
                decoded = line.decode("utf-8", errors="replace").rstrip("\r")
                print(decoded, flush=True)
                if args.repeat > 0 and JOINED_STATE_RE.match(decoded):
                    return 0

        if buffer:
            print(buffer.decode("utf-8", errors="replace").rstrip("\r\n"), flush=True)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
