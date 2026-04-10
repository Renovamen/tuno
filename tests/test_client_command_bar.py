from __future__ import annotations

from unittest.mock import Mock

from tests._client_app_support import (
    Card,
    ClientAPI,
    ClientAppHarness,
    Static,
    TunoApp,
    render_to_text,
)


class ClientCommandBarTests(ClientAppHarness):
    """Cover command-meta feedback and suggestion-bar behavior."""

    async def test_invalid_command_and_illegal_play_show_text_feedback(self) -> None:
        """Surface command and play validation errors in the command-meta area."""
        app = TunoApp(self.url, initial_name="alice")
        guest = ClientAPI(self.url)
        async with app.run_test() as pilot:
            feedback = app.query_one("#command-meta", Static)
            await app.execute_command("/play")
            self.assertTrue(feedback.display)
            self.assertIn("Command error:", str(feedback.renderable))
            self.assertIn("Try /help", str(feedback.renderable))
            self.assertNotIn(
                "Command error:",
                render_to_text(app.query_one("#local-status-body", Static).renderable),
            )

            await app.execute_command("/connect")
            await self.wait_until(lambda: app.player_id is not None, pilot, message="host join")

            await self.connect_guest(guest, pilot)

            await app.execute_command("/start")
            await self.wait_until(
                lambda: app.state.get("started") is True, pilot, message="game start"
            )

            self.session.state.players[0].hand = [
                Card("blue", "7"),
                Card(None, "wild"),
            ]
            self.session.state.players[1].hand = [
                Card("yellow", "2"),
                Card("green", "4"),
            ]
            self.session.state.discard_pile = [Card("red", "1")]
            self.session.state.current_color = "red"
            self.session.state.current_player_index = 0
            self.session.state.status_message = "Illegal play scenario ready."
            await self.session._broadcast_state()
            await self.wait_until(
                lambda: app.state.get("status_message") == "Illegal play scenario ready.",
                pilot,
                message="illegal play sync",
            )

            await app.execute_command("/play 1")
            feedback_text = str(app.query_one("#command-meta", Static).renderable)
            self.assertIn("Illegal play:", feedback_text)
            self.assertIn("does not match current color", feedback_text)
            self.assertNotIn(
                "Illegal play:",
                render_to_text(app.query_one("#local-status-body", Static).renderable),
            )

            await app.execute_command("/play 2")
            feedback_text = str(app.query_one("#command-meta", Static).renderable)
            self.assertIn("wild cards require a color", feedback_text.lower())

        await self.close_clients(app, guest)

    async def test_command_suggestions_and_tab_completion(self) -> None:
        """Support suggestion visibility, arrow selection, and tab completion."""
        app = TunoApp(self.url, initial_name="alice")
        guest = ClientAPI(self.url)
        async with app.run_test() as pilot:
            command_input = app.query_one("#command-input")
            suggestions = app.query_one("#command-suggestions", Static)

            self.assertFalse(suggestions.display)
            command_input.value = "/"
            await pilot.pause(0.05)
            self.assertTrue(suggestions.display)
            self.assertNotIn("suggest commands", str(suggestions.renderable))
            self.assertIn("[bold #7aa2f7]> /connect <name>[/]", str(suggestions.renderable))
            await pilot.press("down")
            self.assertIn("[bold #7aa2f7]> /help[/]", str(suggestions.renderable))
            await pilot.press("tab")
            self.assertEqual(command_input.value, "/help")

            command_input.value = "/"
            await pilot.pause(0.05)
            self.assertIn("[bold #7aa2f7]> /connect <name>[/]", str(suggestions.renderable))
            command_input.value = "/st"
            await pilot.pause(0.05)
            self.assertNotIn("/start", str(suggestions.renderable))
            await pilot.press("tab")
            self.assertEqual(command_input.value, "/st")

            await app.execute_command("/connect")
            await self.wait_until(lambda: app.player_id is not None, pilot, message="host join")

            await self.connect_guest(guest, pilot)
            command_input.value = ""
            await pilot.pause(0.05)
            self.assertFalse(suggestions.display)
            command_input.value = "/"
            await pilot.pause(0.05)
            self.assertIn("[bold #7aa2f7]> /start[/]", str(suggestions.renderable))
            self.assertNotIn("/play <n> [color]", str(suggestions.renderable))

            await app.execute_command("/start")
            await self.wait_until(
                lambda: app.state.get("started") is True, pilot, message="game start"
            )

            self.session.state.players[0].hand = [
                Card(None, "wild"),
                Card("green", "1"),
            ]
            self.session.state.players[1].hand = [
                Card("yellow", "2"),
                Card("green", "4"),
            ]
            self.session.state.discard_pile = [Card("blue", "9")]
            self.session.state.current_color = "blue"
            self.session.state.current_player_index = 0
            self.session.state.status_message = "Suggestion scenario ready."
            await self.session._broadcast_state()
            await self.wait_until(
                lambda: app.state.get("status_message") == "Suggestion scenario ready.",
                pilot,
                message="suggestion scenario sync",
            )

            command_input.value = "/pl"
            await pilot.pause(0.05)
            self.assertIn("[bold #7aa2f7]> /play <n> [color][/]", str(suggestions.renderable))
            self.assertIn("/play <n> [color]", str(suggestions.renderable))
            await pilot.press("tab")
            self.assertEqual(command_input.value, "/play ")

            command_input.value = "/play "
            await pilot.pause(0.05)
            self.assertIn("[bold #7aa2f7]> /play 1 <color> — WILD[/]", str(suggestions.renderable))
            self.assertIn("/play 1 <color> — WILD", str(suggestions.renderable))
            self.assertNotIn("/play 2 — G:1", str(suggestions.renderable))

            command_input.value = "/play "
            await pilot.pause(0.05)
            self.assertIn("[bold #7aa2f7]> /play 1 <color> — WILD[/]", str(suggestions.renderable))
            await pilot.press("tab")
            self.assertEqual(command_input.value, "/play 1 ")

            command_input.value = "/play 1 r"
            await pilot.pause(0.05)
            self.assertIn("/play 1 red", str(suggestions.renderable))
            await pilot.press("tab")
            self.assertEqual(command_input.value, "/play 1 red")

        await self.close_clients(app, guest)

    async def test_exit_command_leaves_cleanly_and_closes_the_app(self) -> None:
        """Allow `/exit` to notify the server, close transport state, and exit the UI."""
        app = TunoApp(self.url, initial_name="alice")
        guest = ClientAPI(self.url)
        app.exit = Mock()
        async with app.run_test() as pilot:
            await app.execute_command("/connect")
            await self.wait_until(lambda: app.player_id is not None, pilot, message="host join")

            await self.connect_guest(guest, pilot)
            await app.execute_command("/start")
            await self.wait_until(
                lambda: app.state.get("started") is True, pilot, message="game start"
            )

            await app.execute_command("/exit")
            await self.wait_until(lambda: app.api is None, pilot, message="client close")
            await self.wait_until(
                lambda: len(self.session.state.players) == 1, pilot, message="server leave"
            )
            self.assertTrue(self.session.state.finished)
            app.exit.assert_called_once_with()

        if guest.websocket is not None:
            await guest.close()
