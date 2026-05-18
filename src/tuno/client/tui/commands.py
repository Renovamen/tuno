from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Protocol

from textual.widgets import Input, Static

from tuno.client.state import my_hand
from tuno.client.tui.completion import (
    CompletionState,
    apply_completion,
    command_candidates,
    move_selection,
    sync_completion_state,
)
from tuno.client.tui.suggestions import render_suggestions
from tuno.core.cards import Color
from tuno.core.snapshot import GameSnapshot
from tuno.protocol.messages import ClientMsg


class CommandMessages:
    """User-visible command-bar feedback strings shared by the runtime and controller."""

    # Command errors
    join_usage: str = "Command error: Usage: /join <player_name>"
    server_first: str = "Command error: Connect to a server first with /server <server>"
    room_first_connect: str = "Command error: Choose a room first with /connect or /create."
    room_url_required: str = "Command error: /server requires a ws:// or wss:// URL."
    room_name_required: str = "Command error: Room name is required."
    not_connected: str = "Command error: Not connected to a server."
    room_first: str = "Command error: Connect to a room first with /connect <room>."
    join_first: str = "Command error: Join the game first with /join <player_name>."
    connect_first: str = "Command error: Connect first."

    # Status updates
    connected_choose_room: str = (
        "Connected to server. Choose a room: /connect <room> or /create <room>"
    )
    disconnecting: str = "Disconnecting from server..."
    disconnected: str = "Disconnected from server. Use /server <server> to connect again."
    left_game: str = "Left the game. You are now spectating this room."
    waiting_response: str = "Waiting for server response..."
    select_server_hint: str = "Select a server with Up/Down, then press Enter."

    # Dynamic templates
    join_failed: str = "Join failed: {error}"
    server_connect_failed: str = "Server connect failed: {error}"
    room_command_failed: str = "Room command failed: {error}"
    send_failed: str = "Error: Send failed: {error}"
    disconnected_error: str = "Disconnected: {error}"
    parse_error: str = "Command error: {error}. Try /help."
    no_server_history: str = "Command error: No server history. Usage: {usage}"

    # Local play validation
    play_requires_positive_number: str = (
        "Command error: {token} requires a positive card number. Example: {token} 3"
    )
    play_out_of_range: str = "Illegal play: card {number} is out of range for your current hand."
    play_card_mismatch: str = (
        "Illegal play: {card} does not match current color {color} or top card {top}."
    )
    play_wild_requires_color: str = (
        "Illegal play: wild cards require a color. Example: {token} 1 red"
    )

    # Server error translations
    server_illegal_play: str = (
        "Illegal play: card does not match current color {color} or top card {top}."
    )
    server_wild_needs_color: str = "Illegal play: wild cards require a color. Example: /play 1 red"
    server_wild_draw_four_restricted: str = (
        "Illegal play: Wild Draw Four only works when you have no card matching current "
        "color {color}."
    )
    server_invalid_selection: str = (
        "Illegal play: that card number is not valid for your current hand."
    )
    server_error_fallback: str = "Error: {message}"


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
    triggers_server_wait: bool = True

    @property
    def token(self) -> str:
        return f"/{self.name}"


class Commands:
    """Canonical slash-command specs, accessed as Commands.PLAY etc."""

    CONNECT = CommandSpec(
        "connect", "/connect <room>", min_args=1, max_args=1, trailing_space_completion=True
    )
    SERVER = CommandSpec("server", "/server <server>", max_args=1, trailing_space_completion=True)
    JOIN = CommandSpec(
        "join", "/join <player_name>", min_args=1, max_args=1, trailing_space_completion=True
    )
    CREATE = CommandSpec(
        "create", "/create <room>", min_args=1, max_args=1, trailing_space_completion=True
    )
    START = CommandSpec("start", "/start")
    PLAY = CommandSpec(
        "play", "/play <n> [color]", min_args=1, max_args=2, trailing_space_completion=True
    )
    DRAW = CommandSpec("draw", "/draw")
    PASS = CommandSpec("pass", "/pass")
    UNO = CommandSpec("uno", "/uno")
    EXIT_GAME = CommandSpec("exit_game", "/exit_game")
    EXIT_ROOM = CommandSpec("exit_room", "/exit_room")
    HELP = CommandSpec("help", "/help", triggers_server_wait=False)
    EXIT_SERVER = CommandSpec("exit_server", "/exit_server", triggers_server_wait=False)
    EXIT = CommandSpec("exit", "/exit", triggers_server_wait=False)


