# TI Z-Stack Integration

Use TI's `zr_light` example as the base application. The project build helper
patches a build-local copy of the TI sources and emits flashable artifacts under
`.vendor/build/`.

External dependencies:

- TI SimpleLink Low Power F2 SDK `8.32.00.07`
- TI SysConfig
- TI Arm Clang compiler
- `cc2538-bsl` for flashing the Sonoff ZBDongle-P

These are not redistributed by this repository.

## Current Build

Three total Hue lights:

```bash
python3 scripts/build_zstack_zr_light.py \
  --variant sonoff_diag \
  --virtual-eui 00124B003A127096 \
  --virtual-child-count 2
```

The diagnostic build:

- changes the sample endpoint to `1`.
- joins Hue as the parent light.
- performs MAC association for virtual child IEEE addresses.
- serves ZDO descriptors for virtual children.
- emits Hue commands as JSON over USB serial.

## Sonoff Board Notes

The Sonoff ZBDongle-P is not an official TI board package. The current build
uses the `CC1352P_2_LAUNCHXL` project because it matches the CC2652P + PA class
closely enough for this prototype. Local board notes live in
`boards/sonoff_zbdongle_p/`.

Important pins:

- UART TX/RX: DIO13/DIO12
- Boot / BSL: DIO15
- PA control: DIO29
- Optional RF switch from LaunchPad base: DIO28

## License Boundary

Files in this repository are Apache-2.0 unless noted otherwise. TI SDK files,
examples, tools, and generated output are subject to TI license terms.
