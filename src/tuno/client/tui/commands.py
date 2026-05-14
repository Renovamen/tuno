from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Protocol

from textual.widgets import Input, Static

from tuno.client.actions import dispatch_command as dispatch_command_action
from tuno.client.state import my_hand
from tuno.client.tui.completion import (
    CompletionState,
    apply_completion,
    command_candidates,
    move_selection,
    sync_completion_state,
)
from tuno.client.tui.suggestions import render_suggestions


class CommandError(ValueError):
    """Raised when a user enters an invalid command."""


@dataclass(frozen=True)
class ParsedCommand:
    name: str
    args: List[str]


@dataclass(frozen=True)
class CommandSpec:
    """Central definition for a user-facing slash command."""

    name: str
    template: str
    min_args: int = 0
    max_args: int = 0
    trailing_space_completion: bool = False

    @property
    def token(self) -> str:
        return f"/{self.name}"

    @property
    def usage(self) -> str:
        return self.template

    @property
    def takes_args(self) -> bool:
        return self.max_args > 0


COMMAND_SPECS_BY_NAME = {
    spec.name: spec
    for spec in (
        CommandSpec(
            "connect", "/connect <room>", min_args=1, max_args=1, trailing_space_completion=True
        ),
        CommandSpec("server", "/server <server>", max_args=1, trailing_space_completion=True),
        CommandSpec(
            "join", "/join <player_name>", min_args=1, max_args=1, trailing_space_completion=True
        ),
        CommandSpec(
            "create", "/create <room>", min_args=1, max_args=1, trailing_space_completion=True
        ),
        CommandSpec("start", "/start"),
        CommandSpec(
            "play", "/play <n> [color]", min_args=1, max_args=2, trailing_space_completion=True
        ),
        CommandSpec("draw", "/draw"),
        CommandSpec("pass", "/pass"),
        CommandSpec("uno", "/uno"),
        CommandSpec("exit_room", "/exit_room"),
        CommandSpec("help", "/help"),
        CommandSpec("exit", "/exit"),
    )
}

CANONICAL_COMMANDS = frozenset(COMMAND_SPECS_BY_NAME)

CONNECT_COMMAND = COMMAND_SPECS_BY_NAME["connect"]
SERVER_COMMAND = COMMAND_SPECS_BY_NAME["server"]
JOIN_PLAYER_COMMAND = COMMAND_SPECS_BY_NAME["join"]
CREATE_ROOM_COMMAND = COMMAND_SPECS_BY_NAME["create"]
START_COMMAND = COMMAND_SPECS_BY_NAME["start"]
PLAY_COMMAND = COMMAND_SPECS_BY_NAME["play"]
DRAW_COMMAND = COMMAND_SPECS_BY_NAME["draw"]
PASS_COMMAND = COMMAND_SPECS_BY_NAME["pass"]
UNO_COMMAND = COMMAND_SPECS_BY_NAME["uno"]
EXIT_ROOM_COMMAND = COMMAND_SPECS_BY_NAME["exit_room"]
HELP_COMMAND = COMMAND_SPECS_BY_NAME["help"]
EXIT_COMMAND = COMMAND_SPECS_BY_NAME["exit"]

SERVER_SELECTION_COMMANDS = (
    SERVER_COMMAND.template,
    HELP_COMMAND.template,
    EXIT_COMMAND.template,
)
ROOM_SELECTION_COMMANDS = (
    CONNECT_COMMAND.template,
    CREATE_ROOM_COMMAND.template,
    HELP_COMMAND.template,
    EXIT_COMMAND.template,
)
ROOM_EXIT_COMMANDS = (
    HELP_COMMAND.template,
    EXIT_ROOM_COMMAND.template,
    EXIT_COMMAND.template,
)
PLAYER_JOIN_COMMANDS = (JOIN_PLAYER_COMMAND.template, *ROOM_EXIT_COMMANDS)
PLAYER_TURN_COMMANDS = (
    PLAY_COMMAND.template,
    DRAW_COMMAND.template,
    PASS_COMMAND.template,
    UNO_COMMAND.template,
)