COMMAND_SPECS_BY_NAME: Dict[str, CommandSpec] = {
    spec.name: spec for spec in vars(Commands).values() if isinstance(spec, CommandSpec)
}

SERVER_SELECTION_COMMANDS: tuple[CommandSpec, ...] = (
    Commands.SERVER,
    Commands.HELP,
    Commands.EXIT,
)
ROOM_SELECTION_COMMANDS: tuple[CommandSpec, ...] = (
    Commands.CONNECT,
    Commands.CREATE,
    Commands.HELP,
    Commands.EXIT_SERVER,
    Commands.EXIT,
)
ROOM_EXIT_COMMANDS: tuple[CommandSpec, ...] = (
    Commands.HELP,
    Commands.EXIT_ROOM,
    Commands.EXIT_SERVER,
    Commands.EXIT,
)
JOINED_EXIT_COMMANDS: tuple[CommandSpec, ...] = (
    Commands.HELP,
    Commands.EXIT_GAME,
    Commands.EXIT_ROOM,
    Commands.EXIT_SERVER,
    Commands.EXIT,
)
PLAYER_JOIN_COMMANDS: tuple[CommandSpec, ...] = (Commands.JOIN, *ROOM_EXIT_COMMANDS)

VALID_PLAY_COLORS = tuple(color.value for color in Color)


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

    if len(args) < spec.min_args or len(args) > spec.max_args:
        raise CommandError(f"Usage: {spec.template}")

    if spec is Commands.PLAY:
        if not args[0].isdigit():
            raise CommandError(f"{Commands.PLAY.token} requires a numeric card index.")
        if len(args) == 2 and args[1].lower() not in VALID_PLAY_COLORS:
            raise CommandError(
                f"{Commands.PLAY.token} color must be one of: {', '.join(VALID_PLAY_COLORS)}."
            )

    return ParsedCommand(name=name, args=args)


def derive_available_commands(
    state: GameSnapshot,
    *,
    connected: bool,
    room_selected: bool,
    joined: bool,
    uno_armed: bool,
) -> List[str]:
    return [
        spec.template
        for spec in _derive_available_specs(
            state,
            connected=connected,
            room_selected=room_selected,
            joined=joined,
            uno_armed=uno_armed,
        )
    ]


def _derive_available_specs(
    state: GameSnapshot,
    *,
    connected: bool,
    room_selected: bool,
    joined: bool,
    uno_armed: bool,
) -> List[CommandSpec]:
    if not connected:
        return list(SERVER_SELECTION_COMMANDS)

    if not room_selected:
        return list(ROOM_SELECTION_COMMANDS)

    if not joined:
        return list(PLAYER_JOIN_COMMANDS)

    if state.finished or not state.started:
        return _with_optional_start(state)
    if not state.your_turn:
        return list(JOINED_EXIT_COMMANDS)

    specs: List[CommandSpec] = [Commands.PLAY]
    if state.can_draw:
        specs.append(Commands.DRAW)
    if state.can_pass:
        specs.append(Commands.PASS)
    if state.uno_hint or uno_armed:
        specs.append(Commands.UNO)
    specs.extend(JOINED_EXIT_COMMANDS)
    return specs


