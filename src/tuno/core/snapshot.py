"""Snapshot helpers that shape authoritative game state for client consumption."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field, fields
from typing import TYPE_CHECKING, Any, Mapping, Optional

if TYPE_CHECKING:
    from tuno.core.game import GameState

from tuno.core.game_storage import public_player_payload, serialize_game

SNAPSHOT_GAME_KEYS = (
    "started",
    "finished",
    "winner_id",
    "status_message",
    "current_color",
    "recent_events",
    "discard_pile",
)


@dataclass(frozen=True)
class GameSnapshot:
    """Client-facing game snapshot. Single source of truth for state keys."""

    started: bool = False
    finished: bool = False
    winner_id: str | None = None
    status_message: str = ""
    current_color: str | None = None
    recent_events: list[str] = field(default_factory=list)
    top_card: dict[str, Any] | None = None
    players: list[dict[str, Any]] = field(default_factory=list)
    your_player_id: str | None = None
    host_player_id: str | None = None
    current_player_id: str | None = None
    current_player_name: str | None = None
    your_turn: bool = False
    can_start: bool = False
    can_draw: bool = False
    can_pass: bool = False
    uno_hint: bool = False
    required_wild_color: bool = False

    def to_dict(self) -> dict[str, Any]:
        """Serialize for JSON wire transport. Field order matches dataclass declaration."""
        return asdict(self)

    @classmethod
    def from_dict(cls, raw: Mapping[str, Any] | GameSnapshot | None) -> "GameSnapshot":
        """Build from a wire/raw payload, tolerating unknown keys and missing fields."""
        if isinstance(raw, cls):
            return raw
        if not isinstance(raw, Mapping):
            return cls()

        known = {f.name for f in fields(cls)}
        return cls(**{k: v for k, v in raw.items() if k in known})


def build_snapshot(game: "GameState", player_id: Optional[str]) -> GameSnapshot:
    """Build the client-facing snapshot for one connected player."""
    from tuno.core.game import MIN_PLAYERS

    snapshot_payload = serialize_game(game, SNAPSHOT_GAME_KEYS)
    discard_pile = snapshot_payload.pop("discard_pile")

    current_player = game.current_player
    players_payload = [
        public_player_payload(player, is_self=(player.player_id == player_id))
        for player in game.players
    ]
    me = next((player for player in game.players if player.player_id == player_id), None)

    return GameSnapshot(
        started=snapshot_payload["started"],
        finished=snapshot_payload["finished"],
        winner_id=snapshot_payload["winner_id"],
        status_message=snapshot_payload["status_message"],
        current_color=snapshot_payload["current_color"],
        recent_events=snapshot_payload["recent_events"],
        top_card=discard_pile[-1] if discard_pile else None,
        players=players_payload,
        your_player_id=player_id,
        host_player_id=game.players[0].player_id if game.players else None,
        current_player_id=current_player.player_id if current_player else None,
        current_player_name=current_player.name if current_player else None,
        your_turn=bool(
            current_player and current_player.player_id == player_id and not game.finished
        ),
        can_start=((not game.started) or game.finished)
        and len(game.players) >= MIN_PLAYERS
        and bool(game.players and player_id == game.players[0].player_id),
        can_draw=bool(
            current_player
            and current_player.player_id == player_id
            and game.started
            and not game.finished
        ),
        can_pass=bool(
            current_player
            and current_player.player_id == player_id
            and game.has_drawn_this_turn
            and not game.finished
        ),
        uno_hint=bool(me and len(me.hand) == 2),
        required_wild_color=bool(
            current_player and current_player.player_id == player_id and game.started
        ),
    )
