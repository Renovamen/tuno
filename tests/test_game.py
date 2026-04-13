from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from tuno.core.cards import Card, build_classic_deck
from tuno.core.game import GameError, GameState


class CardTests(unittest.TestCase):
    """Cover card/deck behavior owned by the game module tests."""

    def test_build_classic_deck_returns_cards(self) -> None:
        """Return concrete `Card` instances when building the classic deck."""
        deck = build_classic_deck()
        self.assertTrue(deck)
        self.assertTrue(all(isinstance(card, Card) for card in deck))


class GameStateTests(unittest.TestCase):
    """Cover rule enforcement and turn flow in `GameState`."""

    def make_started_game(self) -> GameState:
        """Create a deterministic two-player game that has already started."""
        game = GameState(seed=123)
        host_id = game.add_player("Alice")
        game.add_player("Bob")
        game.start(host_id)
        return game

    def test_start_deals_cards_and_sets_top_card(self) -> None:
        """Deal opening hands and initialize the discard state on start."""
        game = self.make_started_game()
        self.assertTrue(game.started)
        self.assertIsNotNone(game.top_card)
        self.assertIsNotNone(game.current_color)
        self.assertEqual(len(game.players), 2)
        self.assertTrue(all(len(player.hand) == 7 for player in game.players))

    def test_only_host_can_start(self) -> None:
        """Reject round start attempts from non-host players."""
        game = GameState(seed=456)
        game.add_player("Alice")
        bob_id = game.add_player("Bob")
        with self.assertRaises(GameError):
            game.start(bob_id)

    def test_wild_draw_four_requires_no_matching_color(self) -> None:
        """Block Wild Draw Four when the player still has a matching color."""
        game = self.make_started_game()
        alice = game.players[0]
        bob = game.players[1]
        alice.hand = [Card("red", "5"), Card(None, "wild_draw_four")]
        bob.hand = [Card("blue", "4")]
        game.discard_pile = [Card("red", "9")]
        game.current_color = "red"
        game.current_player_index = 0

        with self.assertRaises(GameError):
            game.play_card(alice.player_id, 1, chosen_color="green")

    def test_missing_uno_draws_two_penalty_cards(self) -> None:
        """Apply the UNO penalty immediately when a player goes to one card silently."""
        game = self.make_started_game()
        alice = game.players[0]
        bob = game.players[1]
        alice.hand = [Card("red", "5"), Card("blue", "7")]
        bob.hand = [Card("blue", "4"), Card("green", "2")]
        game.draw_pile = [Card("green", "1"), Card("yellow", "6"), Card("yellow", "2")]
        game.discard_pile = [Card("red", "9")]
        game.current_color = "red"
        game.current_player_index = 0

        game.play_card(alice.player_id, 0, say_uno=False)

        self.assertEqual(len(alice.hand), 3)
        self.assertIn("forgot UNO", game.status_message)
        self.assertEqual(game.current_player.player_id, bob.player_id)

    def test_draw_then_pass_advances_turn(self) -> None:
        """Allow a draw-then-pass flow and advance the turn correctly."""
        game = self.make_started_game()
        alice = game.players[0]
        bob = game.players[1]
        alice.hand = [Card("blue", "5")]
        bob.hand = [Card("green", "3")]
        game.draw_pile = [Card("yellow", "1"), Card("green", "2")]
        game.discard_pile = [Card("green", "9")]
        game.current_color = "green"
        game.current_player_index = 0

        game.draw_card(alice.player_id)
        self.assertTrue(game.has_drawn_this_turn)
        self.assertEqual(len(alice.hand), 2)

        game.pass_turn(alice.player_id)
        self.assertFalse(game.has_drawn_this_turn)
        self.assertEqual(game.current_player.player_id, bob.player_id)

    def test_reverse_with_two_players_passes_turn_to_the_other_player(self) -> None:
        """Treat reverse as a direction flip only, not a skip, in a two-player round."""
        game = self.make_started_game()
        alice = game.players[0]
        bob = game.players[1]
        alice.hand = [Card("green", "reverse"), Card("yellow", "3")]
        bob.hand = [Card("green", "5"), Card("blue", "4")]
        game.discard_pile = [Card("green", "9")]
        game.current_color = "green"
        game.current_player_index = 0

        game.play_card(alice.player_id, 0)

        self.assertEqual(game.current_player.player_id, bob.player_id)

    def test_after_drawing_only_the_new_last_card_is_playable(self) -> None:
        """Allow only the newly drawn final hand card, even when an older duplicate exists.

        This covers the edge case where the player already has a card identical to the one
        they just drew. After drawing, the rules still allow playing only the new last card,
        not an older matching duplicate earlier in the hand. The test first proves the draw
        remains playable, then rejects playing index 0, and finally accepts playing the last
        card that was just drawn.
        """
        game = self.make_started_game()

        alice = game.players[0]
        bob = game.players[1]

        alice.hand = [Card("green", "2"), Card("green", "2")]
        bob.hand = [Card("blue", "4")]

        game.draw_pile = [Card("yellow", "8"), Card("green", "2")]
        game.discard_pile = [Card("green", "9")]
        game.current_color = "green"
        game.current_player_index = 0

        game.draw_card(alice.player_id)
        self.assertTrue(game.has_drawn_this_turn)
        self.assertEqual(alice.hand[-1], game.drawn_card)

        with self.assertRaises(GameError):
            game.play_card(alice.player_id, 0)

        game.play_card(alice.player_id, len(alice.hand) - 1)
        self.assertFalse(game.has_drawn_this_turn)