VALID_PLAY_COLORS = (
    "red",
    "yellow",
    "green",
    "blue",
)


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
    spec = COMMAND_SPECS_BY_NAME.get(name)

    if spec is None:
        raise CommandError(f"Unknown command: /{name}")

    if not spec.takes_args and args:
        raise CommandError(f"{spec.token} does not take arguments.")
    if len(args) < spec.min_args or len(args) > spec.max_args:
        raise CommandError(f"Usage: {spec.usage}")

    if spec is PLAY_COMMAND:
        if not args[0].isdigit():
            raise CommandError(f"{PLAY_COMMAND.token} requires a numeric card index.")
        if len(args) == 2 and args[1].lower() not in VALID_PLAY_COLORS:
            raise CommandError(
                f"{PLAY_COMMAND.token} color must be one of: {', '.join(VALID_PLAY_COLORS)}."
            )

    return ParsedCommand(name=name, args=args)


def derive_available_commands(
    state: Dict[str, object],
    *,
    connected: bool,
    room_selected: bool,
    joined: bool,
    uno_armed: bool,
) -> List[str]:
    if not connected:
        return list(SERVER_SELECTION_COMMANDS)

    if not room_selected:
        return list(ROOM_SELECTION_COMMANDS)

    if not joined:
        return list(PLAYER_JOIN_COMMANDS)

    if state.get("finished"):
        return _with_optional_start(state)
    if not state.get("started"):
        return _with_optional_start(state)
    if not state.get("your_turn"):
        return list(ROOM_EXIT_COMMANDS)

    commands: List[str] = [PLAYER_TURN_COMMANDS[0]]

    if state.get("can_draw"):
        commands.append(PLAYER_TURN_COMMANDS[1])
    if state.get("can_pass"):
        commands.append(PLAYER_TURN_COMMANDS[2])
    if state.get("uno_hint") or uno_armed:
        commands.append(PLAYER_TURN_COMMANDS[3])

    commands.extend(ROOM_EXIT_COMMANDS)

    return commands


def _with_optional_start(state: Dict[str, object]) -> List[str]:
    """Return lobby/finished commands, optionally prefixed with host start."""
    commands = list(ROOM_EXIT_COMMANDS)
    if state.get("can_start"):
        commands.insert(0, START_COMMAND.template)
    return commands


def command_template_candidate(template: str) -> Dict[str, str]:
    """Turn a canonical command template into insert/display suggestion data."""
    base = template.split()[0]
    spec = COMMAND_SPECS_BY_NAME.get(base.removeprefix("/"))
    insert = base + " " if spec and spec.trailing_space_completion else base
    return {
        "insert": insert,
        "display": template,
    }


def matches_command_token(text: str, spec: CommandSpec) -> bool:
    return text == spec.token or text.startswith(f"{spec.token} ")


class CommandHost(Protocol):
    """Runtime contract expected by the command controller.

    The host remains the owner of transport, state snapshots, and the broader UI shell.
    The controller only coordinates command parsing, feedback, suggestions, and dispatch.
    """

    state: Dict[str, Any]
    player_id: Optional[str]
    selected_room_name: Optional[str]
    preferred_name: str
    say_uno_next: bool
    api: Any
    server_history: List[str]

    async def connect_server(self, url: str) -> None: ...
    async def join_room(self, name: str) -> None: ...
    async def create_room(self, name: str) -> None: ...
    async def connect(
        self, player_name: Optional[str] = None, url: Optional[str] = None
    ) -> None: ...
    async def send(self, kind: str, **payload: Any) -> None: ...
    async def exit_client(self) -> None: ...
    def render_state(self) -> None: ...
    def query_one(self, selector: str, expect_type: type | None = None): ...


