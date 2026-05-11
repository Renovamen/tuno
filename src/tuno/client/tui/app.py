"""Textual application entrypoint for the terminal UNO client."""

from __future__ import annotations

import argparse
import sys
from typing import Any, Dict, Optional

from textual.app import App, ComposeResult
from textual.containers import Container, Grid, Vertical, VerticalScroll
from textual.events import Key
from textual.widgets import Input, Static

from tuno import __version__
from tuno.client.api import ClientAPI
from tuno.client.runtime import ClientRuntime
from tuno.client.tui.commands import CommandController
from tuno.client.tui.rendering import render_tuno_logo
from tuno.client.tui.theme import activate_tuno_theme
from tuno.client.tui.view_state import build_view_state
from tuno.client.updates import perform_self_update


class TunoApp(App):
    """Own the client-side Textual UI and delegate runtime behavior."""

    CSS_PATH = "app.tcss"

    def __init__(self, initial_url: str = "", initial_name: str = "") -> None:
        """Initialize the app with an optional server URL and player name."""
        super().__init__()

        self.command_controller = CommandController(self)
        self.runtime = ClientRuntime(
            initial_url=initial_url,
            initial_name=initial_name,
            set_feedback=self.command_controller.set_feedback,
            clear_pending_server_response=self.command_controller.clear_pending_server_response,
            render_state=self.render_state,
            exit_app=lambda: self.exit(),
        )
        self._app_version = __version__

    @property
    def selected_server_url(self) -> str:
        return self.runtime.selected_server_url

    @selected_server_url.setter
    def selected_server_url(self, value: str) -> None:
        self.runtime.selected_server_url = value

    @property
    def preferred_name(self) -> str:
        return self.runtime.preferred_name

    @preferred_name.setter
    def preferred_name(self, value: str) -> None:
        self.runtime.preferred_name = value

    @property
    def server_history(self) -> list[str]:
        return self.runtime.server_history

    @server_history.setter
    def server_history(self, value: list[str]) -> None:
        self.runtime.server_history = value

    @property
    def player_id(self) -> Optional[str]:
        return self.runtime.player_id

    @player_id.setter
    def player_id(self, value: Optional[str]) -> None:
        self.runtime.player_id = value

    @property
    def state(self) -> Dict[str, Any]:
        return self.runtime.state

    @state.setter
    def state(self, value: Dict[str, Any]) -> None:
        self.runtime.state = value

    @property
    def say_uno_next(self) -> bool:
        return self.runtime.say_uno_next

    @say_uno_next.setter
    def say_uno_next(self, value: bool) -> None:
        self.runtime.say_uno_next = value

    @property
    def listener_task(self):
        return self.runtime.listener_task

    @listener_task.setter
    def listener_task(self, value) -> None:
        self.runtime.listener_task = value

    @property
    def shutdown_task(self):
        return self.runtime.shutdown_task

    @shutdown_task.setter
    def shutdown_task(self, value) -> None:
        self.runtime.shutdown_task = value

    @property
    def update_check_task(self):
        return self.runtime.update_check_task

    @update_check_task.setter
    def update_check_task(self, value) -> None:
        self.runtime.update_check_task = value

    @property
    def api(self) -> Optional[ClientAPI]:
        return self.runtime.api

    @api.setter
    def api(self, value: Optional[ClientAPI]) -> None:
        self.runtime.api = value

    @property
    def update_notice_text(self) -> str:
        return self.runtime.update_notice_text

    @update_notice_text.setter
    def update_notice_text(self, value: str) -> None:
        self.runtime.update_notice_text = value

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
                            "Hand (scroll for more)",
                            id="hand-title",
                            classes="section-title",
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

                        with Vertical(id="recent-activity-section"):
                            yield Static(
                                "Recent Activity (scroll for more)",
                                id="recent-activity-title",
                                classes="section-title",
                            )
                            yield Static("", classes="section-divider")
                            yield Static("", id="recent-top-card-body")
                            yield Static(
                                "", id="recent-top-card-divider", classes="section-divider"
                            )
                            with VerticalScroll(id="recent-activity-scroll"):
                                yield Static("No game events yet.", id="recent-activity-body")

        with Container(id="command-zone"):
            with Container(id="command-input-shell"):
                yield Input(placeholder="/server ws://127.0.0.1:8765", id="command-input")

            yield Static("", id="command-meta")
            yield Static("", id="command-suggestions")

            yield Static("", id="update-notice")

    async def on_mount(self) -> None:
        """Focus the command input and render the initial empty state."""
        from importlib.metadata import version as pkg_version

        activate_tuno_theme(self)

        try:
            self._app_version = pkg_version("tuno")
        except Exception:
            self._app_version = __version__

        self.query_one("#command-input", Input).focus()

        self.runtime.start_update_check(self._app_version)

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

        if (
            event.key == "enter"
            and self.command_controller.server_history_active
            and not command_input.value.strip()
        ):
            event.prevent_default()
            event.stop()
            await self.execute_command("")
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
        """Delegate lobby join behavior to the runtime service."""
        await self.runtime.connect(player_name=player_name, url=url)

    async def connect_server(self, url: str) -> None:
        """Delegate server switching behavior to the runtime service."""
        await self.runtime.connect_server(url)

    async def exit_client(self) -> None:
        """Delegate shutdown behavior to the runtime service."""
        await self.runtime.exit_client()

    async def send(self, kind: str, **payload: Any) -> None:
        """Delegate one outbound server action to the runtime service."""
        await self.runtime.send(kind, **payload)

    def render_state(self) -> None:
        """Re-render all state-derived widgets from the latest local snapshot."""
        server_target = self.api.url if self.api else self.selected_server_url or "No server"
        available = self.command_controller.available_commands()
        view_state = build_view_state(
            app_version=self._app_version,
            server_target=server_target,
            state=self.state,
            connected=self.api is not None,
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

        # Check and notify about updates if needed
        update_notice = self.query_one("#update-notice", Static)
        update_notice.display = bool(self.update_notice_text)
        update_notice.update(self.update_notice_text)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the tuno terminal client.")
    parser.add_argument(
        "--name",
        dest="player_name",
        default=None,
        help="Optional player name used by /connect if omitted.",
    )
    return parser


def build_update_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Update the installed tuno client.")
    return parser


def main() -> None:
    if len(sys.argv) > 1 and sys.argv[1] == "update":
        build_update_parser().parse_args(sys.argv[2:])
        perform_self_update(__version__)
        return

    parser = build_parser()
    args = parser.parse_args()
    app = TunoApp(initial_name=args.player_name or "")
    app.run()


if __name__ == "__main__":
    main()
