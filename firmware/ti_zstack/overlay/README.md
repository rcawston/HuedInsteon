# TI Overlay

This directory contains project-owned adapter code for the older portable
firmware path. It is retained as reference while the active prototype is driven
by `scripts/build_zstack_zr_light.py`.

Do not copy TI SDK source into this repository. Keep SDK files in `.vendor/` or
a normal TI installation path.

Useful reference points:

- On/Off and Level Control callbacks should emit JSON commands to the Pi.
- Pi reports should update local ZCL On/Off and Current Level attributes.
- Mutable light state must be per logical light, not shared globally.
- The Hue room model requires separate IEEE identities, not only multiple
  endpoints under one IEEE address.