class CommandController:
    """Own command-bar parsing, completion, feedback, and dispatch orchestration."""

    def __init__(self, host: CommandHost) -> None:
        self.host = host
        self.command_feedback_message: Optional[str] = None
        self.awaiting_server_response = False
        self.completion_state = CompletionState()
        self.server_history_active = False

    async def execute(self, raw: str) -> None:
        """Parse raw input and surface syntax errors before dispatching commands."""
        if self.server_history_active and raw.strip() in {"", SERVER_COMMAND.token}:
            await self.connect_selected_server_history()
            return

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
        if command.name not in {HELP_COMMAND.name, EXIT_COMMAND.name} and not (
            command.name == SERVER_COMMAND.name and not command.args
        ):
            self.set_pending_server_response()

        if command.name == SERVER_COMMAND.name and not command.args:
            self.show_server_history()
        else:
            self.server_history_active = False
            self.host.say_uno_next = await dispatch_command_action(
                command,
                preferred_name=self.host.preferred_name,
                say_uno_next=self.host.say_uno_next,
                state=self.host.state,
                connect=self.host.connect,
                connect_server=self.host.connect_server,
                join_room=self.host.join_room,
                create_room=self.host.create_room,
                send=self.host.send,
                exit_client=self.host.exit_client,
                set_command_feedback=self.set_feedback,
                render_state=self.host.render_state,
            )

        if command.name == HELP_COMMAND.name or (
            command.name == UNO_COMMAND.name and self.host.say_uno_next != previous_uno_state
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
        if not self.server_history_active:
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
            room_selected=self.host.selected_room_name is not None,
            joined=self.host.player_id is not None,
            uno_armed=self.host.say_uno_next,
        )

    def candidates(self, raw: str) -> List[Dict[str, str]]:
        """Build completion candidates for the current input and visible game state."""
        server_candidates = self._server_history_candidates(raw)
        if server_candidates is not None:
            return server_candidates

        return command_candidates(
            raw,
            available_commands=self.available_commands(),
            card_command_token=PLAY_COMMAND.token,
            command_template_candidate=command_template_candidate,
            valid_play_colors=VALID_PLAY_COLORS,
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

        if (
            self.server_history_active
            and raw.strip()
            and not matches_command_token(raw.strip(), SERVER_COMMAND)
        ):
            self.server_history_active = False
            self.completion_state = CompletionState()

        if not raw.startswith("/"):
            if self.server_history_active and not raw.strip():
                candidates = self.candidates(raw)
                self.completion_state = sync_completion_state(self.completion_state, candidates)
                suggestions.display = True
                suggestions.update(render_suggestions(candidates, self.completion_state))
                return
            suggestions.display = False
            suggestions.update("")
            self.completion_state = CompletionState()
            return

        candidates = self.candidates(raw)
        self.completion_state = sync_completion_state(self.completion_state, candidates)
        if (
            clear_feedback_on_suggestions
            and candidates
            and self.command_feedback_message is not None
        ):
            self.command_feedback_message = None
            self.render_meta(
                self.host.player_id is None,
                self._default_meta_text() if self.host.player_id is None else "",
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

        if self.server_history_active:
            selected = candidates[self.completion_state.suggestion_index]
            command_input.value = selected["insert"]
            command_input.cursor_position = len(command_input.value)

        self.refresh_assist(command_input.value)
        return True

    def show_server_history(self) -> None:
        """Show the selectable server history list after a bare server command."""
        if not self.host.server_history:
            self.server_history_active = False
            self.set_feedback(f"Command error: No server history. Usage: {SERVER_COMMAND.usage}")
            return

        self.server_history_active = True

        self.completion_state = CompletionState()
        command_input = self.host.query_one("#command-input", Input)
        command_input.value = f"{SERVER_COMMAND.token} "
        command_input.cursor_position = len(command_input.value)
        command_input.focus()

        self.set_feedback("Select a server with Up/Down, then press Enter.")

    async def connect_selected_server_history(self) -> None:
        """Connect to the currently selected server history entry."""
        candidates = self._server_history_candidates("") or []
        if not candidates:
            self.server_history_active = False
            self.set_feedback(f"Command error: No server history. Usage: {SERVER_COMMAND.usage}")
            return

        index = min(self.completion_state.suggestion_index, len(candidates) - 1)
        target = candidates[index]["insert"].removeprefix(f"{SERVER_COMMAND.token} ").strip()
        self.server_history_active = False
        self.completion_state = CompletionState()
        await self.host.connect_server(target)

    def _server_history_candidates(self, raw: str) -> List[Dict[str, str]] | None:
        """Return server-history candidates when the command bar is in server mode."""
        text = raw.strip()
        if not self.server_history_active and not matches_command_token(text, SERVER_COMMAND):
            return None

        if matches_command_token(text, SERVER_COMMAND):
            parts = text.split(maxsplit=1)
            if len(parts) == 1 and not (raw.endswith(" ") or self.server_history_active):
                return None
            prefix = "" if self.server_history_active else parts[1] if len(parts) == 2 else ""
        elif self.server_history_active and not text:
            prefix = ""
        else:
            return None

        return [
            {"insert": f"{SERVER_COMMAND.token} {url}", "display": url}
            for url in self.host.server_history
            if url.startswith(prefix)
        ]

    def _default_meta_text(self) -> str:
        if self.host.api is None:
            return f"Connect to a server: {SERVER_COMMAND.template}"
        if self.host.selected_room_name is None:
            return f"Choose a room: {CONNECT_COMMAND.template} or {CREATE_ROOM_COMMAND.template}"
        return f"Join the game: {JOIN_PLAYER_COMMAND.template}"
