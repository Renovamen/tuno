"""Command and action orchestration helpers."""

from __future__ import annotations

from typing import Any, Awaitable, Callable, Dict, Optional

from tuno.client.commands import ParsedCommand
from tuno.client.completion import WILD_RANKS
from tuno.client.rendering import my_hand

ConnectFn = Callable[[Optional[str], Optional[str]], Awaitable[None]]
SendFn = Callable[[str], Awaitable[None]]
ExitFn = Callable[[], Awaitable[None]]
FeedbackFn = Callable[[str], None]
RenderFn = Callable[[], None]


async def dispatch_command(
    command: ParsedCommand,
    *,
    preferred_name: str,
    say_uno_next: bool,
    state: Dict[str, Any],
    connect: ConnectFn,
    send: Callable[..., Awaitable[None]],
    exit_client: ExitFn,
    set_command_feedback: FeedbackFn,
    render_state: RenderFn,
) -> bool:
    """Execute a parsed command and return the updated UNO-arm state."""
    if command.name == "connect":
        name = command.args[0] if command.args else preferred_name
        await connect(player_name=name or None)
        return say_uno_next
    if command.name == "start":
        await send("start")
        return say_uno_next
    if command.name == "play":
        chosen_color = command.args[1].lower() if len(command.args) == 2 else None
        return await play_card_by_number(
            int(command.args[0]),
            state=state,
            chosen_color=chosen_color,
            say_uno_next=say_uno_next,
            send=send,
            set_command_feedback=set_command_feedback,
            render_state=render_state,
        )
    if command.name == "draw":
        await send("draw_card")
        return say_uno_next
    if command.name == "pass":
        await send("pass_turn")
        return say_uno_next
    if command.name == "uno":
        if not say_uno_next:
            await send("set_uno", armed=True)
        return True
    if command.name == "help":
        return say_uno_next
    if command.name == "exit":
        await exit_client()
        return say_uno_next
    return say_uno_next


async def play_card_by_number(
    display_number: int,
    *,
    state: Dict[str, Any],
    chosen_color: Optional[str],
    say_uno_next: bool,
    send: Callable[..., Awaitable[None]],
    set_command_feedback: FeedbackFn,
    render_state: RenderFn,
) -> bool:
    """Validate a displayed hand index locally and send the play request if legal."""
    if display_number <= 0:
        set_command_feedback(
            "Command error: /play requires a positive card number. Example: /play 3"
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
            set_command_feedback("Illegal play: wild cards require a color. Example: /play 1 red")
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
