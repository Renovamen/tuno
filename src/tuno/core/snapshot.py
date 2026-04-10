"""Snapshot helpers that shape authoritative game state for client consumption."""

from __future__ import annotations

from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from tuno.core.game import GameState


def build_snapshot(game: "GameState", player_id: Optional[str]) -> dict:
    """Build the client-facing snapshot for one connected player."""
    from tuno.core.game import MIN_PLAYERS

    current_player = game.current_player
    players_payload = [
        player.to_public_dict(is_self=(player.player_id == player_id)) for player in game.players
    ]
    me = next((player for player in game.players if player.player_id == player_id), None)

    return {
        "started": game.started,
        "finished": game.finished,
        "winner_id": game.winner_id,
        "status_message": game.status_message,
        "current_color": game.current_color,
        "top_card": game.top_card.to_dict() if game.top_card else None,
        "players": players_payload,
        "your_player_id": player_id,
        "host_player_id": game.players[0].player_id if game.players else None,
        "current_player_id": current_player.player_id if current_player else None,
        "current_player_name": current_player.name if current_player else None,
        "your_turn": bool(
            current_player and current_player.player_id == player_id and not game.finished
        ),
        "can_start": ((not game.started) or game.finished)
        and len(game.players) >= MIN_PLAYERS
        and bool(game.players and player_id == game.players[0].player_id),
        "can_draw": bool(
            current_player
            and current_player.player_id == player_id
            and game.started
            and not game.finished
        ),
        "can_pass": bool(
            current_player
            and current_player.player_id == player_id
            and game.has_drawn_this_turn
            and not game.finished
        ),
        "uno_hint": bool(me and len(me.hand) == 2),
        "required_wild_color": bool(
            current_player and current_player.player_id == player_id and game.started
        ),
        "recent_events": list(game.recent_events),
    }
