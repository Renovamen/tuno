from __future__ import annotations

import unittest

from tuno.client.tui.commands import CONNECT_COMMAND, PLAY_COMMAND, VALID_PLAY_COLORS
from tuno.client.tui.completion import (
    CompletionState,
    apply_completion,
    command_candidates,
    move_selection,
    sync_completion_state,
)


class ClientCompletionTests(unittest.TestCase):
    """Cover pure completion and suggestion state helpers."""

    def test_command_candidates_use_available_commands(self) -> None:
        """Expose only commands that are currently available in the UI state."""
        candidates = command_candidates(
            "/", available_commands=["/server <server>", "/help"], hand=[]
        )
        self.assertEqual(
            candidates,
            [
                {"insert": "/server ", "display": "/server <server>"},
                {"insert": "/help", "display": "/help"},
            ],
        )

    def test_refresh_hides_suggestions_without_slash(self) -> None:
        """Hide suggestions and reset state when the input is not a command."""
        state = CompletionState(completion_candidates=["/join "])
        # Non-slash input produces no candidates; syncing clears state.
        candidates = command_candidates(
            "play", available_commands=["/join <player_name>", "/help"], hand=[]
        )
        sync_completion_state(state, candidates)
        self.assertEqual(candidates, [])
        self.assertEqual(state.completion_candidates, [])

    def test_tab_completion_uses_selected_candidate_after_navigation(self) -> None:
        """Apply the highlighted candidate after arrow-key navigation."""
        candidates = command_candidates(
            "/", available_commands=["/join <player_name>", "/help"], hand=[]
        )
        state = sync_completion_state(CompletionState(), candidates)
        state = move_selection(state, candidates, 1)
        completed, state = apply_completion("/", state, candidates)
        self.assertEqual(completed, "/help")
        self.assertFalse(state.suggestion_navigated)

    def test_command_candidates_filter_out_unavailable_prefix_matches(self) -> None:
        """Avoid suggesting commands that are not currently legal for the player."""
        candidates = command_candidates(
            "/st", available_commands=["/join <player_name>", "/help"], hand=[]
        )
        self.assertEqual(candidates, [])

    def test_play_candidates_include_hand_cards(self) -> None:
        """Turn the current hand into numbered `/play` suggestions."""
        candidates = command_candidates(
            "/play ",
            available_commands=["/play <n> [color]", "/draw", "/help"],
            card_command_token=PLAY_COMMAND.token,
            valid_play_colors=VALID_PLAY_COLORS,
            hand=[
                {"color": None, "rank": "wild"},
                {"color": "green", "rank": "7"},
            ],
        )
        self.assertEqual(candidates[0]["insert"], "/play 1 ")
        self.assertEqual(candidates[1]["insert"], "/play 2")

    def test_connect_candidates_include_existing_rooms(self) -> None:
        """Turn the visible room list into `/connect` suggestions."""
        candidates = command_candidates(
            "/connect ",
            available_commands=["/connect <room>", "/create <room>", "/help"],
            connect_command_token=CONNECT_COMMAND.token,
            hand=[],
            rooms=[
                {"name": "main", "status": "Lobby", "player_count": 1},
                {"name": "table-2", "status": "Playing", "player_count": 4},
            ],
        )
        self.assertEqual(
            candidates,
            [
                {"insert": "/connect main", "display": "/connect main"},
                {"insert": "/connect table-2", "display": "/connect table-2"},
            ],
        )

    def test_connect_candidates_filter_by_room_prefix(self) -> None:
        """Narrow `/connect` room suggestions as the user types the room name."""
        candidates = command_candidates(
            "/connect ma",
            available_commands=["/connect <room>", "/create <room>", "/help"],
            connect_command_token=CONNECT_COMMAND.token,
            hand=[],
            rooms=[
                {"name": "main"},
                {"name": "math"},
                {"name": "table-2"},
            ],
        )
        self.assertEqual(
            [candidate["insert"] for candidate in candidates],
            ["/connect main", "/connect math"],
        )
