# SPDX-License-Identifier: Apache-2.0
from huedinsteon.config import ConfigError, load_config, parse_config


def test_load_example_config():
    config = load_config("config.example.toml")

    assert len(config.banks) == 3
    assert config.banks[0].endpoint == 1
    assert config.bank_by_endpoint[2].id == "bank_b"


def test_rejects_duplicate_endpoint():
    data = {
        "zigbee": {"port": "/dev/ttyUSB0"},
        "insteon": {"port": "/dev/ttyUSB1"},
        "banks": [
            {"id": "a", "name": "A", "endpoint": 1, "insteon_address": "11.22.33"},
            {"id": "b", "name": "B", "endpoint": 1, "insteon_address": "22.33.44"},
        ],
    }

    try:
        parse_config(data)
    except ConfigError as err:
        assert "duplicate endpoint" in str(err)
    else:
        raise AssertionError("expected ConfigError")