def _with_optional_start(state: GameSnapshot) -> List[CommandSpec]:
    """Return lobby/finished commands, optionally prefixed with host start."""
    specs = list(JOINED_EXIT_COMMANDS)
    if state.can_start:
        specs.insert(0, Commands.START)
    return specs


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

    state: GameSnapshot
    player_id: Optional[str]
    selected_room_name: Optional[str]
    preferred_name: str
    say_uno_next: bool
    api: Any
    rooms: List[Dict[str, Any]]
    server_history: List[str]

    async def connect_server(self, url: str) -> None: ...
    async def join_room(self, name: str) -> None: ...
    async def create_room(self, name: str) -> None: ...
    async def connect(
        self, player_name: Optional[str] = None, url: Optional[str] = None
    ) -> None: ...
    async def send(self, kind: ClientMsg, **payload: Any) -> None: ...
    async def exit_client(self) -> None: ...
    async def exit_server(self) -> None: ...
    async def exit_game(self) -> None: ...
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
        if self.server_history_active and raw.strip() in {"", Commands.SERVER.token}:
            await self.connect_selected_server_history()
            return

        self.clear_feedback()

        try:
            command = parse_command(raw)
        except CommandError as exc:
            self.set_feedback(CommandMessages.parse_error.format(error=exc))
            return

        await self.dispatch(command)

    async def dispatch(self, command: ParsedCommand) -> None:
        """Execute a parsed command while preserving the existing render/update hooks."""
        from tuno.client.actions import dispatch_command

        spec = COMMAND_SPECS_BY_NAME[command.name]
        is_bare_server = spec is Commands.SERVER and not command.args
        previous_uno_state = self.host.say_uno_next

        if spec.triggers_server_wait and not is_bare_server:
            self.set_pending_server_response()

        if is_bare_server:
            self.show_server_history()
        else:
            self.server_history_active = False
            self.host.say_uno_next = await dispatch_command(
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
                exit_server=self.host.exit_server,
                exit_game=self.host.exit_game,
                set_command_feedback=self.set_feedback,
                render_state=self.host.render_state,
            )

        if spec is Commands.HELP or (
            spec is Commands.UNO and self.host.say_uno_next != previous_uno_state
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
        self.command_feedback_message = CommandMessages.waiting_response
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
            card_command_token=Commands.PLAY.token,
            connect_command_token=Commands.CONNECT.token,
            command_template_candidate=command_template_candidate,
            valid_play_colors=VALID_PLAY_COLORS,
            hand=my_hand(self.host.state),
            rooms=self.host.rooms,
            current_color=self.host.state.current_color,
            top_card=self.host.state.top_card or None,
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
            and not matches_command_token(raw.strip(), Commands.SERVER)
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
            self.set_feedback(
                CommandMessages.no_server_history.format(usage=Commands.SERVER.template)
            )
            return

        self.server_history_active = True

        self.completion_state = CompletionState()
        command_input = self.host.query_one("#command-input", Input)
        command_input.value = f"{Commands.SERVER.token} "
        command_input.cursor_position = len(command_input.value)
        command_input.focus()

        self.set_feedback(CommandMessages.select_server_hint)

    async def connect_selected_server_history(self) -> None:
        """Connect to the currently selected server history entry."""
        candidates = self._server_history_candidates("") or []
        if not candidates:
            self.server_history_active = False
            self.set_feedback(
                CommandMessages.no_server_history.format(usage=Commands.SERVER.template)
            )
            return

        index = min(self.completion_state.suggestion_index, len(candidates) - 1)
        target = candidates[index]["insert"].removeprefix(f"{Commands.SERVER.token} ").strip()
        self.server_history_active = False
        self.completion_state = CompletionState()
        await self.host.connect_server(target)

    def _server_history_candidates(self, raw: str) -> List[Dict[str, str]] | None:
        """Return server-history candidates when the command bar is in server mode."""
        text = raw.strip()
        if not self.server_history_active and not matches_command_token(text, Commands.SERVER):
            return None

        if matches_command_token(text, Commands.SERVER):
            parts = text.split(maxsplit=1)
            if len(parts) == 1 and not (raw.endswith(" ") or self.server_history_active):
                return None
            prefix = "" if self.server_history_active else parts[1] if len(parts) == 2 else ""
        elif self.server_history_active and not text:
            prefix = ""
        else:
            return None

        return [
            {"insert": f"{Commands.SERVER.token} {url}", "display": url}
            for url in self.host.server_history
            if url.startswith(prefix)
        ]

    def _default_meta_text(self) -> str:
        if self.host.api is None:
            return f"Connect to a server: {Commands.SERVER.template}"
        if self.host.selected_room_name is None:
            return f"Choose a room: {Commands.CONNECT.template} or {Commands.CREATE.template}"
        return f"Join the game: {Commands.JOIN.template}"
