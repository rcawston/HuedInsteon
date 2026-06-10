# HuedInsteon Plan

## Goal

Make three Insteon i3 Dial lighting banks appear in the Hue app as independent
dimmable lights, using one Raspberry Pi and one CC2652P Zigbee dongle.

Target hardware:

- Raspberry Pi Zero 2 W
- Insteon 2413U PowerLinc Modem
- Sonoff ZBDongle-P or equivalent TI CC2652P USB dongle
- Existing Hue Bridge Pro

## Current Architecture

The one-dongle Zigbee design is parent plus virtual children:

- Parent Zigbee identity exposes light 1.
- Virtual child identity 1 exposes light 2.
- Virtual child identity 2 exposes light 3.
- Each identity must have its own IEEE address, short address, security state,
  frame counters, descriptors, and ZCL light state.

The Pi bridge maps Hue-originated Zigbee commands to Insteon banks and maps
physical Insteon changes back to Zigbee light reports.

## What Has Been Proven

- A Sonoff ZBDongle-P can run TI Z-Stack router/light firmware.
- Hue Bridge Pro accepts the custom firmware as a third-party dimmable light.
- Multiple endpoints under one IEEE address are not enough because Hue groups
  them under one device.
- MAC-level association from virtual child IEEE identities can create separate
  Hue-visible light resources from one physical dongle.
- Diagnostic firmware tracks live child short addresses, serves virtual-child
  descriptors, demultiplexes Hue commands by identity, and emits identity-aware
  serial JSON.
- Firmware persists the virtual identity table, including live short addresses,
  frame counters, on/level state, and serial sequence state, then restores the
  Z-Stack address manager and association table on boot/network restoration.
- The build helper supports `--virtual-child-count 0..15`.

For three total lights, build with `--virtual-child-count 2`.

## Active Work

1. Production firmware state:
   - validate reboot/rejoin against Hue Bridge Pro using already-added parent
     and virtual-child lights.
   - apply Pi-originated reports to the correct Hue-visible identity.
   - trim the diagnostic command set into the production serial surface once
     reverse reporting is implemented.

2. Serial bridge contract:
   - keep newline-delimited JSON.
   - route by logical `endpoint`.
   - include optional `identity`, `ieee`, and `nwk` metadata for diagnostics.

3. Insteon integration:
   - connect `pyinsteon` to the 2413U PLM.
   - map bank events to Zigbee reports.
   - prevent command loops and reconcile startup state.

## Build Snapshot

```bash
python3 scripts/build_zstack_zr_light.py \
  --variant sonoff_diag \
  --virtual-eui 00124B003A127096 \
  --virtual-child-count 2
```

The generated firmware artifact is written under:

```text
.vendor/build/zr_light_sonoff_diag/
```

## Licensing

Project-owned code and docs are Apache-2.0. TI SimpleLink SDK, Z-Stack, tools,
examples, and generated build artifacts are external dependencies under Texas
Instruments license terms.
