# Development Notes

## Scope

The repository has three active parts:

- Python bridge core and fake adapters for host-side testing.
- Firmware helper code plus a Z-Stack build patcher for the Sonoff ZBDongle-P.
- Hue/Zigbee diagnostic scripts used during commissioning experiments.

The real Insteon PLM adapter is intentionally deferred. For now, development
focus is the Zigbee identity model and serial command stream.

## Setup

```bash
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -e ".[dev]"
pytest
```

Hardware dependencies are optional:

```bash
python -m pip install -e ".[hardware]"
```

## Useful Commands

Validate config:

```bash
huedinsteon validate-config config.example.toml
```

Exercise the Python mapping logic without hardware:

```bash
huedinsteon simulate-command config.example.toml --endpoint 1 --command level --level 128
```

Build diagnostic firmware for three total Hue lights:

```bash
python3 scripts/build_zstack_zr_light.py \
  --variant sonoff_diag \
  --virtual-eui 00124B003A127096 \
  --virtual-child-count 2
```

Run serial diagnostics:

```bash
.venv/bin/python scripts/zigbee_diag.py /dev/cu.usbserial-1130 state --watch 10
```

## Current Firmware Direction

The final user-facing model is:

- Parent Zigbee identity = light 1.
- Virtual child identity 1 = light 2.
- Virtual child identity 2 = light 3.

The endpoint-only prototype worked technically but failed the Hue room model:
Hue grouped multiple endpoints under one device. The current diagnostic
firmware therefore works at the MAC association level so Hue sees separate IEEE
identities.

## Publish Boundaries

Project code is Apache-2.0. TI SimpleLink SDK, Z-Stack, SysConfig, TI compiler,
and generated build products are not part of this repository and remain under
Texas Instruments license terms.
