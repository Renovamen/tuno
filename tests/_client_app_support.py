from __future__ import annotations

import asyncio
import contextlib
import socket
import sys
import unittest
from io import StringIO
from pathlib import Path

from rich.console import Console, RenderableType

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

try:
    from textual.pilot import Pilot  # type: ignore
    from textual.widgets import Static

    from tuno.client.app import TunoApp

    TEXTUAL_AVAILABLE = True
except Exception:  # pragma: no cover
    Pilot = object  # type: ignore
    Static = object  # type: ignore
    TunoApp = object  # type: ignore
    TEXTUAL_AVAILABLE = False

from tuno.client.api import ClientAPI
from tuno.core.cards import Card
from tuno.server.local import run_server
from tuno.server.session import GameSession

__all__ = [
    "Card",
    "ClientAPI",
    "ClientAppHarness",
    "Pilot",
    "Static",
    "TEXTUAL_AVAILABLE",
    "TunoApp",
    "get_free_port",
    "render_to_text",
]


def render_to_text(renderable: RenderableType) -> str:
    """Render any Rich renderable to a plain string for assertion purposes."""
    buf = StringIO()
    console = Console(file=buf, width=80, highlight=False, markup=False)
    console.print(renderable)
    return buf.getvalue()


def get_free_port() -> int:
    """Reserve an ephemeral localhost port for an isolated UI test server."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


@unittest.skipUnless(TEXTUAL_AVAILABLE, "textual is required for app interaction tests")
class ClientAppHarness(unittest.IsolatedAsyncioTestCase):
    """Shared integration harness for Textual client interaction tests."""

    async def wait_until(
        self, predicate, pilot: Pilot, *, timeout: float = 2.0, message: str = "condition"
    ) -> None:
        """Poll the Textual pilot until a condition becomes true or times out."""
        deadline = asyncio.get_running_loop().time() + timeout
        while True:
            if predicate():
                return
            remaining = deadline - asyncio.get_running_loop().time()
            if remaining <= 0:
                self.fail(f"Timed out waiting for {message}")
            await pilot.pause(0.05)

    async def asyncSetUp(self) -> None:
        """Start a fresh local websocket server for each interaction test."""
        try:
            self.port = get_free_port()
        except PermissionError as exc:  # pragma: no cover
            self.skipTest(f"local socket binding unavailable in this environment: {exc}")
        self.url = f"ws://127.0.0.1:{self.port}"
        self.session = GameSession()
        self.server_task = asyncio.create_task(
            run_server("127.0.0.1", self.port, session=self.session)
        )
        await asyncio.sleep(0.1)

    async def asyncTearDown(self) -> None:
        """Stop the local websocket server after each interaction test."""
        self.server_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await self.server_task

    async def connect_guest(self, guest: ClientAPI, pilot: Pilot) -> None:
        """Join a second player and wait for the shared session to reflect it."""
        await guest.open()
        guest_events = guest.events()
        await asyncio.wait_for(guest_events.__anext__(), timeout=2)
        await guest.send("join", name="bob")
        await asyncio.wait_for(guest_events.__anext__(), timeout=2)
        await self.wait_until(
            lambda: len(self.session.state.players) == 2, pilot, message="guest join"
        )

    async def close_clients(self, app: TunoApp, guest: ClientAPI) -> None:
        """Shut down the test clients and listener task cleanly."""
        if app.api is not None:
            await app.api.close()
        if app.listener_task is not None:
            app.listener_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await app.listener_task
        await guest.close()
