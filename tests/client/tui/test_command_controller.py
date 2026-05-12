from __future__ import annotations

from unittest.mock import Mock

from tests.client.support import (
    Card,
    ClientAPI,
    ClientAppHarness,
    TunoApp,
)


class ClientCommandControllerTests(ClientAppHarness):
    """Cover command dispatch side effects without asserting rendered UI."""

    async def test_invalid_command_and_illegal_play_set_feedback(self) -> None:
        """Route syntax and play-validation failures into command feedback state.

        Flow:
        1. Submit an invalid slash command before connecting.
        2. Verify parser feedback is stored on the command controller.
        3. Connect to the server, join as host, add a guest, and start a round.
        4. Seed a hand where one numbered card is illegal and one wild card lacks a color.
        5. Verify both local validation failures produce clear feedback.
        """
        app = TunoApp()
        guest = ClientAPI(self.url)
        async with app.run_test() as pilot:
            # 1. Invalid command before connect should surface parser feedback.
            await app.execute_command("/play")
            feedback_text = app.command_controller.command_feedback_message or ""
            self.assertIn("Command error:", feedback_text)
            self.assertIn("Try /help", feedback_text)

            # 2. Open the server connection, join as host, then add a guest.
            await app.execute_command(f"/server {self.url}")
            await self.wait_until(lambda: app.api is not None, pilot, message="server connect")
            await app.execute_command("/connect alice")
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
            feedback_text = app.command_controller.command_feedback_message or ""
            self.assertIn("Illegal play:", feedback_text)
            self.assertIn("does not match current color", feedback_text)

            # 4. Reject a wild card play that omits the required chosen color.
            await app.execute_command("/play 2")
            feedback_text = app.command_controller.command_feedback_message or ""
            self.assertIn("wild cards require a color", feedback_text.lower())

        await self.close_clients(app, guest)

    async def test_exit_command_leaves_cleanly_and_closes_the_app(self) -> None:
        """Ensure `/exit` performs the full shutdown path for both client and server state.

        Flow:
        1. Connect to a real server session, join as host, and start a round.
        2. Invoke `/exit`.
        3. Verify the client transport is closed and the app exit hook is called once.
        4. Verify the authoritative server session observes the player leaving the game.
        """
        app = TunoApp()
        guest = ClientAPI(self.url)
        app.exit = Mock()
        async with app.run_test() as pilot:
            # 1. Open transport, join, and start a real session for the full `/exit` path.
            await app.execute_command(f"/server {self.url}")
            await self.wait_until(lambda: app.api is not None, pilot, message="server connect")
            await app.execute_command("/connect alice")
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

    async def test_failed_server_switch_keeps_current_connection(self) -> None:
        """Keep the active websocket when a later `/server` target fails to open."""
        app = TunoApp()
        async with app.run_test() as pilot:
            await app.execute_command(f"/server {self.url}")
            await self.wait_until(
                lambda: app.api is not None and app.api.url == self.url,
                pilot,
                message="initial server connect",
            )

            await app.execute_command("/server ws://127.0.0.1:1")
            await pilot.pause(0.1)

            self.assertIsNotNone(app.api)
            self.assertEqual(app.api.url, self.url)
            self.assertIn("ws://127.0.0.1:1", app.server_history)

        await self.close_clients(app, ClientAPI(self.url))
