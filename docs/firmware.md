# Firmware Notes

The CC2652P dongle must join the Hue Bridge Pro Zigbee network as a light
device. It must not run coordinator firmware for final operation.

## Current Result

The useful result is not the old three-endpoint prototype. Hue Bridge Pro can
control multiple endpoints, but the Hue app groups them under one device, which
prevents independent room assignment.

The current one-dongle direction is parent plus virtual children:

- Parent identity exposes one Dimmable Light.
- Each virtual child has its own IEEE address and performs MAC association.
- Hue Bridge Pro creates separate light resources for those identities.
- The firmware maps parent/child identity back to logical endpoint numbers for
  the Pi: parent = `1`, first child = `2`, second child = `3`.

The diagnostic firmware has proven admission and discovery. Production firmware
still needs persistent per-identity network/security/ZCL state.

## Build

The build helper patches TI's `zr_light` example locally. It does not modify or
vendor TI SDK source.

Three total Hue lights:

```bash
python3 scripts/build_zstack_zr_light.py \
  --variant sonoff_diag \
  --virtual-eui 00124B003A127096 \
  --virtual-child-count 2
```

Parent-only:

```bash
python3 scripts/build_zstack_zr_light.py \
  --variant sonoff_diag \
  --virtual-eui 00124B003A127095 \
  --virtual-child-count 0 \
  --build-dir .vendor/build/zr_light_sonoff_diag_0
```

Use a fresh `--virtual-eui` when Hue appears to cache old trust-center state.

## Flash

```bash
.venv/bin/python .vendor/cc2538-bsl/cc2538_bsl/cc2538_bsl.py \
  --bootloader-sonoff-usb \
  -p /dev/cu.usbserial-1130 \
  -b 500000 \
  -e -w -v \
  -f .vendor/build/zr_light_sonoff_diag/zr_light_sonoff_diag.bin
```

## Commissioning Flow

Start Hue search:

```bash
python3 scripts/hue_bridge.py v2-search --action-type search_allow_default_link_key
```

Join the parent:

```bash
.venv/bin/python scripts/zigbee_diag.py /dev/cu.usbserial-1130 commission --watch 120
```

Associate two virtual children:

```bash
.venv/bin/python scripts/zigbee_diag.py /dev/cu.usbserial-1130 vmacassoc1 --watch 45
.venv/bin/python scripts/zigbee_diag.py /dev/cu.usbserial-1130 vrestore --watch 5
.venv/bin/python scripts/zigbee_diag.py /dev/cu.usbserial-1130 vmacassoc2 --watch 45
.venv/bin/python scripts/zigbee_diag.py /dev/cu.usbserial-1130 vrestore --watch 5
```

Then use the Hue app to change each light and listen for JSON command lines on
the serial port.

## Serial Protocol

Firmware to Pi:

```json
{"dir":"zb->pi","type":"cmd","endpoint":1,"identity":1,"ieee":"00124b003a127096","nwk":"0x1234","command":"on","seq":1}
{"dir":"zb->pi","type":"cmd","endpoint":2,"identity":2,"ieee":"00124b003a126fa1","nwk":"0xaed3","command":"level","level":128,"transition_ms":400,"seq":2}
```

Pi to firmware:

```json
{"dir":"pi->zb","type":"report","endpoint":1,"on":true,"level":180,"source":"insteon","transition_ms":0,"seq":991}
{"dir":"pi->zb","type":"health?","seq":992}
```

## Remaining Firmware Work

- Persist per-identity short address, trust-center state, frame counters, and
  ZCL attributes.
- Route incoming APS/ZCL commands for each virtual identity without relying on
  diagnostic global-state swaps.
- Apply Pi-originated reports to the correct Hue-visible identity.
- Add reset/rejoin behavior that does not require manually changing IEEE
  addresses after each experiment.

## License Boundary

Project-owned firmware helpers and scripts are Apache-2.0. TI SDK/Z-Stack
sources, tools, examples, and generated artifacts are external dependencies
under TI's terms.
