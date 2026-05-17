from __future__ import annotations

import unittest

from tuno.client.state import format_server_error, my_hand
from tuno.core.snapshot import GameSnapshot


class ClientStateTests(unittest.TestCase):
    """Cover client snapshot helper behavior."""

    def test_my_hand_returns_current_players_hand_copy(self) -> None:
        hand = [{"rank": "7", "color": "green"}]
        state = GameSnapshot(
            your_player_id="p1",
            players=[
                {"player_id": "p1", "hand": hand},
                {"player_id": "p2", "hand": [{"rank": "2", "color": "red"}]},
            ],
        )

        result = my_hand(state)

        self.assertEqual(result, hand)
        self.assertIsNot(result, hand)

    def test_my_hand_returns_empty_list_when_player_is_missing(self) -> None:
        self.assertEqual(my_hand(GameSnapshot(your_player_id="p1", players=[])), [])

    def test_format_server_error_uses_snapshot_context_for_illegal_play(self) -> None:
        message = format_server_error(
            GameSnapshot(current_color="red", top_card={"short": "R:5"}),
            "That card cannot be played.",
            "illegal_play",
        )

        self.assertEqual(
            message,
            "Illegal play: card does not match current color red or top card R:5.",
        )

    def test_format_server_error_falls_back_to_server_message(self) -> None:
        self.assertEqual(
            format_server_error(GameSnapshot(), "Something failed.", "unknown_code"),
            "Error: Something failed.",
        )
