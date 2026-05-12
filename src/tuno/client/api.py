"""Thin websocket transport wrapper used by the terminal client."""

from __future__ import annotations

import ssl
from typing import Any, AsyncIterator, Dict
from urllib.parse import urlparse

from tuno.protocol.messages import decode_server_message, encode_message

try:
    import certifi
except Exception:  # pragma: no cover - fall back to platform trust store if certifi isn't present
    certifi = None


def build_client_ssl_context() -> ssl.SSLContext:
    """Build a TLS client context pinned to the bundled certifi CA bundle.

    PyInstaller builds on macOS do not always discover the platform trust store in the same
    way as an unfrozen Python environment. Using certifi gives the packaged client a stable CA
    bundle for `wss://` connections such as Cloudflare Workers.
    """
    ssl_context = ssl.create_default_context()
    if certifi is not None:
        ssl_context.load_verify_locations(certifi.where())
    return ssl_context


class ClientAPI:
    """Own the websocket connection and protocol encoding/decoding for the client."""

    def __init__(self, url: str) -> None:
        self.url = url
        self.websocket = None

    async def open(self) -> None:
        """Open the websocket connection to the target server."""
        from websockets.asyncio.client import connect

        ssl_context = build_client_ssl_context() if urlparse(self.url).scheme == "wss" else None
        self.websocket = await connect(self.url, ssl=ssl_context)

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
