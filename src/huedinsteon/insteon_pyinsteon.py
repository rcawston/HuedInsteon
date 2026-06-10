# SPDX-License-Identifier: Apache-2.0
"""pyinsteon adapter placeholder.

The bridge core is already written against this adapter boundary, but the
actual pyinsteon calls need to be verified with the 2413U PLM and i3 Dial
traffic before we lock them in.
"""

from __future__ import annotations

from collections.abc import AsyncIterator

from .config import InsteonConfig
from .models import InsteonEvent, LightState


class PyInsteonAdapter:
    def __init__(self, config: InsteonConfig) -> None:
        self.config = config

    async def start(self) -> None:
        raise NotImplementedError(
            "PyInsteonAdapter needs hardware verification against pyinsteon 1.6.4 and the 2413U PLM"
        )

    async def stop(self) -> None:
        pass

    async def set_light(self, bank_id: str, state: LightState) -> None:
        raise NotImplementedError("Insteon command mapping is not implemented yet")

    async def events(self) -> AsyncIterator[InsteonEvent]:
        raise NotImplementedError("Insteon event subscription is not implemented yet")
        yield  # pragma: no cover

