from __future__ import annotations

import unittest

from tuno.core.cards import Card
from tuno.core.game import GameState
from tuno.core.snapshot import build_snapshot


class GameSnapshotTests(unittest.TestCase):
    """Cover extracted snapshot shaping helpers for client-facing state."""

    def test_snapshot_marks_host_and_turn_flags(self) -> None:
        """Expose host, current player, and command-policy booleans consistently."""
        game = GameState(seed=7)
        alice = game.add_player("alice")
        bob = game.add_player("bob")
        game.start(alice)

        snapshot = build_snapshot(game, alice)

        self.assertEqual(snapshot["host_player_id"], alice)
        self.assertEqual(snapshot["current_player_id"], alice)
        self.assertTrue(snapshot["your_turn"])
        self.assertTrue(snapshot["can_draw"])
        self.assertFalse(snapshot["can_pass"])
        self.assertEqual(snapshot["players"][0]["player_id"], alice)
        self.assertEqual(snapshot["players"][1]["player_id"], bob)

    def test_snapshot_reenables_can_start_for_host_after_round_finishes(self) -> None:
        """Expose restart capability to the host after a round winner is declared."""
        game = GameState(seed=7)
        alice = game.add_player("alice")
        game.add_player("bob")
        game.start(alice)
        game.players[0].hand = [Card("red", "5")]
        game.players[1].hand = [Card("blue", "2")]
        game.discard_pile = [Card("red", "1")]
        game.current_color = "red"
        game.current_player_index = 0
        game.play_card(alice, 0, say_uno=True)

        snapshot = build_snapshot(game, alice)

        self.assertTrue(snapshot["finished"])
        self.assertTrue(snapshot["can_start"])
