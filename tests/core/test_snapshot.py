from __future__ import annotations

import unittest

from tuno.core.cards import Card
from tuno.core.game import GameState
from tuno.core.snapshot import GameSnapshot, build_snapshot


class GameSnapshotTests(unittest.TestCase):
    """Cover extracted snapshot shaping helpers for client-facing state."""

    def test_snapshot_marks_host_and_turn_flags(self) -> None:
        """Expose host, current player, and command-policy booleans consistently."""
        game = GameState(seed=7)
        alice = game.add_player("alice")
        bob = game.add_player("bob")
        game.start(alice)

        snapshot = build_snapshot(game, alice)

        self.assertEqual(snapshot.host_player_id, alice)
        self.assertEqual(snapshot.current_player_id, alice)
        self.assertTrue(snapshot.your_turn)
        self.assertTrue(snapshot.can_draw)
        self.assertFalse(snapshot.can_pass)
        self.assertEqual(snapshot.players[0]["player_id"], alice)
        self.assertEqual(snapshot.players[1]["player_id"], bob)

    def test_snapshot_blocks_second_draw_after_drawing_this_turn(self) -> None:
        """Disable `can_draw` once the active player has already drawn this turn."""
        game = GameState(seed=7)
        alice = game.add_player("alice")
        game.add_player("bob")
        game.start(alice)
        game.has_drawn_this_turn = True

        snapshot = build_snapshot(game, alice)

        self.assertFalse(snapshot.can_draw)

    def test_snapshot_reenables_can_start_for_host_after_round_finishes(self) -> None:
        """Expose restart capability to the host after a round winner is declared."""
        game = GameState(seed=7)
        alice = game.add_player("alice")
        game.add_player("bob")
        game.start(alice)
        game.players[0].hand = [Card("red", "5")]
        game.players[1].hand = [Card("blue", "2")]
        game._deck.discard_pile = [Card("red", "1")]
        game.current_color = "red"
        game.current_player_index = 0
        game.play_card(alice, 0, say_uno=True)

        snapshot = build_snapshot(game, alice)

        self.assertTrue(snapshot.finished)
        self.assertTrue(snapshot.can_start)

    def test_snapshot_round_trips_known_wire_fields(self) -> None:
        """Serialize and rehydrate the public snapshot payload shape."""
        snapshot = GameSnapshot(
            started=True,
            current_color="red",
            top_card={"rank": "5", "short": "R:5"},
            players=[{"player_id": "p1", "hand": [{"rank": "5", "color": "red"}]}],
        )
        payload = snapshot.to_dict()
        payload["unknown"] = "ignored"

        result = GameSnapshot.from_dict(payload)

        self.assertEqual(result, snapshot)
        self.assertIsNot(payload["players"], snapshot.players)

    def test_snapshot_from_dict_tolerates_empty_or_already_typed_payload(self) -> None:
        """Treat missing or already-normalized state payloads as stable snapshots."""
        snapshot = GameSnapshot(started=True)

        self.assertIs(GameSnapshot.from_dict(snapshot), snapshot)
        self.assertEqual(GameSnapshot.from_dict(None), GameSnapshot())
        self.assertEqual(GameSnapshot.from_dict([]), GameSnapshot())
