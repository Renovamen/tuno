from __future__ import annotations

from unittest.mock import Mock

from tests._client_app_support import (
    Card,
    ClientAPI,
    ClientAppHarness,
    Static,
    TunoApp,
)


class ClientCommandBarTests(ClientAppHarness):
    """Cover command-meta feedback and suggestion-bar behavior."""

    async def test_invalid_command_and_illegal_play_show_text_feedback(self) -> None:
        """Route syntax and play-validation failures into the command-meta feedback area.

        Flow:
        1. Submit an invalid slash command before connecting.
        2. Verify parser feedback is surfaced to the user.
        3. Connect, join a second player, and start a round.
        4. Seed a hand where one numbered card is illegal and one wild card lacks a color.
        5. Verify both local validation failures produce clear feedback.
        """
        app = TunoApp(self.url, initial_name="alice")
        guest = ClientAPI(self.url)
        async with app.run_test() as pilot:
            # 1. Invalid command before connect should surface parser feedback.
            await app.execute_command("/play")
            feedback_text = str(app.query_one("#command-meta", Static).renderable)
            self.assertIn("Command error:", feedback_text)
            self.assertIn("Try /help", feedback_text)

            # 2. Connect, join a guest, and enter an active round for play validation.
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

            # 3. Reject a numbered card that does not match color or rank.
            await app.execute_command("/play 1")
            feedback_text = str(app.query_one("#command-meta", Static).renderable)
            self.assertIn("Illegal play:", feedback_text)
            self.assertIn("does not match current color", feedback_text)

            # 4. Reject a wild card play that omits the required chosen color.
            await app.execute_command("/play 2")
            feedback_text = str(app.query_one("#command-meta", Static).renderable)
            self.assertIn("wild cards require a color", feedback_text.lower())

        await self.close_clients(app, guest)

    async def test_command_suggestions_and_tab_completion(self) -> None:
        """Verify command suggestions evolve with app state and support keyboard completion.

        Flow:
        1. Start in the pre-join state and verify `/connect` suggestions appear from `/`.
        2. Use arrow keys and Tab to move the selection and complete `/help`.
        3. Connect as host, join a second player, and verify `/start` appears in the lobby.
        4. Start a round and seed a wild-card hand for the local player.
        5. Verify `/play` suggestions derive from the current hand and support progressive
           Tab completion through command, card number, and wild color.
        """
        app = TunoApp(self.url, initial_name="alice")
        guest = ClientAPI(self.url)
        async with app.run_test() as pilot:
            command_input = app.query_one("#command-input")
            suggestions = app.query_one("#command-suggestions", Static)

            # 1. Pre-join suggestions start with connect/help candidates from a bare slash.
            self.assertFalse(suggestions.display)
            command_input.value = "/"
            await pilot.pause(0.05)
            self.assertIn("/connect <name>", str(suggestions.renderable))
            await pilot.press("down")
            self.assertIn("/help", str(suggestions.renderable))
            await pilot.press("tab")
            self.assertEqual(command_input.value, "/help")

            # 2. Partial `/st` input should not autocomplete into `/start` before joining.
            command_input.value = "/"
            await pilot.pause(0.05)
            self.assertIn("/connect <name>", str(suggestions.renderable))
            command_input.value = "/st"
            await pilot.pause(0.05)
            self.assertNotIn("/start", str(suggestions.renderable))
            await pilot.press("tab")
            self.assertEqual(command_input.value, "/st")

            # 3. After host+guest reach the lobby, `/start` becomes the primary suggestion.
            await app.execute_command("/connect")
            await self.wait_until(lambda: app.player_id is not None, pilot, message="host join")

            await self.connect_guest(guest, pilot)
            command_input.value = ""
            await pilot.pause(0.05)
            self.assertEqual(str(suggestions.renderable), "")
            command_input.value = "/"
            await pilot.pause(0.05)
            self.assertIn("/start", str(suggestions.renderable))
            self.assertNotIn("/play <n> [color]", str(suggestions.renderable))

            # 4. Once the round starts, `/play` suggestions are derived from the visible hand.
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

            # 5. Tab completion should expand `/pl` into the full `/play` template.
            command_input.value = "/pl"
            await pilot.pause(0.05)
            self.assertIn("/play <n> [color]", str(suggestions.renderable))
            await pilot.press("tab")
            self.assertEqual(command_input.value, "/play ")

            # 6. With `/play `, only legal hand candidates should be suggested.
            command_input.value = "/play "
            await pilot.pause(0.05)
            self.assertIn("/play 1 <color> — WILD", str(suggestions.renderable))
            self.assertNotIn("/play 2 — G:1", str(suggestions.renderable))

            # 7. Tab completion should advance from the play template to the selected card slot.
            command_input.value = "/play "
            await pilot.pause(0.05)
            self.assertIn("/play 1 <color> — WILD", str(suggestions.renderable))
            await pilot.press("tab")
            self.assertEqual(command_input.value, "/play 1 ")

            # 8. Wild-card color completion should finish `/play 1 r` as `/play 1 red`.
            command_input.value = "/play 1 r"
            await pilot.pause(0.05)
            self.assertIn("/play 1 red", str(suggestions.renderable))
            await pilot.press("tab")
            self.assertEqual(command_input.value, "/play 1 red")

        await self.close_clients(app, guest)

    async def test_exit_command_leaves_cleanly_and_closes_the_app(self) -> None:
        """Ensure `/exit` performs the full shutdown path for both client and server state.

        Flow:
        1. Join a real session and start a round.
        2. Invoke `/exit`.
        3. Verify the client transport is closed and the app exit hook is called once.
        4. Verify the authoritative server session observes the player leaving the game.
        """
        app = TunoApp(self.url, initial_name="alice")
        guest = ClientAPI(self.url)
        app.exit = Mock()
        async with app.run_test() as pilot:
            # 1. Join and start a real session so `/exit` exercises the full leave path.
            await app.execute_command("/connect")
            await self.wait_until(lambda: app.player_id is not None, pilot, message="host join")

            await self.connect_guest(guest, pilot)
            await app.execute_command("/start")
            await self.wait_until(
                lambda: app.state.get("started") is True, pilot, message="game start"
            )

            # 2. `/exit` should drop local transport state immediately.
            await app.execute_command("/exit")
            await self.wait_until(lambda: app.api is None, pilot, message="client close")

            # 3. The server should observe the leave and collapse to the remaining player.
            await self.wait_until(
                lambda: len(self.session.state.players) == 1, pilot, message="server leave"
            )
            self.assertTrue(self.session.state.finished)

            # 4. The Textual app should request shutdown exactly once.
            app.exit.assert_called_once_with()

        if guest.websocket is not None:
            await guest.close()
