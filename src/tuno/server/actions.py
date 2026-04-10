"""Shared action application helpers for server runtimes."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from tuno.core.game import GameError, GameState


@dataclass(frozen=True)
class ActionResult:
    """Return value describing how a server action changed connection ownership."""

    player_id: Optional[str]
    welcome_player_id: Optional[str] = None


def apply_action(state: GameState, player_id: Optional[str], payload: dict) -> ActionResult:
    """Apply one validated protocol action to the authoritative game state."""
    kind = payload["type"]

    if kind == "join":
        if player_id:
            raise GameError("You already joined.")
        joined_player_id = state.add_player(payload.get("name", "Player"))
        return ActionResult(player_id=joined_player_id, welcome_player_id=joined_player_id)

    if kind == "start":
        _require_joined(player_id)
        state.start(player_id)
        return ActionResult(player_id=player_id)

    if kind == "play_card":
        _require_joined(player_id)
        state.play_card(
            player_id,
            int(payload.get("hand_index", -1)),
            chosen_color=payload.get("chosen_color"),
            say_uno=bool(payload.get("say_uno", False)),
        )
        return ActionResult(player_id=player_id)

    if kind == "draw_card":
        _require_joined(player_id)
        state.draw_card(player_id)
        return ActionResult(player_id=player_id)

    if kind == "pass_turn":
        _require_joined(player_id)
        state.pass_turn(player_id)
        return ActionResult(player_id=player_id)

    if kind == "leave":
        if player_id:
            state.remove_player(player_id)
        return ActionResult(player_id=None)

    if kind == "set_uno":
        _require_joined(player_id)
        state.set_uno_intent(player_id, bool(payload.get("armed", False)))
        return ActionResult(player_id=player_id)

    raise GameError("Unknown action.")


def _require_joined(player_id: Optional[str]) -> None:
    """Raise a consistent error when an action requires a joined player."""
    if not player_id:
        raise GameError("Join first.")
