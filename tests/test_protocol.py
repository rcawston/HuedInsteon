# SPDX-License-Identifier: Apache-2.0
import json

import pytest

from huedinsteon.models import LightState, ZigbeeCommand, ZigbeeReport
from huedinsteon.protocol import ProtocolError, decode_line, decode_report_line, encode_message


def test_decode_level_command():
    message = decode_line(
        b'{"dir":"zb->pi","type":"cmd","endpoint":2,"command":"level","level":128,"transition_ms":400,"seq":7}\n'
    )

    assert message == ZigbeeCommand(endpoint=2, command="level", level=128, transition_ms=400, seq=7)


def test_decode_identity_metadata():
    message = decode_line(
        b'{"dir":"zb->pi","type":"cmd","endpoint":3,"identity":3,'
        b'"ieee":"00124b003a126fa2","nwk":"0xaed4","command":"off","seq":11}\n'
    )

    assert message == ZigbeeCommand(
        endpoint=3,
        identity=3,
        ieee="00124b003a126fa2",
        nwk="0xaed4",
        command="off",
        seq=11,
    )


def test_decode_legacy_onoff_command():
    message = decode_line(b'{"type":"cmd","endpoint":1,"command":"onoff","on":true,"seq":3}\n')

    assert message == ZigbeeCommand(endpoint=1, command="on", seq=3)


def test_encode_report():
    raw = encode_message(ZigbeeReport(endpoint=1, state=LightState(on=True, level=180, source="insteon", seq=9)))
    payload = json.loads(raw)

    assert payload["type"] == "report"
    assert payload["endpoint"] == 1
    assert payload["on"] is True
    assert payload["level"] == 180
    assert decode_report_line(raw).state.level == 180


def test_rejects_bad_command():
    with pytest.raises(ProtocolError):
        decode_line(b'{"type":"cmd","endpoint":1,"command":"bogus"}')
