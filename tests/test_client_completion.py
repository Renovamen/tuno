from __future__ import annotations

import unittest

from tuno.client.completion import (
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
            "/", available_commands=["/connect <name>", "/help"], hand=[]
        )
        self.assertEqual(
            candidates,
            [
                {"insert": "/connect ", "display": "/connect <name>"},
                {"insert": "/help", "display": "/help"},
            ],
        )

    def test_refresh_hides_suggestions_without_slash(self) -> None:
        """Hide suggestions and reset state when the input is not a command."""
        state = CompletionState(completion_candidates=["/connect "])
        # Non-slash input produces no candidates; syncing clears state.
        candidates = command_candidates(
            "play", available_commands=["/connect <name>", "/help"], hand=[]
        )
        sync_completion_state(state, candidates)
        self.assertEqual(candidates, [])
        self.assertEqual(state.completion_candidates, [])

    def test_tab_completion_uses_selected_candidate_after_navigation(self) -> None:
        """Apply the highlighted candidate after arrow-key navigation."""
        candidates = command_candidates(
            "/", available_commands=["/connect <name>", "/help"], hand=[]
        )
        state = sync_completion_state(CompletionState(), candidates)
        state = move_selection(state, candidates, 1)
        completed, state = apply_completion("/", state, candidates)
        self.assertEqual(completed, "/help")
        self.assertFalse(state.suggestion_navigated)

    def test_command_candidates_filter_out_unavailable_prefix_matches(self) -> None:
        """Avoid suggesting commands that are not currently legal for the player."""
        candidates = command_candidates(
            "/st", available_commands=["/connect <name>", "/help"], hand=[]
        )
        self.assertEqual(candidates, [])

    def test_play_candidates_include_hand_cards(self) -> None:
        """Turn the current hand into numbered `/play` suggestions."""
        candidates = command_candidates(
            "/play ",
            available_commands=["/play <n> [color]", "/draw", "/help"],
            hand=[
                {"rank": "wild", "short": "WILD", "label": "WILD"},
                {"rank": "7", "short": "G:7", "label": "Green 7"},
            ],
        )
        self.assertEqual(candidates[0]["insert"], "/play 1 ")
        self.assertEqual(candidates[1]["insert"], "/play 2")
