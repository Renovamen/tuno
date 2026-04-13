from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Protocol

from textual.widgets import Input, Static

from tuno.client.actions import dispatch_command as dispatch_command_action
from tuno.client.completion import (
    CompletionState,
    apply_completion,
    command_candidates,
    move_selection,
    render_suggestions,
    sync_completion_state,
)
from tuno.client.rendering import my_hand


class CommandHost(Protocol):
    """Runtime contract expected by the command controller.

    The host remains the owner of transport, state snapshots, and the broader UI shell.
    The controller only coordinates command parsing, feedback, suggestions, and dispatch.
    """

    state: Dict[str, Any]
    player_id: Optional[str]
    preferred_name: str
    say_uno_next: bool
    api: Any

    async def connect(self, player_name: Optional[str] = None, url: Optional[str] = None) -> None: ...
    async def send(self, kind: str, **payload: Any) -> None: ...
    async def exit_client(self) -> None: ...
    def render_state(self) -> None: ...
    def query_one(self, selector: str, expect_type: type | None = None): ...


class CommandError(ValueError):
    """Raised when a user enters an invalid command."""


@dataclass(frozen=True)
class ParsedCommand:
    name: str
    args: List[str]


CANONICAL_COMMANDS = {
    "connect",
    "start",
    "play",
    "draw",
    "pass",
    "uno",
    "help",
    "exit",
}
VALID_PLAY_COLORS = {
    "red",
    "yellow",
    "green",
    "blue",
}


class CommandController:
    """Own command-bar parsing, completion, feedback, and dispatch orchestration."""

    def __init__(self, host: CommandHost) -> None:
        self.host = host
        self.command_feedback_message: Optional[str] = None
        self.awaiting_server_response = False
        self.completion_state = CompletionState()

    async def execute(self, raw: str) -> None:
        """Parse raw input and surface syntax errors before dispatching commands."""
        self.clear_feedback()

        try:
            command = parse_command(raw)
        except CommandError as exc:
            self.set_feedback(f"Command error: {exc}. Try /help.")
            return

        await self.dispatch(command)

    async def dispatch(self, command: ParsedCommand) -> None:
        """Execute a parsed command while preserving the existing render/update hooks."""
        previous_uno_state = self.host.say_uno_next
        if command.name not in {"help", "exit"}:
            self.set_pending_server_response()

        self.host.say_uno_next = await dispatch_command_action(
            command,
            preferred_name=self.host.preferred_name,
            say_uno_next=self.host.say_uno_next,
            state=self.host.state,
            connect=self.host.connect,
            send=self.host.send,
            exit_client=self.host.exit_client,
            set_command_feedback=self.set_feedback,
            render_state=self.host.render_state,
        )

        if command.name == "help" or (
            command.name == "uno" and self.host.say_uno_next != previous_uno_state
        ):
            self.host.render_state()

    def set_feedback(self, message: str) -> None:
        """Update the short-lived feedback shown beneath the input."""
        self.awaiting_server_response = False
        self.command_feedback_message = message
        self.host.render_state()

    def clear_feedback(self) -> None:
        """Clear any prior feedback before a new command attempt."""
        self.awaiting_server_response = False
        self.command_feedback_message = None
        self.host.render_state()

    def clear_pending_server_response(self) -> None:
        """Clear the pending-response hint when the next server message arrives."""
        if self.awaiting_server_response:
            self.awaiting_server_response = False
            self.command_feedback_message = None

    def reset_completion_state(self) -> None:
        """Reset transient completion state after a command is submitted."""
        self.completion_state = CompletionState()

    def set_pending_server_response(self) -> None:
        """Show a waiting hint after a valid command is sent to the server."""
        self.awaiting_server_response = True
        self.command_feedback_message = "Waiting for server response..."
        self.host.render_state()

    def available_commands(self) -> List[str]:
        """Return the currently legal command templates for the local player."""
        return derive_available_commands(
            self.host.state,
            connected=self.host.api is not None,
            joined=self.host.player_id is not None,
            uno_armed=self.host.say_uno_next,
        )

    def candidates(self, raw: str) -> List[Dict[str, str]]:
        """Build completion candidates for the current input and visible game state."""
        return command_candidates(
            raw,
            available_commands=self.available_commands(),
            hand=my_hand(self.host.state),
            current_color=self.host.state.get("current_color"),
            top_card=self.host.state.get("top_card") or None,
        )

    def render_meta(self, visible: bool, text: str) -> None:
        """Show command feedback or contextual guidance beneath the input."""
        meta = self.host.query_one("#command-meta", Static)
        meta.display = visible
        meta.update(text)

    def refresh_assist(self, raw: str, *, clear_feedback_on_suggestions: bool = False) -> None:
        """Refresh the suggestion dropdown from the current input and app state.

        Args:
            raw: The current command-bar contents to evaluate for slash-command suggestions.
            clear_feedback_on_suggestions: Set to ``True`` when showing fresh
                completion suggestions should clear any existing feedback message,
                such as a prior command error.
        """
        suggestions = self.host.query_one("#command-suggestions", Static)

        if not raw.startswith("/"):
            suggestions.display = False
            suggestions.update("")
            self.completion_state = CompletionState()
            return

        candidates = self.candidates(raw)
        self.completion_state = sync_completion_state(self.completion_state, candidates)
        if clear_feedback_on_suggestions and candidates and self.command_feedback_message is not None:
            self.command_feedback_message = None
            self.render_meta(
                self.host.player_id is None,
                "Join the game: /connect <name>" if self.host.player_id is None else "",
            )

        suggestions.display = True
        suggestions.update(render_suggestions(candidates, self.completion_state))

    def apply_tab_completion(self) -> None:
        """Apply the current tab-completion result to the command input widget."""
        command_input = self.host.query_one("#command-input", Input)
        candidates = self.candidates(command_input.value)
        if not candidates:
            return

        completed, self.completion_state = apply_completion(
            command_input.value,
            self.completion_state,
            candidates,
        )
        command_input.value = completed
        command_input.cursor_position = len(completed)
        self.refresh_assist(completed)

    def move_suggestion_selection(self, delta: int) -> bool:
        """Move the highlighted suggestion row when suggestions are visible."""
        command_input = self.host.query_one("#command-input", Input)
        candidates = self.candidates(command_input.value)
        if not command_input.value.startswith("/") or not candidates:
            return False

        self.completion_state = move_selection(self.completion_state, candidates, delta)
        self.refresh_assist(command_input.value)
        return True


