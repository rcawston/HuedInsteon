#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Start TI Z-Stack sample-light commissioning through the CUI UART menu."""

from __future__ import annotations

import argparse
import re
import time

import serial


CUI_ESC = b"\x1b\0\0\0\0"
CUI_RIGHT = bytes([0xFC])
CUI_EXECUTE = b"\r"


def clean_cui(text: str) -> str:
    text = re.sub(r"\x1b\[[0-9;?]*[A-Za-z]", "", text)
    for token in ["\x02", "\x03", "\x1b7", "\x1b8"]:
        text = text.replace(token, "")
    return text


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("port", help="Serial port, for example /dev/cu.usbserial-1130")
    parser.add_argument("--baud", type=int, default=115200)
    parser.add_argument("--watch", type=float, default=20.0, help="Seconds to watch CUI output")
    parser.add_argument(
        "--reset",
        action="store_true",
        help="Toggle Sonoff USB serial lines to reset into the application before commissioning.",
    )
    args = parser.parse_args()

    if args.reset:
        with serial.Serial(args.port, args.baud, timeout=0.2) as uart:
            for dtr, rts in [(False, False), (True, False), (False, False), (False, True), (False, False)]:
                uart.dtr = dtr
                uart.rts = rts
                time.sleep(0.15)
        time.sleep(2.0)

    with serial.Serial(args.port, args.baud, timeout=0.2) as uart:
        uart.reset_input_buffer()

        # Escape returns to the main menu's Help item. From there, two Right
        # inputs select Commission, and Enter executes it.
        for key in [CUI_ESC, CUI_RIGHT, CUI_RIGHT, CUI_EXECUTE]:
            uart.write(key)
            time.sleep(0.35)

        deadline = time.time() + args.watch
        chunks: list[bytes] = []
        while time.time() < deadline:
            data = uart.read(4096)
            if data:
                chunks.append(data)

    output = clean_cui(b"".join(chunks).decode("utf-8", errors="replace"))
    lines = [line.strip() for line in output.splitlines() if line.strip()]
    for line in lines[-20:]:
        print(line)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
