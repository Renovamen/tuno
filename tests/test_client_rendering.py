from __future__ import annotations

import unittest

from tuno.client.rendering import (
    format_server_error,
    render_command_feedback,
)


class ClientRenderingTests(unittest.TestCase):
    """Cover functional rendering helpers that affect correctness or safety."""

    def test_command_feedback_escapes_markup(self) -> None:
        """Escape Rich markup so feedback text cannot spoof the UI."""
        self.assertEqual(render_command_feedback("[bold]boom[/]"), r"\[bold]boom\[/]")

    def test_command_feedback_is_empty_without_a_message(self) -> None:
        """Return an empty renderable when there is no feedback to display."""
        self.assertEqual(render_command_feedback(None), "")

    def test_format_server_error_uses_current_color_and_top_card(self) -> None:
        """Include the current color and top card when rewriting server errors."""
        state = {"current_color": "red", "top_card": {"short": "R:5"}}
        message = format_server_error(
            state, "That card can't be played right now.", code="illegal_play"
        )
        self.assertIn("current color red", message)
        self.assertIn("top card R:5", message)
