from __future__ import annotations

import unittest

from tuno.core.cards import Card
from tuno.core.game import GameState
from tuno.core.game_storage import deserialize_game, serialize_game

ROUND_TRIP_STORAGE_KEYS = (
    "seed",
    "players",
    "started",
    "finished",
    "winner_id",
    "current_player_index",
    "direction",
    "current_color",
    "status_message",
    "recent_events",
    "has_drawn_this_turn",
    "draw_pile",
    "discard_pile",
    "drawn_card",
    "next_player_serial",
    "rng_state",
)


class GameStorageTests(unittest.TestCase):
    """Cover storage payload round-trips for authoritative game state."""

    def test_serialize_game_returns_only_requested_keys(self) -> None:
        """Let callers choose the payload shape they need."""
        game = GameState(seed=11)
        alice = game.add_player("alice")
        game.add_player("bob")
        game.start(alice)

        payload = serialize_game(game, ("started", "current_color", "discard_pile"))

        self.assertEqual(set(payload), {"started", "current_color", "discard_pile"})
        self.assertTrue(payload["started"])
        self.assertEqual(payload["current_color"], game.current_color)
        self.assertEqual(payload["discard_pile"], [game.top_card.to_dict()])

    def test_serialize_round_trip_preserves_turn_and_private_cards(self) -> None:
        """Restore a saved game with enough private state to keep playing."""
        game = GameState(seed=11)
        alice = game.add_player("alice")
        bob = game.add_player("bob")
        game.start(alice)
        game.players[0].hand = [Card("red", "5")]
        game.players[1].hand = [Card("blue", "2")]
        game._deck.discard_pile = [Card("red", "1")]
        game.current_color = "red"
        game.current_player_index = 0

        restored = deserialize_game(
            serialize_game(game, ROUND_TRIP_STORAGE_KEYS), ROUND_TRIP_STORAGE_KEYS
        )

        self.assertEqual(restored.seed, game.seed)
        self.assertEqual(restored.current_player.player_id, alice)
        self.assertEqual(restored.players[0].hand, [Card("red", "5")])
        self.assertEqual(restored.players[1].hand, [Card("blue", "2")])

        restored.play_card(alice, 0, say_uno=True)

        self.assertTrue(restored.finished)
        self.assertEqual(restored.winner_id, alice)
        self.assertEqual(restored.players[1].player_id, bob)


if __name__ == "__main__":
    unittest.main()
