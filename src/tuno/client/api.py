"""Thin websocket transport wrapper used by the terminal client."""

from __future__ import annotations

from typing import Any, AsyncIterator, Dict

from tuno.protocol.messages import decode_server_message, encode_message


class ClientAPI:
    """Own the websocket connection and protocol encoding/decoding for the client."""

    def __init__(self, url: str) -> None:
        self.url = url
        self.websocket = None

    async def open(self) -> None:
        """Open the websocket connection to the target server."""
        from websockets.asyncio.client import connect

        self.websocket = await connect(self.url)

    async def close(self) -> None:
        """Close and forget the current websocket connection."""
        if self.websocket is not None:
            await self.websocket.close()
            self.websocket = None

    async def send(self, kind: str, **payload: Any) -> None:
        """Encode and send one client action message."""
        if self.websocket is None:
            raise RuntimeError("Not connected.")
        await self.websocket.send(encode_message(kind, **payload))

    async def events(self) -> AsyncIterator[Dict[str, Any]]:
        """Yield decoded server messages from the live websocket stream."""
        if self.websocket is None:
            raise RuntimeError("Not connected.")
        async for raw in self.websocket:
            yield decode_server_message(raw)
