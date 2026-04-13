"""Textual application entrypoint for the terminal UNO client."""

from __future__ import annotations

import argparse
import asyncio
import contextlib
from typing import Any, Dict, Optional

from textual.app import App, ComposeResult
from textual.containers import Container, Grid, Vertical, VerticalScroll
from textual.events import Key
from textual.widgets import Input, Static

from tuno.client.api import ClientAPI
from tuno.client.commands import CommandController
from tuno.client.rendering import format_server_error, render_tuno_logo
from tuno.client.theme import activate_tuno_theme
from tuno.client.view_state import build_view_state


class TunoApp(App):
    """Own the client-side Textual UI, local state, and command orchestration."""

    CSS_PATH = "app.tcss"

    def __init__(self, initial_url: str, initial_name: str = "") -> None:
        """Initialize the app with the default server URL and optional player name."""
        super().__init__()

        self.initial_url = initial_url
        self.preferred_name = initial_name.strip()

        self.player_id: Optional[str] = None
        self.state: Dict[str, Any] = {}
        self.say_uno_next = False
        self._exiting = False

        self.listener_task: Optional[asyncio.Task] = None
        self.shutdown_task: Optional[asyncio.Task] = None

        self.api: Optional[ClientAPI] = None
        self.command_controller = CommandController(self)

    def compose(self) -> ComposeResult:
        """Compose the static widget tree for the command-first client layout."""

        with Container(id="main-frame"):
            with Grid(id="main-columns"):
                with Vertical(id="left-panel"):
                    yield Static("Local Status", id="local-status-title", classes="section-title")
                    yield Static("", classes="section-divider")
                    yield Static("Join to view local hand info.", id="local-status-body")

                    yield Static("", classes="section-gap")
                    yield Static("", classes="section-gap")
                    yield Static("", id="tuno-logo")

                    with Vertical(id="hand-section"):
                        yield Static(
                            "Hand (scroll for more)", id="hand-title", classes="section-title"
                        )
                        yield Static("", classes="section-divider")
                        with VerticalScroll(id="hand-scroll"):
                            yield Static("", id="hand-body")

                with Vertical(id="right-panel"):
                    with Vertical(id="right-panel-sections"):
                        yield Static("Players (0/5)", id="players-title", classes="section-title")
                        yield Static("", classes="section-divider")
                        yield Static("No players yet.", id="players-body")

                        yield Static("", classes="section-gap")

                        yield Static(
                            "Recent Activity", id="recent-activity-title", classes="section-title"
                        )
                        yield Static("", classes="section-divider")
                        yield Static("", id="recent-top-card-body")
                        yield Static("", id="recent-top-card-divider", classes="section-divider")
                        yield Static("No game events yet.", id="recent-activity-body")

        with Container(id="command-zone"):
            with Container(id="command-input-shell"):
                yield Input(placeholder="/connect alice", id="command-input")
            yield Static("", id="command-meta")
            yield Static("", id="command-suggestions")

    async def on_mount(self) -> None:
        """Focus the command input and render the initial empty state."""
        from importlib.metadata import version as pkg_version

        activate_tuno_theme(self)

        try:
            self._app_version = pkg_version("tuno")
        except Exception:
            self._app_version = "0.1.1"

        self.query_one("#command-input", Input).focus()
        self.render_state()

    async def on_input_changed(self, event: Input.Changed) -> None:
        """Refresh suggestions whenever the command input text changes."""
        if event.input.id == "command-input":
            self.command_controller.refresh_assist(
                event.value,
                clear_feedback_on_suggestions=True,
            )

    async def on_key(self, event: Key) -> None:
        """Handle tab completion and suggestion navigation while the input is focused."""
        command_input = self.query_one("#command-input", Input)

        if self.focused is not command_input:
            return

        if event.key == "tab":
            event.prevent_default()
            event.stop()
            self.command_controller.apply_tab_completion()
            return
        if event.key == "down" and self.command_controller.move_suggestion_selection(1):
            event.prevent_default()
            event.stop()
            return
        if event.key == "up" and self.command_controller.move_suggestion_selection(-1):
            event.prevent_default()
            event.stop()

    async def on_input_submitted(self, event: Input.Submitted) -> None:
        """Dispatch one submitted command and reset transient completion state."""
        if event.input.id != "command-input":
            return

        command_text = event.value.strip()
        event.input.value = ""
        await self.execute_command(command_text)

    async def execute_command(self, raw: str) -> None:
        """Public command entrypoint retained as a thin delegate to the controller."""
        self.command_controller.reset_completion_state()
        await self.command_controller.execute(raw)

    async def connect(self, player_name: Optional[str] = None, url: Optional[str] = None) -> None:
        """Open the websocket, join the lobby, and start the listen loop."""
        if self.api is not None and self.player_id is not None:
            self.render_state()
            return

        name = (player_name or self.preferred_name).strip()
        if not name:
            self.command_controller.set_feedback("Command error: Usage: /connect <name>")
            return
        self.preferred_name = name

        if self.api:
            await self.api.close()
            self.api = None

        target_url = (url or self.initial_url).strip() or "ws://127.0.0.1:8765"
        self.api = ClientAPI(target_url)

        try:
            await self.api.open()
        except Exception as exc:  # pragma: no cover
            self.api = None
            self.command_controller.set_feedback(f"Connect failed: {exc}")
            return

        self.render_state()

        try:
            await self.api.send("join", name=name)
        except Exception as exc:  # pragma: no cover
            self.command_controller.set_feedback(f"Join failed: {exc}")
            await self.api.close()
            self.api = None

        self.listener_task = asyncio.create_task(self.listen_loop())

    async def exit_client(self) -> None:
        """Exit the UI immediately and finish websocket cleanup in the background."""
        self._exiting = True

        api = self.api
        player_id = self.player_id
        listener_task = self.listener_task

        self.api = None
        self.player_id = None
        self.state = {}
        self.listener_task = None

        self.shutdown_task = asyncio.create_task(
            self._shutdown_transport(api, player_id, listener_task)
        )
        self.exit()

    async def _shutdown_transport(
        self,
        api: Optional[ClientAPI],
        player_id: Optional[str],
        listener_task: Optional[asyncio.Task],
    ) -> None:
        """Finish leave/close cleanup without blocking the visible app exit path."""
        if api is not None:
            if player_id is not None:
                with contextlib.suppress(Exception):
                    await api.send("leave")
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
            self.api = None
            self.state = {}
            self.command_controller.set_feedback(f"Disconnected: {exc}")

    async def handle_message(self, message: Dict[str, Any]) -> None:
        """Apply one decoded server message to local UI state."""
        kind = message.get("type")

        if kind == "welcome":
            self.command_controller.clear_pending_server_response()
            self.player_id = message.get("player_id")
            self.render_state()
        elif kind == "error":
            self.command_controller.set_feedback(
                format_server_error(
                    self.state, message.get("message", "unknown error"), message.get("code", "")
                )
            )
        elif kind in ("info", "state"):
            self.command_controller.clear_pending_server_response()
            if kind == "state":
                self.state = message.get("state", {})
            self.render_state()

    async def send(self, kind: str, **payload: Any) -> None:
        """Send one action to the server or surface a local transport error."""
        if not self.api:
            self.command_controller.set_feedback("Command error: Connect first.")
            return

        try:
            await self.api.send(kind, **payload)
        except Exception as exc:  # pragma: no cover
            self.command_controller.set_feedback(f"Error: Send failed: {exc}")

    def render_state(self) -> None:
        """Re-render all state-derived widgets from the latest local snapshot."""
        server_target = self.api.url if self.api else self.initial_url
        available = self.command_controller.available_commands()
        view_state = build_view_state(
            app_version=self._app_version,
            server_target=server_target,
            state=self.state,
            player_id=self.player_id,
            command_feedback_message=self.command_controller.command_feedback_message,
            say_uno_next=self.say_uno_next,
            available_commands=available,
        )
        self.query_one("#main-frame").border_title = view_state.border_title

        # Tuno logo
        logo = self.query_one("#tuno-logo", Static)
        if not self.state.get("started"):
            logo.display = True
            logo.update(render_tuno_logo())
        else:
            logo.display = False
            logo.update("")

        # Local status section
        self.query_one("#local-status-body", Static).update(view_state.local_status_body)

        # Cards in hand section
        hand_section = self.query_one("#hand-section", Vertical)
        hand_section.display = view_state.hand_visible
        self.query_one("#hand-body", Static).update(
            view_state.hand_body if view_state.hand_visible else ""
        )

        # Players list section
        self.query_one("#players-title", Static).update(view_state.players_title)
        self.query_one("#players-body", Static).update(view_state.players_body)

        # Recent activity section
        # -- The top card is rendered at the top of this section
        top_card_body = self.query_one("#recent-top-card-body", Static)
        top_card_divider = self.query_one("#recent-top-card-divider", Static)
        top_card_body.display = view_state.top_card_visible
        top_card_divider.display = view_state.top_card_visible
        top_card_body.update(view_state.top_card_body if view_state.top_card_visible else "")

        # -- Followed by the recent activity log
        self.query_one("#recent-activity-body", Static).update(view_state.recent_activity_body)

        # Command input and suggestions
        self.command_controller.render_meta(
            view_state.command_meta_visible,
            view_state.command_meta_text,
        )
        command_input = self.query_one("#command-input", Input)
        command_input.placeholder = view_state.input_placeholder
        self.command_controller.refresh_assist(command_input.value)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the tuno terminal client.")
    parser.add_argument("server", nargs="?", default=None, help="Server websocket URL.")
    parser.add_argument("--server", dest="server_flag", default=None, help="Server websocket URL.")
    parser.add_argument(
        "--name",
        dest="player_name",
        default=None,
        help="Optional player name used by /connect if omitted.",
    )
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    initial_server = args.server_flag or args.server or "ws://127.0.0.1:8765"
    app = TunoApp(initial_server, initial_name=args.player_name or "")
    app.run()


if __name__ == "__main__":
    main()
