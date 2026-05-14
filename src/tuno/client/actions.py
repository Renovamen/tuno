"""Command and action orchestration helpers."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Awaitable, Callable, Dict, Optional

from tuno.client.state import my_hand
from tuno.core.cards import WILD_RANKS

if TYPE_CHECKING:
    from tuno.client.tui.commands import ParsedCommand

ConnectFn = Callable[[Optional[str], Optional[str]], Awaitable[None]]
ConnectServerFn = Callable[[str], Awaitable[None]]
RoomFn = Callable[[str], Awaitable[None]]
SendFn = Callable[[str], Awaitable[None]]
ExitFn = Callable[[], Awaitable[None]]
FeedbackFn = Callable[[str], None]
RenderFn = Callable[[], None]


@dataclass(frozen=True)
class CommandDispatchContext:
    preferred_name: str
    say_uno_next: bool
    state: Dict[str, Any]
    connect: ConnectFn
    connect_server: ConnectServerFn
    join_room: RoomFn
    create_room: RoomFn
    send: Callable[..., Awaitable[None]]
    exit_client: ExitFn
    set_command_feedback: FeedbackFn
    render_state: RenderFn


CommandHandler = Callable[["ParsedCommand", CommandDispatchContext], Awaitable[bool]]


async def dispatch_command(
    command: ParsedCommand,
    *,
    preferred_name: str,
    say_uno_next: bool,
    state: Dict[str, Any],
    connect: ConnectFn,
    connect_server: ConnectServerFn,
    join_room: RoomFn,
    create_room: RoomFn,
    send: Callable[..., Awaitable[None]],
    exit_client: ExitFn,
    set_command_feedback: FeedbackFn,
    render_state: RenderFn,
) -> bool:
    """Execute a parsed command and return the updated UNO-arm state."""
    from tuno.client.tui import commands as command_defs

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
        command_defs.HELP_COMMAND: _dispatch_help,
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
    from tuno.client.tui.commands import PLAY_COMMAND

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


async def _dispatch_help(command: ParsedCommand, context: CommandDispatchContext) -> bool:
    return context.say_uno_next


async def _dispatch_exit(command: ParsedCommand, context: CommandDispatchContext) -> bool:
    await context.exit_client()
    return context.say_uno_next


async def _dispatch_noop(command: ParsedCommand, context: CommandDispatchContext) -> bool:
    return context.say_uno_next


async def play_card_by_number(
    display_number: int,
    *,
    state: Dict[str, Any],
    chosen_color: Optional[str],
    say_uno_next: bool,
    send: Callable[..., Awaitable[None]],
    set_command_feedback: FeedbackFn,
    render_state: RenderFn,
    play_command_token: Optional[str] = None,
) -> bool:
    """Validate a displayed hand index locally and send the play request if legal."""
    if play_command_token is None:
        from tuno.client.tui.commands import PLAY_COMMAND

        play_command_token = PLAY_COMMAND.token

    if display_number <= 0:
        set_command_feedback(
            f"Command error: {play_command_token} requires a positive card number. "
            f"Example: {play_command_token} 3"
        )
        return say_uno_next

    player_hand = my_hand(state)
    hand_index = display_number - 1
    if hand_index >= len(player_hand):
        set_command_feedback(
            f"Illegal play: card {display_number} is out of range for your current hand."
        )
        return say_uno_next

    card = player_hand[hand_index]
    if card.get("rank") in WILD_RANKS:
        if chosen_color is None:
            set_command_feedback(
                f"Illegal play: wild cards require a color. Example: {play_command_token} 1 red"
            )
            return say_uno_next
    else:
        current_color = state.get("current_color")
        top_card = state.get("top_card") or {}
        if (
            current_color
            and top_card
            and card.get("color") != current_color
            and card.get("rank") != top_card.get("rank")
        ):
            set_command_feedback(
                f"Illegal play: {card.get('short') or card.get('label')} does not match "
                f"current color {current_color} or top card "
                f"{top_card.get('short') or top_card.get('label')}."
            )
            return say_uno_next

    await send(
        "play_card",
        hand_index=hand_index,
        chosen_color=chosen_color,
        say_uno=say_uno_next,
    )
    render_state()

    return False
