"""Storage payload codecs for authoritative game state."""

from __future__ import annotations

from typing import TYPE_CHECKING, Sequence

from tuno.core.cards import Card

if TYPE_CHECKING:
    from tuno.core.game import GameState, PlayerState

DECK_STORAGE_KEYS = ("draw_pile", "discard_pile")


def serialize_cards(cards: list[Card]) -> list[dict]:
    """Convert cards to their JSON-friendly protocol payloads."""
    return [card.to_dict() for card in cards]


def deserialize_cards(payload: list[dict]) -> list[Card]:
    """Rebuild cards from JSON-friendly protocol payloads."""
    return [Card.from_dict(card) for card in payload]


def public_player_payload(player: "PlayerState", is_self: bool) -> dict:
    """Serialize a player for client snapshots, hiding other players' hands."""
    payload = {
        "player_id": player.player_id,
        "name": player.name,
        "card_count": len(player.hand),
    }

    if is_self:
        payload["hand"] = serialize_cards(player.hand)

    return payload


def private_player_payload(player: "PlayerState") -> dict:
    """Serialize a player with private hand data for authoritative storage."""
    return {
        "player_id": player.player_id,
        "name": player.name,
        "hand": serialize_cards(player.hand),
    }


def serialize_game(game: "GameState", keys: Sequence[str]) -> dict:
    """Convert selected game state fields into a JSON-friendly payload."""
    return {key: _read_game_value(game, key) for key in keys}


def deserialize_game(payload: dict, keys: Sequence[str]) -> GameState:
    """Rebuild one room's game state from a storage payload."""
    from tuno.core.game import GameState

    game = GameState(seed=payload["seed"] if "seed" in payload else None)
    for key in keys:
        if key in payload:
            _write_game_value(game, key, payload[key])
    return game


def _read_game_value(game: "GameState", key: str):
    """Read one named game payload field from authoritative state."""
    if key == "seed":
        return game.seed
    if key == "players":
        return [private_player_payload(player) for player in game.players]
    if key in DECK_STORAGE_KEYS:
        return serialize_cards(getattr(game._deck, key))
    if key == "drawn_card":
        return game.drawn_card.to_dict() if game.drawn_card else None
    if key == "next_player_serial":
        return game._next_player_serial
    if key == "rng_state":
        return game._deck._rng.state

    return _copy_storage_value(getattr(game, key))


def _write_game_value(game: "GameState", key: str, value) -> None:
    """Restore one named game payload field onto authoritative state."""
    if key == "seed":
        game.seed = value
        return
    if key == "players":
        game.players = [_deserialize_player(player) for player in value]
        return
    if key in DECK_STORAGE_KEYS:
        setattr(game._deck, key, deserialize_cards(value))
        return
    if key == "drawn_card":
        game.drawn_card = Card.from_dict(value) if value else None
        return
    if key == "next_player_serial":
        game._next_player_serial = value
        return
    if key == "rng_state":
        game._deck._rng.state = value
        return

    setattr(game, key, _copy_storage_value(value))


def _copy_storage_value(value):
    """Avoid sharing mutable storage payload lists with live game state."""
    return list(value) if isinstance(value, list) else value


def _deserialize_player(payload: dict) -> "PlayerState":
    """Rebuild a player from the Worker storage shape."""
    from tuno.core.game import PlayerState

    return PlayerState(
        player_id=payload["player_id"],
        name=payload["name"],
        hand=deserialize_cards(payload.get("hand", [])),
    )
