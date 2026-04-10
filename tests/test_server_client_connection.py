from __future__ import annotations

import asyncio
import contextlib
import socket
import sys
import unittest
from pathlib import Path
from unittest.mock import AsyncMock

from websockets.exceptions import ConnectionClosedError
from websockets.frames import Close

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from tuno.client.api import ClientAPI
from tuno.server.local import handler, run_server
from tuno.server.session import GameSession


def get_free_port() -> int:
    """Reserve an ephemeral localhost port for an integration test server."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


class ServerClientConnectionTests(unittest.IsolatedAsyncioTestCase):
    """Cover the websocket handshake between the local server and client API."""

    async def next_event_of_type(self, events, expected_type: str, *, timeout: float = 2.0) -> dict:
        """Read from the event stream until the expected message type arrives."""
        deadline = asyncio.get_running_loop().time() + timeout
        while True:
            remaining = deadline - asyncio.get_running_loop().time()
            if remaining <= 0:
                self.fail(f"Timed out waiting for event type {expected_type!r}")
            event = await asyncio.wait_for(events.__anext__(), timeout=remaining)
            if event["type"] == expected_type:
                return event

    async def asyncSetUp(self) -> None:
        """Start a fresh local websocket server for each integration test."""
        try:
            self.port = get_free_port()
        except PermissionError as exc:  # pragma: no cover - sandbox-specific
            self.skipTest(f"local socket binding unavailable in this environment: {exc}")
        self.session = GameSession()
        self.server_task = asyncio.create_task(
            run_server("127.0.0.1", self.port, session=self.session)
        )
        await asyncio.sleep(0.1)

    async def asyncTearDown(self) -> None:
        """Stop the local websocket server after each integration test."""
        self.server_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await self.server_task

    async def test_client_can_connect_join_and_receive_state(self) -> None:
        """Connect, join, and receive the initial authoritative state payload."""
        api = ClientAPI(f"ws://127.0.0.1:{self.port}")
        await api.open()
        try:
            events = api.events()
            info = await self.next_event_of_type(events, "info")
            self.assertEqual(info["type"], "info")

            await api.send("join", name="alice")
            welcome = await self.next_event_of_type(events, "welcome")
            self.assertEqual(welcome["type"], "welcome")
            self.assertTrue(welcome["player_id"])

            state = await self.next_event_of_type(events, "state")
            self.assertEqual(state["type"], "state")
            self.assertEqual(state["state"]["players"][0]["name"], "alice")
            self.assertEqual(state["state"]["your_player_id"], welcome["player_id"])
        finally:
            await api.close()

    async def test_handler_swallows_abrupt_disconnect_and_detaches_client(self) -> None:
        """Treat websocket disconnects as normal cleanup instead of handler failures."""

        class BrokenWebSocket:
            def __aiter__(self):
                return self

            async def __anext__(self):
                raise ConnectionClosedError(Close(1006, "abnormal"), None)

        session = AsyncMock()
        session.attach.return_value = True
        websocket = BrokenWebSocket()

        await handler(websocket, session)

        session.attach.assert_awaited_once_with(websocket)
        session.detach.assert_awaited_once_with(websocket)
