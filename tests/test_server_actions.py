from __future__ import annotations

import unittest

from tuno.core.game import GameError, GameState
from tuno.server.actions import apply_action


class ServerActionTests(unittest.TestCase):
    """Cover shared server-side action dispatch semantics."""

    def test_join_returns_new_player_id_and_welcome_payload(self) -> None:
        """Join assigns a new player id and marks it for welcome delivery."""
        game = GameState(seed=11)

        result = apply_action(game, None, {"type": "join", "name": "alice"})

        self.assertEqual(result.player_id, "p0001")
        self.assertEqual(result.welcome_player_id, "p0001")
        self.assertEqual(game.players[0].name, "alice")

    def test_leave_clears_connection_player_id(self) -> None:
        """Leave removes the player and clears connection ownership."""
        game = GameState(seed=11)
        player_id = game.add_player("alice")

        result = apply_action(game, player_id, {"type": "leave"})

        self.assertIsNone(result.player_id)
        self.assertEqual(game.players, [])

    def test_actions_requiring_join_raise_consistent_error(self) -> None:
        """Non-join actions reject anonymous connections before touching game state."""
        game = GameState(seed=11)

        with self.assertRaises(GameError) as exc_info:
            apply_action(game, None, {"type": "start"})

        self.assertEqual(str(exc_info.exception), "Join first.")

    def test_set_uno_records_recent_event_without_changing_connection_owner(self) -> None:
        """UNO toggles should update game state while preserving connection ownership."""
        game = GameState(seed=11)
        alice = game.add_player("alice")
        game.add_player("bob")
        game.start(alice)

        result = apply_action(game, alice, {"type": "set_uno", "armed": True})

        self.assertEqual(result.player_id, alice)
        self.assertIsNone(result.welcome_player_id)
        self.assertIn("armed UNO", game.recent_events[-1])
