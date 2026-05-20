"""Non-widget runtime state and transport orchestration for the Textual client."""

from __future__ import annotations

import asyncio
import contextlib
import os
from typing import Any, Awaitable, Callable, Dict, Optional
from urllib.parse import urlparse

from tuno.client.api import ClientAPI
from tuno.client.config import load_server_history, remember_server
from tuno.client.state import format_server_error
from tuno.client.tui.commands import CommandMessages
from tuno.client.updates import (
    build_update_notice,
    fetch_latest_release_version,
    is_newer_version,
)
from tuno.core.snapshot import GameSnapshot
from tuno.protocol.messages import ClientMsg, ServerMsg

FeedbackCallback = Callable[[str], None]
RenderCallback = Callable[[], None]
ExitCallback = Callable[[], None]
TaskFactory = Callable[[Awaitable[Any]], asyncio.Task[Any]]
ApiFactory = Callable[[str], ClientAPI]


class ClientRuntime:
    """Own client state, websocket lifecycle, and server-message handling."""

    def __init__(
        self,
        *,
        initial_url: str = "",
        set_feedback: FeedbackCallback,
        clear_pending_server_response: Callable[[], None],
        render_state: RenderCallback,
        exit_app: ExitCallback,
        api_factory: ApiFactory = ClientAPI,
        task_factory: TaskFactory = asyncio.create_task,
    ) -> None:
        self.selected_server_url = initial_url.strip()
        self.preferred_name = ""
        self.server_history = load_server_history()

        self.player_id: Optional[str] = None
        self.selected_room_name: Optional[str] = None
        self.rooms: list[Dict[str, Any]] = []
        self.state: GameSnapshot = GameSnapshot()
        self.say_uno_next = False
        self.update_notice_text = ""

        self.api: Optional[ClientAPI] = None
        self.listener_task: Optional[asyncio.Task[Any]] = None
        self.shutdown_task: Optional[asyncio.Task[Any]] = None
        self.update_check_task: Optional[asyncio.Task[Any]] = None

        self._exiting = False
        self._check_for_updates_enabled = os.environ.get("TUNO_DISABLE_UPDATE_CHECK") != "1"
        self._set_feedback = set_feedback
        self._clear_pending_server_response = clear_pending_server_response
        self._render_state = render_state
        self._exit_app = exit_app
        self._api_factory = api_factory
        self._task_factory = task_factory

    def start_update_check(self, app_version: str) -> None:
        """Start a background release check when update checks are enabled."""
        if self._check_for_updates_enabled:
            self.update_check_task = self._task_factory(self._check_for_updates(app_version))

    async def _check_for_updates(self, app_version: str) -> None:
        """Fetch the latest release version without blocking initial TUI startup."""
        try:
            latest = await asyncio.to_thread(fetch_latest_release_version)
        except Exception:  # pragma: no cover - network failures are intentionally silent
            return

        if latest and is_newer_version(latest, app_version):
            self.update_notice_text = build_update_notice(latest)
            self._render_state()

    async def connect(self, player_name: Optional[str] = None, url: Optional[str] = None) -> None:
        """Join the lobby on the currently open websocket connection."""
        if url:
            await self.connect_server(url)
            if self.api is None:
                return

        if self.api is not None and self.player_id is not None:
            self._render_state()
            return

        name = (player_name or self.preferred_name).strip()
        if not name:
            self._set_feedback(CommandMessages.join_usage)
            return
        self.preferred_name = name

        if self.api is None:
            self._set_feedback(CommandMessages.server_first)
            return
        if self.selected_room_name is None:
            self._set_feedback(CommandMessages.room_first_connect)
            return

        try:
            await self.api.send(ClientMsg.JOIN, name=name)
        except Exception as exc:  # pragma: no cover
            self._set_feedback(CommandMessages.join_failed.format(error=exc))
            await self.api.close()
            self.api = None

    async def connect_server(self, url: str) -> None:
        """Open a websocket connection to the selected server URL."""
        target_url = url.strip()
        parsed = urlparse(target_url)
        if parsed.scheme not in {"ws", "wss"} or not parsed.netloc:
            self._set_feedback(CommandMessages.room_url_required)
            return

        next_api = self._api_factory(target_url)

        try:
            await next_api.open()
        except Exception as exc:  # pragma: no cover
            self._set_feedback(CommandMessages.server_connect_failed.format(error=exc))
            return

        self.server_history = remember_server(target_url)
        await self.close_current_server()
        self.selected_server_url = target_url
        self.api = next_api
        self.listener_task = self._task_factory(self.listen_loop())
        self.selected_room_name = None
        self.rooms = []
        self._set_feedback(CommandMessages.connected_choose_room)

    async def join_room(self, name: str) -> None:
        """Ask the connected server to enter an existing room."""
        await self._send_room_command(ClientMsg.JOIN_ROOM, name)

    async def create_room(self, name: str) -> None:
        """Ask the connected server to create and enter a new room."""
        await self._send_room_command(ClientMsg.CREATE_ROOM, name)

    async def _send_room_command(self, kind: ClientMsg, name: str) -> None:
        if self.api is None:
            self._set_feedback(CommandMessages.server_first)
            return

        room_name = name.strip()
        if not room_name:
            self._set_feedback(CommandMessages.room_name_required)
            return

        try:
            await self.api.send(kind, name=room_name)
        except Exception as exc:  # pragma: no cover
            self._set_feedback(CommandMessages.room_command_failed.format(error=exc))

    async def close_current_server(self) -> None:
        """Close the active websocket and clear state before switching servers."""
        listener_task = self.listener_task
        self.listener_task = None
        if listener_task is not None:
            listener_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await listener_task

        if self.api is not None:
            with contextlib.suppress(Exception):
                await self.api.close()

        self.api = None
        self.player_id = None
        self.selected_room_name = None
        self.rooms = []
        self.state = GameSnapshot()
        self.say_uno_next = False

    async def exit_server(self) -> None:
        """Drop the active server connection without exiting the app."""
        if self.api is None:
            self._set_feedback(CommandMessages.not_connected)
            return

        self._set_feedback(CommandMessages.disconnecting)

        # Send "leave" first so the server can release the player slot cleanly.
        if self.player_id is not None:
            with contextlib.suppress(Exception):
                await self.api.send(ClientMsg.LEAVE)

        await self.close_current_server()
        self._set_feedback(CommandMessages.disconnected)

    async def exit_game(self) -> None:
        """Leave the player slot while keeping the room connection for spectating."""
        if self.api is None:
            self._set_feedback(CommandMessages.not_connected)
            return
        if self.selected_room_name is None:
            self._set_feedback(CommandMessages.room_first)
            return
        if self.player_id is None:
            self._set_feedback(CommandMessages.join_first)
            return

        try:
            await self.api.send(ClientMsg.LEAVE)
        except Exception as exc:  # pragma: no cover
            self._set_feedback(CommandMessages.send_failed.format(error=exc))
            return

        self.player_id = None
        self.say_uno_next = False
        self._set_feedback(CommandMessages.left_game)

    async def exit_client(self) -> None:
        """Exit the UI immediately and finish websocket cleanup in the background."""
        self._exiting = True

        api = self.api
        player_id = self.player_id
        listener_task = self.listener_task

        self.api = None
        self.player_id = None
        self.selected_room_name = None
        self.rooms = []
        self.state = GameSnapshot()
        self.listener_task = None

        self.shutdown_task = self._task_factory(
            self._shutdown_transport(api, player_id, listener_task)
        )
        self._exit_app()

    async def _shutdown_transport(
        self,
        api: Optional[ClientAPI],
        player_id: Optional[str],
        listener_task: Optional[asyncio.Task[Any]],
    ) -> None:
        """Finish leave/close cleanup without blocking the visible app exit path."""
        if api is not None:
            if player_id is not None:
                with contextlib.suppress(Exception):
                    await api.send(ClientMsg.LEAVE)
            with contextlib.suppress(Exception):
                await api.close()

        if listener_task is not None:
            listener_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await listener_task

    async def listen_loop(self) -> None:
        """Consume server events until the websocket closes or raises."""
        assert self.api is not None

        try:
            async for message in self.api.events():
                await self.handle_message(message)
        except Exception as exc:  # pragma: no cover
            if self._exiting:
                return

            self.player_id = None
            self.selected_room_name = None
            self.rooms = []
            self.api = None
            self.state = GameSnapshot()
            self._set_feedback(CommandMessages.disconnected_error.format(error=exc))

    async def handle_message(self, message: Dict[str, Any]) -> None:
        """Apply one decoded server message to local client state."""
        kind = message.get("type")

        if kind == ServerMsg.WELCOME:
            self._clear_pending_server_response()
            self.player_id = message.get("player_id")
            self._render_state()
        elif kind == ServerMsg.ROOM_JOINED:
            self._clear_pending_server_response()
            self.selected_room_name = str(message.get("name", "")).strip() or None
            self.player_id = None
            self.state = GameSnapshot()
            self._render_state()
        elif kind in {ServerMsg.ROOM_CLOSED, ServerMsg.ROOM_LEFT}:
            self._clear_pending_server_response()
            self.selected_room_name = None
            self.player_id = None
            self.state = GameSnapshot()
            self.say_uno_next = False
            self._render_state()
        elif kind == ServerMsg.ROOM_LIST:
            self._clear_pending_server_response()
            self.rooms = list(message.get("rooms", []))
            self._render_state()
        elif kind == ServerMsg.ERROR:
            self._set_feedback(
                format_server_error(
                    self.state, message.get("message", "unknown error"), message.get("code", "")
                )
            )
        elif kind in (ServerMsg.INFO, ServerMsg.STATE):
            self._clear_pending_server_response()
            if kind == ServerMsg.STATE:
                self.state = GameSnapshot.from_dict(message.get("state", {}))
                # Clear a stale UNO arm whenever the turn ends or rolls over.
                if not self.state.your_turn:
                    self.say_uno_next = False
            self._render_state()

    async def send(self, kind: ClientMsg, **payload: Any) -> None:
        """Send one action to the server or surface a local transport error."""
        if not self.api:
            self._set_feedback(CommandMessages.connect_first)
            return
        if kind == ClientMsg.EXIT_ROOM and self.selected_room_name is None:
            self._set_feedback(CommandMessages.room_first)
            return

        try:
            await self.api.send(kind, **payload)
        except Exception as exc:  # pragma: no cover
            self._set_feedback(CommandMessages.send_failed.format(error=exc))