def parse_command(raw: str) -> ParsedCommand:
    text = raw.strip()
    if not text:
        raise CommandError("Command is empty.")
    if not text.startswith("/"):
        raise CommandError("Commands must start with '/'.")

    parts = text[1:].split()
    if not parts:
        raise CommandError("Command is empty.")

    name = parts[0].lower()
    args = parts[1:]

    if name not in CANONICAL_COMMANDS:
        raise CommandError(f"Unknown command: /{name}")

    if name == "play":
        if len(args) not in {1, 2}:
            raise CommandError("Usage: /play <n> [color]")
        if not args[0].isdigit():
            raise CommandError("/play requires a numeric card index.")
        if len(args) == 2 and args[1].lower() not in VALID_PLAY_COLORS:
            raise CommandError("/play color must be one of: red, yellow, green, blue.")
    elif name in {"start", "draw", "pass", "uno", "help", "exit"} and args:
        raise CommandError(f"/{name} does not take arguments.")
    elif name == "connect" and len(args) > 1:
        raise CommandError("Usage: /connect [name]")

    return ParsedCommand(name=name, args=args)


def derive_available_commands(
    state: Dict[str, object], *, connected: bool, joined: bool, uno_armed: bool
) -> List[str]:
    if not connected or not joined:
        return ["/connect <name>", "/help", "/exit"]

    if state.get("finished"):
        commands = ["/help", "/exit"]
        if state.get("can_start"):
            commands.insert(0, "/start")
        return commands
    if not state.get("started"):
        commands = ["/help", "/exit"]
        if state.get("can_start"):
            commands.insert(0, "/start")
        return commands
    if not state.get("your_turn"):
        return ["/help", "/exit"]

    commands: List[str] = ["/play <n> [color]"]

    if state.get("can_draw"):
        commands.append("/draw")
    if state.get("can_pass"):
        commands.append("/pass")
    if state.get("uno_hint") or uno_armed:
        commands.append("/uno")

    commands.append("/help")
    commands.append("/exit")

    return commands
