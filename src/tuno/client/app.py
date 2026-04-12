"""Textual application entrypoint for the terminal UNO client."""

from __future__ import annotations

import argparse
import asyncio
import contextlib
from typing import Any, Dict, List, Optional

from textual.app import App, ComposeResult
from textual.containers import Container, Grid, Vertical, VerticalScroll
from textual.events import Key
from textual.widgets import Input, Static

from tuno.client.actions import dispatch_command
from tuno.client.api import ClientAPI
from tuno.client.commands import (
    CommandError,
    ParsedCommand,
    derive_available_commands,
    parse_command,
)
from tuno.client.completion import (
    CompletionState,
    apply_completion,
    command_candidates,
    move_selection,
    render_suggestions,
    sync_completion_state,
)
from tuno.client.rendering import format_server_error, my_hand, render_tuno_logo
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
        self.api: Optional[ClientAPI] = None
        self.player_id: Optional[str] = None
        self.state: Dict[str, Any] = {}
        self.say_uno_next = False
        self._exiting = False
        self.listener_task: Optional[asyncio.Task] = None
        self.shutdown_task: Optional[asyncio.Task] = None
        self.command_feedback_message: Optional[str] = None
        self.completion_state = CompletionState()

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
            self._app_version = "0.1.0"

        self.query_one("#command-input", Input).focus()
        self.render_state()

    async def on_input_changed(self, event: Input.Changed) -> None:
        """Refresh suggestions whenever the command input text changes."""
        if event.input.id == "command-input":
            self._refresh_command_assist(event.value)

    async def on_key(self, event: Key) -> None:
        """Handle tab completion and suggestion navigation while the input is focused."""
        command_input = self.query_one("#command-input", Input)

        if self.focused is not command_input:
            return

        if event.key == "tab":
            event.prevent_default()
            event.stop()
            self._apply_tab_completion()
            return
        if event.key == "down" and self._move_suggestion_selection(1):
            event.prevent_default()
            event.stop()
            return
        if event.key == "up" and self._move_suggestion_selection(-1):
            event.prevent_default()
            event.stop()

    async def on_input_submitted(self, event: Input.Submitted) -> None:
        """Dispatch one submitted command and reset transient completion state."""
        if event.input.id != "command-input":
            return

        command_text = event.value.strip()
        event.input.value = ""
        self.completion_state = CompletionState()
        await self.execute_command(command_text)

    async def execute_command(self, raw: str) -> None:
        """Parse raw input and route syntax errors into command feedback."""
        self.clear_command_feedback()
        try:
            command = parse_command(raw)
        except CommandError as exc:
            self.set_command_feedback(f"Command error: {exc}. Try /help.")
            return
        await self.dispatch_command(command)

    async def dispatch_command(self, command: ParsedCommand) -> None:
        """Map parsed slash commands onto client actions and server messages."""
        previous_uno_state = self.say_uno_next
        self.say_uno_next = await dispatch_command(
            command,
            preferred_name=self.preferred_name,
            say_uno_next=self.say_uno_next,
            state=self.state,
            connect=self.connect,
            send=self.send,
            exit_client=self.exit_client,
            set_command_feedback=self.set_command_feedback,
            render_state=self.render_state,
        )
        if command.name == "help" or (
            command.name == "uno" and self.say_uno_next != previous_uno_state
        ):
            self.render_state()

    async def connect(self, player_name: Optional[str] = None, url: Optional[str] = None) -> None:
        """Open the websocket, join the lobby, and start the listen loop."""
        if self.api is not None and self.player_id is not None:
            self.render_state()
            return

        name = (player_name or self.preferred_name).strip()
        if not name:
            self.set_command_feedback("Command error: Usage: /connect <name>")
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
            self.set_command_feedback(f"Connect failed: {exc}")
            return

        self.render_state()

        try:
            await self.api.send("join", name=name)
        except Exception as exc:  # pragma: no cover
            self.set_command_feedback(f"Join failed: {exc}")
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
            self.set_command_feedback(f"Disconnected: {exc}")

    async def handle_message(self, message: Dict[str, Any]) -> None:
        """Apply one decoded server message to local UI state."""
        kind = message.get("type")

        if kind == "welcome":
            self.player_id = message.get("player_id")
            self.render_state()
        elif kind == "error":
            self.set_command_feedback(
                format_server_error(
                    self.state, message.get("message", "unknown error"), message.get("code", "")
                )
            )
        elif kind in ("info", "state"):
            if kind == "state":
                self.state = message.get("state", {})
            self.render_state()

    async def send(self, kind: str, **payload: Any) -> None:
        """Send one action to the server or surface a local transport error."""
        if not self.api:
            self.set_command_feedback("Command error: Connect first.")
            return

        try:
            await self.api.send(kind, **payload)
        except Exception as exc:  # pragma: no cover
            self.set_command_feedback(f"Error: Send failed: {exc}")

    def render_state(self) -> None:
        """Re-render all state-derived widgets from the latest local snapshot."""
        server_target = self.api.url if self.api else self.initial_url
        available = self._available_commands()
        view_state = build_view_state(
            app_version=self._app_version,
            server_target=server_target,
            state=self.state,
            player_id=self.player_id,
            command_feedback_message=self.command_feedback_message,
            say_uno_next=self.say_uno_next,
            available_commands=available,
        )
        self.query_one("#main-frame").border_title = view_state.border_title

        logo = self.query_one("#tuno-logo", Static)
        if not self.state.get("started"):
            logo.display = True
            logo.update(render_tuno_logo())
        else:
            logo.display = False
            logo.update("")

        self.query_one("#local-status-body", Static).update(view_state.local_status_body)

        hand_section = self.query_one("#hand-section", Vertical)
        hand_section.display = view_state.hand_visible
        self.query_one("#hand-body", Static).update(
            view_state.hand_body if view_state.hand_visible else ""
        )

        self.query_one("#players-title", Static).update(view_state.players_title)
        self.query_one("#players-body", Static).update(view_state.players_body)

        top_card_body = self.query_one("#recent-top-card-body", Static)
        top_card_divider = self.query_one("#recent-top-card-divider", Static)
        top_card_body.display = view_state.top_card_visible
        top_card_divider.display = view_state.top_card_visible
        top_card_body.update(view_state.top_card_body if view_state.top_card_visible else "")

        self.query_one("#recent-activity-body", Static).update(view_state.recent_activity_body)

        self._render_command_meta(view_state.command_meta_visible, view_state.command_meta_text)
        command_input = self.query_one("#command-input", Input)
        command_input.placeholder = view_state.input_placeholder
        self._refresh_command_assist(command_input.value)

    def set_command_feedback(self, message: str) -> None:
        """Update the short-lived command feedback shown beneath the input."""
        self.command_feedback_message = message
        self.render_state()

    def clear_command_feedback(self) -> None:
        """Clear any transient command feedback before the next command attempt."""
        self.command_feedback_message = None
        self.render_state()

    def _available_commands(self) -> List[str]:
        """Return the currently legal command templates for the local player."""
        return derive_available_commands(
            self.state,
            connected=self.api is not None,
            joined=self.player_id is not None,
            uno_armed=self.say_uno_next,
        )

    def _candidates(self, raw: str) -> List[Dict[str, str]]:
        """Build completion candidates for the current input and game state."""
        return command_candidates(
            raw,
            available_commands=self._available_commands(),
            hand=my_hand(self.state),
            current_color=self.state.get("current_color"),
            top_card=self.state.get("top_card") or None,
        )

    def _render_command_meta(self, visible: bool, text: str) -> None:
        """Show either command feedback or contextual prompt guidance beneath the input."""
        meta = self.query_one("#command-meta", Static)
        meta.display = visible
        meta.update(text)

    def _refresh_command_assist(self, raw: str) -> None:
        """Refresh the suggestion dropdown from the current input and state."""
        suggestions = self.query_one("#command-suggestions", Static)

        if not raw.startswith("/"):
            suggestions.display = False
            suggestions.update("")
            self.completion_state = CompletionState()
            return

        candidates = self._candidates(raw)
        self.completion_state = sync_completion_state(self.completion_state, candidates)

        suggestions.display = True
        suggestions.update(render_suggestions(candidates, self.completion_state))

    def _apply_tab_completion(self) -> None:
        """Apply the current tab-completion result to the command input."""
        command_input = self.query_one("#command-input", Input)
        candidates = self._candidates(command_input.value)
        if not candidates:
            return

        completed, self.completion_state = apply_completion(
            command_input.value, self.completion_state, candidates
        )
        command_input.value = completed
        command_input.cursor_position = len(completed)

        self._refresh_command_assist(completed)

    def _move_suggestion_selection(self, delta: int) -> bool:
        """Move the highlighted suggestion row when the dropdown is visible."""
        command_input = self.query_one("#command-input", Input)
        candidates = self._candidates(command_input.value)
        if not command_input.value.startswith("/") or not candidates:
            return False

        self.completion_state = move_selection(self.completion_state, candidates, delta)
        self._refresh_command_assist(command_input.value)

        return True


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
