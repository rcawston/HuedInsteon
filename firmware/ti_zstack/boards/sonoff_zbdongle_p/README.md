# Sonoff ZBDongle-P Board Notes

TI does not ship a `SONOFF_ZBDONGLE_P` board package in the SimpleLink SDK.
These notes capture the local board assumptions used by the prototype.

| Signal | CC2652P DIO | Notes |
| --- | ---: | --- |
| UART TXD to CP2102N | DIO13 | Host receives |
| UART RXD from CP2102N | DIO12 | Host transmits |
| UART CTS | DIO19 | Only with hardware flow control enabled |
| UART RTS | DIO18 | Only with hardware flow control enabled |
| Boot / BSL trigger | DIO15 | Manual button and Auto-BSL |
| 20 dBm PA control | DIO29 | High-power PA enable |
| 2.4 GHz RF switch | DIO28 | Present in CC1352P_2 base |
| Green LED | DIO7 | May be unpopulated |

The current build helper still uses the `CC1352P_2_LAUNCHXL` base project and
patches/remaps what is needed. The files in this directory are retained for a
future cleaner board package.
