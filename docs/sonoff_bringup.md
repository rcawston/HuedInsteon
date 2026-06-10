# Sonoff ZBDongle-P Bring-Up

Use this for the Sonoff ZBDongle-P, not the ZBDongle-E.

Expected hardware:

- TI CC2652P radio
- Silicon Labs CP2102N USB serial bridge
- Auto-BSL support through the USB UART control lines

Observed device path in this workspace:

```text
/dev/cu.usbserial-1130
```

## Confirm The Dongle

```bash
python3 scripts/probe_sonoff_dongle.py
python3 scripts/query_znp_version.py /dev/cu.usbserial-1130
```

Record the stock firmware version and keep a known-good coordinator image for
recovery before flashing custom firmware.

## Bootloader

The Sonoff ZBDongle-P uses DIO15 for bootloader entry. The current flash path
uses `cc2538-bsl` with Sonoff Auto-BSL:

```bash
.venv/bin/python .vendor/cc2538-bsl/cc2538_bsl/cc2538_bsl.py \
  --bootloader-sonoff-usb \
  -p /dev/cu.usbserial-1130 \
  -b 500000 \
  -e -w -v \
  -f .vendor/build/zr_light_sonoff_diag/zr_light_sonoff_diag.bin
```

If Auto-BSL fails, use the physical boot button while plugging in.

## Build Target

For the current three-light experiment:

```bash
python3 scripts/build_zstack_zr_light.py \
  --variant sonoff_diag \
  --virtual-eui 00124B003A127096 \
  --virtual-child-count 2
```

The build helper uses TI's `CC1352P_2_LAUNCHXL` Z-Stack `zr_light` project as
the base and patches a build-local copy. The TI SDK stays in `.vendor/`.

## Known Pin Assumptions

| Signal | CC2652P DIO | Notes |
| --- | ---: | --- |
| UART TXD to CP2102N | DIO13 | Host receives |
| UART RXD from CP2102N | DIO12 | Host transmits |
| Boot / BSL trigger | DIO15 | Manual button and Auto-BSL |
| PA control | DIO29 | High-power PA |
| Optional RF switch | DIO28 | Present in CC1352P_2 base |

Keep hardware flow control disabled unless the dongle DIP switches and host
serial configuration both enable RTS/CTS.

## Hue Test

1. Flash the diagnostic image.
2. Start Hue Bridge Pro light search.
3. Run `commission` to join the parent light.
4. Run `vmacassoc1`, `vrestore`, `vmacassoc2`, `vrestore`.
5. Confirm Hue shows three separate lights.
6. Change each light in Hue and verify JSON command lines on USB serial.

Useful serial command:

```bash
.venv/bin/python scripts/zigbee_diag.py /dev/cu.usbserial-1130 listen --watch 120
```
