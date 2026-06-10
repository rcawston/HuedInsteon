# Firmware

This directory contains project-owned firmware helpers and notes. It is not a
TI SDK checkout.

Current approach:

- Build from TI Z-Stack `zr_light` for CC1352P/CC2652P-class hardware.
- Use the Sonoff ZBDongle-P as one physical CC2652P radio.
- Expose one parent light plus configurable virtual child identities.
- Keep TI SDK, compiler, SysConfig, and generated artifacts outside the repo.

Directory map:

- `common/`: portable serial protocol and bridge helper code.
- `single_light/`: historical one-light variant config.
- `three_endpoint/`: historical endpoint-only variant config.
- `ti_zstack/`: TI integration notes and Sonoff board overlay.
- `tests/`: host-side C tests for portable firmware helpers.

The endpoint-only variants remain useful reference code, but the Hue-compatible
room model requires separate Zigbee IEEE identities.
