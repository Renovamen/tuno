"""Command and action orchestration helpers."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Dict, Optional

from tuno.client.state import my_hand
from tuno.client.tui import commands as command_defs
from tuno.client.tui.commands import COMMAND_MESSAGES, PLAY_COMMAND, ParsedCommand
from tuno.core.cards import Card, Color
from tuno.core.snapshot import GameSnapshot

ConnectFn = Callable[[Optional[str], Optional[str]], Awaitable[None]]
ConnectServerFn = Callable[[str], Awaitable[None]]
RoomFn = Callable[[str], Awaitable[None]]
SendFn = Callable[[str], Awaitable[None]]
ExitFn = Callable[[], Awaitable[None]]
ExitServerFn = Callable[[], Awaitable[None]]
ExitGameFn = Callable[[], Awaitable[None]]
FeedbackFn = Callable[[str], None]
RenderFn = Callable[[], None]


@dataclass(frozen=True)
class CommandDispatchContext:
    preferred_name: str
    say_uno_next: bool
    state: GameSnapshot
    connect: ConnectFn
    connect_server: ConnectServerFn
    join_room: RoomFn
    create_room: RoomFn
    send: Callable[..., Awaitable[None]]
    exit_client: ExitFn
    exit_server: ExitServerFn
    exit_game: ExitGameFn
    set_command_feedback: FeedbackFn
    render_state: RenderFn


CommandHandler = Callable[["ParsedCommand", CommandDispatchContext], Awaitable[bool]]


async def dispatch_command(
    command: ParsedCommand,
    *,
    preferred_name: str,
    say_uno_next: bool,
    state: GameSnapshot,
    connect: ConnectFn,
    connect_server: ConnectServerFn,
    join_room: RoomFn,
    create_room: RoomFn,
    send: Callable[..., Awaitable[None]],
    exit_client: ExitFn,
    exit_server: ExitServerFn,
    exit_game: ExitGameFn,
    set_command_feedback: FeedbackFn,
    render_state: RenderFn,
) -> bool:
    """Execute a parsed command and return the updated UNO-arm state."""
    context = CommandDispatchContext(
        preferred_name=preferred_name,
        say_uno_next=say_uno_next,
        state=state,
        connect=connect,
        connect_server=connect_server,
        join_room=join_room,
        create_room=create_room,
        send=send,
        exit_client=exit_client,
        exit_server=exit_server,
        exit_game=exit_game,
        set_command_feedback=set_command_feedback,
        render_state=render_state,
    )
    handlers: Dict[Any, CommandHandler] = {
        command_defs.SERVER_COMMAND: _dispatch_server,
        command_defs.CONNECT_COMMAND: _dispatch_connect_room,
        command_defs.CREATE_ROOM_COMMAND: _dispatch_create_room,
        command_defs.JOIN_PLAYER_COMMAND: _dispatch_join_player,
        command_defs.START_COMMAND: _dispatch_start,
        command_defs.PLAY_COMMAND: _dispatch_play,
        command_defs.DRAW_COMMAND: _dispatch_draw,
        command_defs.PASS_COMMAND: _dispatch_pass,
        command_defs.UNO_COMMAND: _dispatch_uno,
        command_defs.EXIT_GAME_COMMAND: _dispatch_exit_game,
        command_defs.EXIT_ROOM_COMMAND: _dispatch_exit_room,
        command_defs.HELP_COMMAND: _dispatch_help,
        command_defs.EXIT_SERVER_COMMAND: _dispatch_exit_server,
        command_defs.EXIT_COMMAND: _dispatch_exit,
    }

    spec = command_defs.COMMAND_SPECS_BY_NAME.get(command.name)
    handler = handlers.get(spec, _dispatch_noop)
    return await handler(command, context)


async def _dispatch_server(command: ParsedCommand, context: CommandDispatchContext) -> bool:
    if command.args:
        await context.connect_server(command.args[0])
    return context.say_uno_next


async def _dispatch_connect_room(command: ParsedCommand, context: CommandDispatchContext) -> bool:
    await context.join_room(command.args[0])
    return context.say_uno_next


async def _dispatch_create_room(command: ParsedCommand, context: CommandDispatchContext) -> bool:
    await context.create_room(command.args[0])
    return context.say_uno_next


async def _dispatch_join_player(command: ParsedCommand, context: CommandDispatchContext) -> bool:
    await context.connect(player_name=command.args[0])
    return context.say_uno_next


async def _dispatch_start(command: ParsedCommand, context: CommandDispatchContext) -> bool:
    await context.send("start")
    return context.say_uno_next


async def _dispatch_play(command: ParsedCommand, context: CommandDispatchContext) -> bool:
    chosen_color = command.args[1].lower() if len(command.args) == 2 else None
    return await play_card_by_number(
        int(command.args[0]),
        state=context.state,
        chosen_color=chosen_color,
        say_uno_next=context.say_uno_next,
        send=context.send,
        set_command_feedback=context.set_command_feedback,
        render_state=context.render_state,
        play_command_token=PLAY_COMMAND.token,
    )


async def _dispatch_draw(command: ParsedCommand, context: CommandDispatchContext) -> bool:
    await context.send("draw_card")
    return context.say_uno_next


async def _dispatch_pass(command: ParsedCommand, context: CommandDispatchContext) -> bool:
    await context.send("pass_turn")
    return context.say_uno_next


async def _dispatch_uno(command: ParsedCommand, context: CommandDispatchContext) -> bool:
    if not context.say_uno_next:
        await context.send("set_uno", armed=True)
    return True


async def _dispatch_exit_game(command: ParsedCommand, context: CommandDispatchContext) -> bool:
    await context.exit_game()
    return False


async def _dispatch_exit_room(command: ParsedCommand, context: CommandDispatchContext) -> bool:
    await context.send("exit_room")
    return False


async def _dispatch_help(command: ParsedCommand, context: CommandDispatchContext) -> bool:
    return context.say_uno_next


async def _dispatch_exit_server(command: ParsedCommand, context: CommandDispatchContext) -> bool:
    await context.exit_server()
    return False


async def _dispatch_exit(command: ParsedCommand, context: CommandDispatchContext) -> bool:
    await context.exit_client()
    return context.say_uno_next


async def _dispatch_noop(command: ParsedCommand, context: CommandDispatchContext) -> bool:
    return context.say_uno_next


async def play_card_by_number(
    display_number: int,
    *,
    state: GameSnapshot,
    chosen_color: Optional[str],
    say_uno_next: bool,
    send: Callable[..., Awaitable[None]],
    set_command_feedback: FeedbackFn,
    render_state: RenderFn,
    play_command_token: Optional[str] = None,
) -> bool:
    """Validate a displayed hand index locally and send the play request if legal."""
    play_command_token = _play_command_token(play_command_token)
    if not _validate_positive_display_number(
        display_number, play_command_token, set_command_feedback
    ):
        return say_uno_next

    card_selection = _select_displayed_card(display_number, state, set_command_feedback)
    if card_selection is None:
        return say_uno_next

    hand_index, card = card_selection
    if not _validate_play_choice(
        card, state, chosen_color, play_command_token, set_command_feedback
    ):
        return say_uno_next

    await send(
        "play_card",
        hand_index=hand_index,
        chosen_color=chosen_color,
        say_uno=say_uno_next,
    )
    render_state()

    return False


def _play_command_token(play_command_token: Optional[str]) -> str:
    if play_command_token is not None:
        return play_command_token
    return PLAY_COMMAND.token


def _validate_positive_display_number(
    display_number: int, play_command_token: str, set_command_feedback: FeedbackFn
) -> bool:
    if display_number > 0:
        return True

    set_command_feedback(
        COMMAND_MESSAGES.play_requires_positive_number.format(token=play_command_token)
    )
    return False


def _select_displayed_card(
    display_number: int, state: GameSnapshot, set_command_feedback: FeedbackFn
) -> tuple[int, Dict[str, Any]] | None:
    player_hand = my_hand(state)
    hand_index = display_number - 1
    if hand_index < len(player_hand):
        return hand_index, player_hand[hand_index]

    set_command_feedback(COMMAND_MESSAGES.play_out_of_range.format(number=display_number))
    return None


def _validate_play_choice(
    card: Dict[str, Any],
    state: GameSnapshot,
    chosen_color: Optional[str],
    play_command_token: str,
    set_command_feedback: FeedbackFn,
) -> bool:
    if Card.from_dict(card).is_wild():
        return _validate_wild_choice(chosen_color, play_command_token, set_command_feedback)

    current_color = state.current_color
    top_card = state.top_card or {}
    if (
        current_color
        and top_card
        and card.get("color") != current_color
        and card.get("rank") != top_card.get("rank")
    ):
        set_command_feedback(
            COMMAND_MESSAGES.play_card_mismatch.format(
                card=Card.from_dict(card).short_label(),
                color=current_color,
                top=Card.from_dict(top_card).short_label(),
            )
        )
        return False
    return True


def _validate_wild_choice(
    chosen_color: Optional[str], play_command_token: str, set_command_feedback: FeedbackFn
) -> bool:
    if Color.parse(chosen_color) is not None:
        return True

    set_command_feedback(COMMAND_MESSAGES.play_wild_requires_color.format(token=play_command_token))
    return False
