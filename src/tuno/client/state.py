"""Helpers for reading and presenting client game-state snapshots."""

from __future__ import annotations

from typing import Any, Dict, List

from tuno.core.cards import Card
from tuno.core.snapshot import GameSnapshot


def my_hand(state: GameSnapshot) -> List[Dict[str, Any]]:
    """Return the current player's visible hand from a client snapshot."""
    for player in state.players:
        if player.get("player_id") == state.your_player_id:
            return list(player.get("hand", []))
    return []


def format_server_error(state: GameSnapshot, message: str, code: str = "") -> str:
    """Translate server error payloads into client-facing, context-rich text."""
    from tuno.client.tui.commands import COMMAND_MESSAGES

    top_card = state.top_card or {}
    top_label = Card.from_dict(top_card).short_label() if top_card else "-"
    current_color = state.current_color or "-"

    match code:
        case "illegal_play":
            return COMMAND_MESSAGES.server_illegal_play.format(color=current_color, top=top_label)
        case "wild_needs_color":
            return COMMAND_MESSAGES.server_wild_needs_color
        case "wild_draw_four_restricted":
            return COMMAND_MESSAGES.server_wild_draw_four_restricted.format(color=current_color)
        case "invalid_selection":
            return COMMAND_MESSAGES.server_invalid_selection
        case _:
            return COMMAND_MESSAGES.server_error_fallback.format(message=message)
