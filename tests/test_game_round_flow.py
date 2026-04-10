import unittest

from tuno.core.cards import Card
from tuno.core.game import GameState


class GameRoundFlowTests(unittest.TestCase):
    """Cover multi-player round-flow scenarios on GameState."""

    def make_game(self) -> GameState:
        """Create a deterministic three-player game with a started round."""
        game = GameState(seed=7)
        self.alice = game.add_player("alice")
        self.bob = game.add_player("bob")
        self.cara = game.add_player("cara")
        game.start(self.alice)
        return game

    def test_host_can_start_round(self) -> None:
        """Start a seeded round and deal opening hands to every player."""
        game = self.make_game()
        self.assertTrue(game.started)
        self.assertEqual(len(game.players), 3)
        self.assertEqual(len(game.players[0].hand), 7)

    def test_skip_advances_two_turns(self) -> None:
        """Advance past the next player after a skip card resolves."""
        game = self.make_game()
        game.players[0].hand = [Card("red", "skip"), Card("green", "5")]
        game.discard_pile = [Card("red", "1")]
        game.current_color = "red"
        game.current_player_index = 0

        game.play_card(self.alice, 0)

        self.assertEqual(game.current_player.player_id, self.cara)

    def test_uno_penalty_applies_immediately(self) -> None:
        """Apply the missing-UNO penalty before the turn advances."""
        game = self.make_game()
        game.players[0].hand = [Card("red", "5"), Card("green", "2")]
        game.discard_pile = [Card("red", "1")]
        game.current_color = "red"
        game.current_player_index = 0

        game.play_card(self.alice, 0, say_uno=False)

        self.assertEqual(len(game.players[0].hand), 3)
        self.assertIn("forgot UNO", game.status_message)

    def test_single_round_finishes_when_hand_is_empty(self) -> None:
        """Finish the round immediately when a player empties their hand."""
        game = self.make_game()
        game.players[0].hand = [Card("red", "5")]
        game.discard_pile = [Card("red", "1")]
        game.current_color = "red"
        game.current_player_index = 0

        game.play_card(self.alice, 0)

        self.assertTrue(game.finished)
        self.assertEqual(game.winner_id, self.alice)

    def test_host_can_restart_after_round_finishes(self) -> None:
        """Allow the host to start a fresh round after the previous one finishes."""
        game = self.make_game()
        game.players[0].hand = [Card("red", "5")]
        game.discard_pile = [Card("red", "1")]
        game.current_color = "red"
        game.current_player_index = 0

        game.play_card(self.alice, 0)
        game.start(self.alice)

        self.assertTrue(game.started)
        self.assertFalse(game.finished)
        self.assertIsNone(game.winner_id)
        self.assertEqual(game.status_message, "Game started.")
        self.assertEqual(game.recent_events, ["Game started."])
        self.assertTrue(all(len(player.hand) == 7 for player in game.players))

    def test_disconnect_during_round_keeps_game_running_when_two_players_remain(self) -> None:
        """Continue the round when a disconnect still leaves at least two players."""
        game = self.make_game()
        game.current_player_index = 1

        game.remove_player(self.bob)

        self.assertFalse(game.finished)
        self.assertEqual(len(game.players), 2)
        self.assertEqual(game.current_player.player_id, self.cara)
        self.assertIn("disconnected", game.status_message)

    def test_disconnect_during_round_ends_game_when_one_player_remains(self) -> None:
        """End the round and award a default win when only one player remains."""
        game = GameState(seed=9)
        self.alice = game.add_player("alice")
        self.bob = game.add_player("bob")
        game.start(self.alice)

        game.remove_player(self.bob)

        self.assertTrue(game.finished)
        self.assertEqual(game.winner_id, self.alice)
        self.assertIn("wins by default", game.status_message)

    def test_last_player_disconnect_resets_game_to_lobby(self) -> None:
        """Reset the game to an unstarted lobby after the last client leaves."""
        game = GameState(seed=9)
        self.alice = game.add_player("alice")
        self.bob = game.add_player("bob")
        game.start(self.alice)

        game.remove_player(self.bob)
        game.remove_player(self.alice)

        self.assertFalse(game.started)
        self.assertFalse(game.finished)
        self.assertEqual(game.players, [])
        self.assertEqual(game.status_message, "Waiting for players.")
        self.assertEqual(game.recent_events, ["Waiting for players."])

    def test_uno_intent_records_recent_activity_for_other_players(self) -> None:
        """Broadcast the UNO arm event through the shared recent activity log."""
        game = self.make_game()
        game.current_player_index = 0

        game.set_uno_intent(self.alice, True)
        self.assertIn("armed UNO", game.status_message)
        self.assertIn("armed UNO", game.recent_events[-1])

    def test_wild_event_uses_chosen_color_in_recent_activity(self) -> None:
        """Store wild-play activity using the selected color so clients can render it correctly."""
        game = self.make_game()
        game.players[0].hand = [Card(None, "wild"), Card("green", "1")]
        game.discard_pile = [Card("blue", "4")]
        game.current_color = "blue"
        game.current_player_index = 0

        game.play_card(self.alice, 0, chosen_color="red", say_uno=True)

        self.assertIn("[bold red]WILD[/]", game.recent_events[-1])
