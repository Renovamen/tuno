from __future__ import annotations

import unittest

from tuno.client.rendering import (
    format_server_error,
    render_command_feedback,
    render_hand_body,
    render_local_status_body,
    render_players_title,
    render_recent_activity_body,
    render_top_card_body,
)


class ClientRenderingTests(unittest.TestCase):
    """Cover pure rendering helpers for client-facing Textual markup."""

    def test_command_feedback_escapes_markup(self) -> None:
        """Escape Rich markup so feedback text cannot spoof the UI."""
        self.assertEqual(render_command_feedback("[bold]boom[/]"), r"> \[bold]boom\[/]")

    def test_command_feedback_is_empty_without_a_message(self) -> None:
        """Return an empty renderable when there is no feedback to display."""
        self.assertEqual(render_command_feedback(None), "")

    def test_local_status_body_renders_bold_role_and_phase_labels(self) -> None:
        """Render role and phase labels with inline emphasis markup."""
        body = render_local_status_body({})
        self.assertIn("[bold]Role:[/] Not joined", body)
        self.assertIn("[bold]Phase:[/] Lobby", body)

    def test_hand_body_renders_empty_state_without_player_metadata(self) -> None:
        """Render only hand-relevant content, without duplicating player metadata."""
        body = render_hand_body(
            {
                "your_player_id": "p1",
                "host_player_id": "p1",
                "players": [{"player_id": "p1", "name": "[danger]", "hand": []}],
            },
            say_uno_next=False,
        )
        self.assertEqual(body, "(empty)")

    def test_players_title_includes_current_count(self) -> None:
        """Reflect the connected-player count in the section title."""
        self.assertEqual(render_players_title({"players": [{}, {}]}), "Players (2/5)")

    def test_recent_activity_body_shows_empty_state(self) -> None:
        """Fallback to a placeholder when there are no gameplay events yet."""
        body = render_recent_activity_body({"recent_events": []})
        self.assertIn("No game events yet.", body)

    def test_top_card_body_is_rendered_separately_from_recent_events(self) -> None:
        """Expose the top card independently instead of splicing it into event history."""
        body = render_top_card_body(
            {
                "started": True,
                "top_card": {"color": "red", "short": "R:5", "label": "Red 5"},
            }
        )
        self.assertIn("Top card:", body)
        recent = render_recent_activity_body({"started": True, "recent_events": ["Game started."]})
        self.assertNotIn("Top card:", recent)

    def test_top_card_body_uses_current_color_for_wild_cards(self) -> None:
        """Render wild top cards using the chosen current color, not the base wild color."""
        body = render_top_card_body(
            {
                "started": True,
                "current_color": "red",
                "top_card": {
                    "color": None,
                    "rank": "wild",
                    "short": "WILD",
                    "label": "Wild",
                },
            }
        )
        self.assertIn("[bold red]WILD[/]", body)

    def test_recent_activity_bolds_uno_and_preserves_event_markup(self) -> None:
        """Apply presentation formatting to recent activity without flattening card markup."""
        body = render_recent_activity_body(
            {
                "recent_events": [
                    "alice armed UNO.",
                    "alice played [bold blue]WILD[/].",
                ]
            }
        )
        self.assertIn("[bold]alice armed UNO.[/]", body)
        self.assertIn("[bold blue]WILD[/]", body)

    def test_format_server_error_uses_current_color_and_top_card(self) -> None:
        """Include the current color and top card when rewriting server errors."""
        state = {"current_color": "red", "top_card": {"short": "R:5"}}
        message = format_server_error(
            state, "That card can't be played right now.", code="illegal_play"
        )
        self.assertIn("current color red", message)
        self.assertIn("top card R:5", message)
