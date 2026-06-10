# HuedInsteon

HuedInsteon is a standalone bridge for making Insteon i3 Dial lighting banks
appear as native dimmable lights on a Philips Hue Bridge Pro, without the
Insteon cloud, an Insteon hub, or Home Assistant.

The target hardware is:

- Raspberry Pi Zero 2 W
- Insteon 2413U PowerLinc Modem for local Insteon RF/powerline control
- Sonoff ZBDongle-P, or another TI CC2652P + CP2102N USB Zigbee dongle
- Custom CC2652P firmware that joins the Hue Zigbee network as lighting devices

## Current Status

This is an active hardware/firmware prototype, not production software yet.

What is already proven:

- The Python bridge scaffold, config loader, fake adapters, serial protocol
  model, and host-side tests are in place.
- A Sonoff ZBDongle-P can be built and flashed from TI Z-Stack `zr_light`.
- A parent CC2652P light can join Hue Bridge Pro as a dimmable Zigbee light.
- Hue Bridge Pro can expose multiple endpoints on one Zigbee node, but the Hue
  app groups those endpoints under one device. That does not satisfy the room
  assignment requirement.
- Lower-level MAC association from virtual child IEEE identities works. Hue
  created separate connected light resources for a parent light plus virtual
  child lights from one physical dongle.
- Firmware builds now support `--virtual-child-count N` for `N` from `0` to
  `15`. `0` means parent-only. For the intended three total Hue lights, use
  `--virtual-child-count 2` so the parent is light 1 and the two virtual
  children are lights 2 and 3.

What is not done yet:

- Production multi-identity firmware. The diagnostic firmware proves admission,
  but production firmware still needs persistent per-light short addresses,
  trust-center state, frame counters, ZDO descriptor routing, ZCL state, and
  command demultiplexing.
- Serial command routing from each Hue-visible Zigbee identity back to the Pi.
- Real Insteon PLM integration through `pyinsteon`, including event handling,
  reconciliation, loop prevention, and startup state sync.
- Runtime configuration for how many compiled Zigbee identities are enabled.
- Installer/deployment polish for the Raspberry Pi service.

See `plan.md` for the current roadmap.

## Setup

```bash
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -e ".[dev]"
```

Hardware dependencies, when needed:

```bash
python -m pip install -e ".[hardware]"
```

## Test

```bash
pytest
```

For the C firmware helper tests:

```bash
pytest tests/test_firmware_c.py
```

## Validate Config

```bash
huedinsteon validate-config config.example.toml
```

## Simulate A Hue Command

This checks the Python mapping logic without PLM or Zigbee hardware:

```bash
huedinsteon simulate-command config.example.toml --endpoint 1 --command level --level 128
```

## Firmware Build

Build a diagnostic Sonoff image with the parent light plus two virtual children
for three total Hue-visible lights:

```bash
python3 scripts/build_zstack_zr_light.py \
  --variant sonoff_diag \
  --virtual-eui 00124B003A127096 \
  --virtual-child-count 2
```

Build parent-only:

```bash
python3 scripts/build_zstack_zr_light.py \
  --variant sonoff_diag \
  --virtual-eui 00124B003A127095 \
  --virtual-child-count 0
```

Build with a larger diagnostic virtual-child capacity:

```bash
python3 scripts/build_zstack_zr_light.py \
  --variant sonoff_diag \
  --virtual-eui 00124B003A127094 \
  --virtual-child-count 5 \
  --build-dir .vendor/build/zr_light_sonoff_diag_5
```

Use a fresh `--virtual-eui` when testing with Hue if the bridge appears to have
cached old trust-center or device state for a prior identity.

## Flash Sonoff ZBDongle-P

```bash
.venv/bin/python .vendor/cc2538-bsl/cc2538_bsl/cc2538_bsl.py \
  --bootloader-sonoff-usb \
  -p /dev/cu.usbserial-1130 \
  -b 500000 \
  -e -w -v \
  -f .vendor/build/zr_light_sonoff_diag/zr_light_sonoff_diag.bin
```

Adjust the serial device path if macOS assigns a different `/dev/cu.usbserial-*`
name.

## Hue / Zigbee Diagnostics

Start Hue search:

```bash
python3 scripts/hue_bridge.py v2-search --action-type search_allow_default_link_key
```

Join the parent light:

```bash
.venv/bin/python scripts/zigbee_diag.py /dev/cu.usbserial-1130 commission --watch 120
```

Associate virtual children:

```bash
.venv/bin/python scripts/zigbee_diag.py /dev/cu.usbserial-1130 vmacassoc1 --watch 45
.venv/bin/python scripts/zigbee_diag.py /dev/cu.usbserial-1130 vrestore --watch 5
.venv/bin/python scripts/zigbee_diag.py /dev/cu.usbserial-1130 vmacassoc2 --watch 45
.venv/bin/python scripts/zigbee_diag.py /dev/cu.usbserial-1130 vrestore --watch 5
```

For a build with more configured children, indexed commands such as
`vmacassoc4` work, and plural commands such as `vmacassocs` iterate over the
compiled virtual-child count.

Query Hue lights:

```bash
python3 scripts/hue_bridge.py lights
```

Delete known test lights when cleaning up a Hue Bridge:

```bash
python3 scripts/hue_bridge.py delete --yes 69 70 71 72
```

## Repository Map

- `src/huedinsteon/`: Python bridge core and adapters
- `firmware/common/`: portable C helpers and serial protocol pieces
- `firmware/ti_zstack/`: TI Z-Stack overlay notes and board files
- `scripts/build_zstack_zr_light.py`: TI Z-Stack diagnostic build patcher
- `scripts/zigbee_diag.py`: serial diagnostic command helper
- `scripts/hue_bridge.py`: Hue Bridge API helper
- `docs/`: bring-up and firmware notes
- `plan.md`: current roadmap and architecture summary

## License

Project-owned source code and documentation are licensed under Apache-2.0. See
`LICENSE` and `NOTICE`.

The repository does not include or relicense the Texas Instruments SimpleLink
SDK, Z-Stack source tree, TI compiler, SysConfig, or Code Composer Studio
artifacts. Those must be obtained separately from TI and used under TI's terms.

## Architecture Direction

The final one-dongle design is parent-light plus virtual Zigbee children:

- The physical CC2652P joins as a real Hue-visible dimmable light.
- Additional banks join through MAC-level virtual child identities with unique
  IEEE addresses.
- Each light identity must maintain its own Zigbee network/security/ZCL state.
- The Pi bridge maps Hue-originated on/off and level commands to the matching
  Insteon bank, and maps physical i3 Dial changes back to the matching Zigbee
  light state.

This keeps one USB Zigbee dongle while allowing the Hue app to treat the banks
as independent lights that can be assigned to different rooms.
