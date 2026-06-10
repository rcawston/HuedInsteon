# Three-Endpoint Variant

Historical endpoint-only prototype.

Hue Bridge Pro can expose three dimmable-light endpoints under one IEEE address,
but the Hue app groups them under one device. That prevents assigning the banks
to separate rooms, so this is not the final architecture.

The current one-dongle design uses separate Zigbee identities:

- parent identity = logical light 1
- virtual child 1 = logical light 2
- virtual child 2 = logical light 3

The endpoint variant remains useful as reference for per-endpoint ZCL attribute
state and reporting.
