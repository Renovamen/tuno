from __future__ import annotations

from unittest.mock import Mock

from tests.client.support import (
    Card,
    ClientAPI,
    ClientAppHarness,
    TunoApp,
)
from tuno.client.tui.commands import CommandMessages


class ClientCommandControllerTests(ClientAppHarness):
    """Cover command dispatch side effects without asserting rendered UI."""

    async def test_invalid_command_and_illegal_play_set_feedback(self) -> None:
        """Route syntax and play-validation failures into command feedback state."""
        app = TunoApp()
        guest = ClientAPI(self.url)
        async with app.run_test() as pilot:
            await app.execute_command("/play")
            feedback_text = app.command_controller.command_feedback_message or ""
            self.assertIn("Command error:", feedback_text)
            self.assertIn("Try /help", feedback_text)

            await self.connect_and_seed_illegal_play(app, guest, pilot)

            await app.execute_command("/play 1")
            feedback_text = app.command_controller.command_feedback_message or ""
            self.assertIn("Illegal play:", feedback_text)
            self.assertIn("does not match current color", feedback_text)

            await app.execute_command("/play 2")
            feedback_text = app.command_controller.command_feedback_message or ""
            self.assertIn("wild cards require a color", feedback_text.lower())

        await self.close_clients(app, guest)

    async def connect_and_seed_illegal_play(self, app: TunoApp, guest: ClientAPI, pilot) -> None:
        """Start a room and seed local-validation failure cases."""
        await app.execute_command(f"/server {self.url}")
        await self.wait_until(lambda: app.api is not None, pilot, message="server connect")
        await app.execute_command("/create main")
        await self.wait_until(lambda: app.selected_room_name == "main", pilot, message="room")
        await app.execute_command("/join alice")
        await self.wait_until(lambda: app.player_id is not None, pilot, message="host join")
        await self.connect_guest(guest, pilot)

        await app.execute_command("/start")
        await self.wait_until(lambda: app.state.started is True, pilot, message="game start")

        game = self.session.rooms["main"].state
        game.players[0].hand = [Card("blue", "7"), Card(None, "wild")]
        game.players[1].hand = [Card("yellow", "2"), Card("green", "4")]
        game._deck.discard_pile = [Card("red", "1")]
        game.current_color = "red"
        game.current_player_index = 0
        game.status_message = "Illegal play scenario ready."
        await self.session.rooms["main"]._broadcast_state()
        await self.wait_until(
            lambda: app.state.status_message == "Illegal play scenario ready.",
            pilot,
            message="illegal play sync",
        )

    async def test_exit_command_leaves_cleanly_and_closes_the_app(self) -> None:
        """Ensure `/exit` performs the full shutdown path for both client and server state.

        Flow:
        1. Connect to a real server session, create a room, join as host, and start a round.
        2. Invoke `/exit`.
        3. Verify the client transport is closed and the room observes the player leaving.
        4. Verify the app exit hook is called once.
        """
        app = TunoApp()
        guest = ClientAPI(self.url)
        app.exit = Mock()
        async with app.run_test() as pilot:
            # Step 1: Open transport, create/select a room, and join as host.
            await app.execute_command(f"/server {self.url}")
            await self.wait_until(lambda: app.api is not None, pilot, message="server connect")
            await app.execute_command("/create main")
            await self.wait_until(
                lambda: app.selected_room_name == "main", pilot, message="room create"
            )
            await app.execute_command("/join alice")
            await self.wait_until(lambda: app.player_id is not None, pilot, message="host join")

            # Step 1: Add a guest and start gameplay so `/exit` must send a leave.
            await self.connect_guest(guest, pilot)
            await app.execute_command("/start")
            await self.wait_until(lambda: app.state.started is True, pilot, message="game start")

            # Step 2: `/exit` should drop local transport state immediately.
            await app.execute_command("/exit")
            await self.wait_until(lambda: app.api is None, pilot, message="client close")

            # Step 3: The room should observe the leave and collapse to the remaining player.
            await self.wait_until(
                lambda: len(self.session.rooms["main"].state.players) == 1,
                pilot,
                message="server leave",
            )
            self.assertTrue(self.session.rooms["main"].state.finished)

            # Step 4: The Textual app should request shutdown exactly once.
            app.exit.assert_called_once_with()

        if guest.websocket is not None:
            await guest.close()

    async def test_repeated_uno_does_not_stick_in_waiting_state(self) -> None:
        """A second /uno (already armed) must not leave a stuck server-wait hint.

        Flow:
        1. Start a round so it is the host's turn.
        2. First /uno arms UNO and the resulting STATE clears the waiting hint.
        3. Second /uno is a local no-op (already armed); it must not re-enter the
           waiting state, since no request is sent and no STATE would clear it.
        """
        app = TunoApp()
        guest = ClientAPI(self.url)
        async with app.run_test() as pilot:
            await app.execute_command(f"/server {self.url}")
            await self.wait_until(lambda: app.api is not None, pilot, message="server connect")
            await app.execute_command("/create main")
            await self.wait_until(
                lambda: app.selected_room_name == "main", pilot, message="room create"
            )
            await app.execute_command("/join alice")
            await self.wait_until(lambda: app.player_id is not None, pilot, message="host join")
            await self.connect_guest(guest, pilot)
            await app.execute_command("/start")
            await self.wait_until(
                lambda: app.state.started is True and app.state.your_turn is True,
                pilot,
                message="our turn",
            )

            # Step 2: First /uno arms and the server STATE clears the waiting hint.
            await app.execute_command("/uno")
            await self.wait_until(lambda: app.say_uno_next is True, pilot, message="armed")
            await self.wait_until(
                lambda: app.command_controller.awaiting_server_response is False,
                pilot,
                message="first uno cleared",
            )

            # Step 3: Second /uno must not get stuck waiting; it surfaces feedback
            # through the same path used for any invalid command.
            await app.execute_command("/uno")
            self.assertFalse(app.command_controller.awaiting_server_response)
            self.assertEqual(
                app.command_controller.command_feedback_message,
                CommandMessages.uno_already_armed,
            )

        await self.close_clients(app, guest)

    async def test_failed_server_switch_keeps_current_connection(self) -> None:
        """Keep the active websocket when a later `/server` target fails to open.

        Flow:
        1. Connect to a reachable server without selecting a room.
        2. Attempt to switch to an unreachable websocket URL.
        3. Verify the original connection remains active and the failed URL is not remembered.
        """
        app = TunoApp()
        async with app.run_test() as pilot:
            # Step 1: Establish the initial server connection.
            await app.execute_command(f"/server {self.url}")
            await self.wait_until(
                lambda: app.api is not None and app.api.url == self.url,
                pilot,
                message="initial server connect",
            )

            # Step 2: Try to switch to a server that cannot accept the websocket.
            await app.execute_command("/server ws://127.0.0.1:1")
            await pilot.pause(0.1)

            # Step 3: Failed switching must not discard the working connection,
            # and the failed URL must not be added to history.
            self.assertIsNotNone(app.api)
            self.assertEqual(app.api.url, self.url)
            self.assertNotIn("ws://127.0.0.1:1", app.server_history)

        await self.close_clients(app, ClientAPI(self.url))
