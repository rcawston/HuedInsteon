#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Query a TI ZNP coordinator for SYS_VERSION and SYS_PING over serial."""

from __future__ import annotations

import argparse
import os
import select
import termios
import time


def mt_fcs(payload: bytes) -> int:
    fcs = 0
    for byte in payload:
        fcs ^= byte
    return fcs


def mt_frame(cmd0: int, cmd1: int, data: bytes = b"") -> bytes:
    payload = bytes([len(data), cmd0, cmd1]) + data
    return b"\xfe" + payload + bytes([mt_fcs(payload)])


def read_mt_frames(fd: int, timeout_s: float) -> list[tuple[bool, bytes]]:
    end = time.time() + timeout_s
    buf = bytearray()
    frames: list[tuple[bool, bytes]] = []

    while time.time() < end:
        readable, _, _ = select.select([fd], [], [], max(0, end - time.time()))
        if not readable:
            break
        chunk = os.read(fd, 4096)
        if not chunk:
            continue
        buf.extend(chunk)

        while True:
            try:
                sof = buf.index(0xFE)
            except ValueError:
                buf.clear()
                break
            if sof:
                del buf[:sof]
            if len(buf) < 5:
                break

            data_len = buf[1]
            frame_len = 1 + 1 + 2 + data_len + 1
            if len(buf) < frame_len:
                break

            raw = bytes(buf[:frame_len])
            del buf[:frame_len]
            frames.append((mt_fcs(raw[1:-1]) == raw[-1], raw))

    return frames


def configure_port(fd: int) -> None:
    attrs = termios.tcgetattr(fd)
    attrs[0] = 0
    attrs[1] = 0
    attrs[2] = termios.CS8 | termios.CREAD | termios.CLOCAL
    attrs[3] = 0
    attrs[4] = termios.B115200
    attrs[5] = termios.B115200
    termios.tcsetattr(fd, termios.TCSANOW, attrs)
    termios.tcflush(fd, termios.TCIOFLUSH)


def describe_frame(raw: bytes) -> str:
    if len(raw) < 5 or raw[0] != 0xFE:
        return "unknown"

    data_len = raw[1]
    cmd0 = raw[2]
    cmd1 = raw[3]
    data = raw[4 : 4 + data_len]

    if cmd0 == 0x61 and cmd1 == 0x02:
        fields = list(data[:5])
        extra = data[5:]
        if len(fields) == 5:
            return (
                "SYS_VERSION "
                f"transport={fields[0]} product={fields[1]} "
                f"version={fields[2]}.{fields[3]}.{fields[4]} "
                f"extra={extra.hex() or '-'}"
            )
    if cmd0 == 0x61 and cmd1 == 0x01:
        caps = int.from_bytes(data, "little") if data else 0
        return f"SYS_PING capabilities=0x{caps:04x}"

    return f"cmd0=0x{cmd0:02x} cmd1=0x{cmd1:02x} data={data.hex()}"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("port", help="Serial port, for example /dev/cu.usbserial-1130")
    args = parser.parse_args()

    probes = [
        ("SYS_VERSION", mt_frame(0x21, 0x02)),
        ("SYS_PING", mt_frame(0x21, 0x01)),
    ]

    fd = os.open(args.port, os.O_RDWR | os.O_NOCTTY | os.O_NONBLOCK)
    try:
        configure_port(fd)
        for name, payload in probes:
            print(f"sending {name}: {payload.hex()}")
            os.write(fd, payload)
            time.sleep(0.1)
            frames = read_mt_frames(fd, 1.2)
            if not frames:
                print("  no response")
            for ok, raw in frames:
                print(f"  response ok={ok}: {raw.hex()}  {describe_frame(raw)}")
    finally:
        os.close(fd)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

