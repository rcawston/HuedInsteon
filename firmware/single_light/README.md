# Single-Light Variant

Historical first-pairing variant.

It represents one CC2652P router as one Dimmable Light endpoint and was used to
prove that Hue Bridge Pro accepts custom TI Z-Stack light firmware.

Current work uses `scripts/build_zstack_zr_light.py --variant sonoff_diag`
instead, with `--virtual-child-count` controlling how many extra virtual
identities are compiled into the diagnostic image.
