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
    top_card = state.top_card or {}
    top_label = Card.from_dict(top_card).short_label() if top_card else "-"
    current_color = state.current_color or "-"

    match code:
        case "illegal_play":
            return (
                f"Illegal play: card does not match current color {current_color} "
                f"or top card {top_label}."
            )
        case "wild_needs_color":
            return "Illegal play: wild cards require a color. Example: /play 1 red"
        case "wild_draw_four_restricted":
            return (
                "Illegal play: Wild Draw Four only works when you have no card matching current "
                f"color {current_color}."
            )
        case "invalid_selection":
            return "Illegal play: that card number is not valid for your current hand."
        case _:
            return f"Error: {message}"
