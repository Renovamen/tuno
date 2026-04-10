from __future__ import annotations

import unittest

from tuno.core.events import (
    disconnect_turn_passed,
    disconnect_wins_by_default,
    effect_drew_cards,
    forgot_uno,
    game_started,
    lobby_joined,
    lobby_waiting,
    played_card,
)


class GameEventTextTests(unittest.TestCase):
    """Cover extracted user-facing game event text helpers."""

    def test_lobby_events_use_expected_text(self) -> None:
        """Keep canonical lobby event wording stable."""
        self.assertEqual(lobby_waiting(), "Waiting for players.")
        self.assertIn("joined the lobby", lobby_joined("alice"))

    def test_disconnect_messages_cover_continue_and_default_win_cases(self) -> None:
        """Differentiate between continuing play and default-win disconnect outcomes."""
        self.assertIn("bob's turn", disconnect_turn_passed("alice", "bob"))
        self.assertIn("wins by default", disconnect_wins_by_default("alice", "bob"))

    def test_play_and_penalty_text_helpers_match_current_event_style(self) -> None:
        """Preserve the compact event wording used by recent activity rendering."""
        self.assertEqual(game_started(), "Game started.")
        self.assertIn("played", played_card("alice", "[bold red]R:5[/]"))
        self.assertIn("forgot UNO", forgot_uno("alice"))
        self.assertIn("drew 4", effect_drew_cards("bob", 4))
