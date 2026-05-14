from __future__ import annotations

from tests.client.support import (
    Card,
    ClientAPI,
    ClientAppHarness,
    TunoApp,
)


class ClientAppFlowTests(ClientAppHarness):
    """Cover end-to-end gameplay flow in the Textual client."""

    async def test_initial_url_connects_on_mount(self) -> None:
        app = TunoApp(initial_url=self.url)

        async with app.run_test() as pilot:
            await self.wait_until(lambda: app.api is not None, pilot, message="initial server")
            await app.runtime.close_current_server()

    async def test_app_can_connect_start_play_draw_and_pass(self) -> None:
        """Exercise the full gameplay happy path across lobby, game, and turn actions.

        Flow:
        1. Connect to the server and create a room.
        2. Join the local player as host and connect a guest player.
        3. Start a round and bind the test to the created room session.
        4. Seed a normal play scenario and verify `/play 1` updates card counts and turn state.
        5. Seed a wild-card scenario and verify `/play 1 red` updates the chosen color.
        6. Seed draw and UNO scenarios, arm UNO, and verify the UNO intent sticks.
        7. Draw a card, confirm `/pass` becomes available, then pass and verify turn/state reset.
        """
        app = TunoApp()
        guest = ClientAPI(self.url)
        async with app.run_test() as pilot:
            # Step 1: Connect to the websocket server, then create and select the room.
            await app.execute_command(f"/server {self.url}")
            await self.wait_until(lambda: app.api is not None, pilot, message="server connect")
            await app.execute_command("/create main")
            await self.wait_until(
                lambda: app.selected_room_name == "main", pilot, message="room create"
            )

            # Step 2: Join the room as the local host and attach a second player.
            await app.execute_command("/join alice")
            await self.wait_until(lambda: app.player_id is not None, pilot, message="host join")
            self.assertEqual(len(self.session.rooms["main"].state.players), 1)

            await self.connect_guest(guest, pilot)

            # Step 3: Start gameplay and keep direct handles to the active room state.
            await app.execute_command("/start")
            await self.wait_until(
                lambda: app.state.get("started") is True, pilot, message="game start"
            )
            game = self.session.rooms["main"].state
            session = self.session.rooms["main"]
            self.assertTrue(game.started)

            # Step 4: Seed a deterministic normal-play state for `/play 1`.
            game.players[0].hand = [
                Card("red", "5"),
                Card("blue", "7"),
                Card("green", "1"),
            ]
            game.players[1].hand = [Card("yellow", "2"), Card("green", "4")]
            game.discard_pile = [Card("red", "1")]
            game.current_color = "red"
            game.current_player_index = 0
            game.draw_pile = [Card("blue", "9"), Card("yellow", "8")]
            game.has_drawn_this_turn = False
            game.drawn_card = None
            game.status_message = "Play scenario ready."
            await session._broadcast_state()
            await self.wait_until(
                lambda: app.state.get("status_message") == "Play scenario ready.",
                pilot,
                message="play scenario sync",
            )

            # Step 4 assertion: Playing the first card advances turn state and card counts.
            await app.execute_command("/play 1")
            await self.wait_until(
                lambda: "played" in app.state.get("status_message", ""),
                pilot,
                message="play resolution",
            )
            self.assertEqual(app.state["players"][0]["card_count"], 2)
            self.assertFalse(app.state["your_turn"])
            self.assertEqual(app.state["top_card"]["short"], "R:5")

            # Step 5: Seed a wild-card state where the command must include a color.
            game.current_player_index = 0
            game.players[0].hand = [Card(None, "wild"), Card("green", "1")]
            game.players[1].hand = [Card("yellow", "2"), Card("green", "4")]
            game.discard_pile = [Card("blue", "9")]
            game.current_color = "blue"
            game.draw_pile = [Card("red", "3"), Card("yellow", "9")]
            game.has_drawn_this_turn = False
            game.drawn_card = None
            game.status_message = "Wild scenario ready."
            await session._broadcast_state()
            await self.wait_until(
                lambda: app.state.get("status_message") == "Wild scenario ready.",
                pilot,
                message="wild scenario sync",
            )

            # Step 5 assertion: `/play 1 red` records the chosen color on the snapshot.
            await app.execute_command("/play 1 red")
            await self.wait_until(
                lambda: app.state.get("current_color") == "red", pilot, message="wild resolution"
            )
            self.assertIn("played", app.state.get("status_message", ""))
            self.assertEqual(app.state["top_card"]["rank"], "wild")

            # Step 6: Seed a draw-ready state and verify the client receives it.
            game.current_player_index = 0
            game.players[0].hand = [Card("blue", "7"), Card("green", "1")]
            game.players[1].hand = [Card("yellow", "2"), Card("green", "4")]
            game.discard_pile = [Card("yellow", "1")]
            game.current_color = "yellow"
            game.draw_pile = [Card("red", "3"), Card("yellow", "9")]
            game.has_drawn_this_turn = False
            game.drawn_card = None
            game.status_message = "Draw scenario ready."
            await session._broadcast_state()
            await self.wait_until(
                lambda: app.state.get("status_message") == "Draw scenario ready.",
                pilot,
                message="draw scenario sync",
            )

            # Step 6: Seed the one-card-after-play UNO path before arming UNO.
            game.players[0].hand = [Card("red", "5"), Card("green", "2")]
            game.players[1].hand = [Card("yellow", "2"), Card("green", "4")]
            game.discard_pile = [Card("red", "1")]
            game.current_color = "red"
            game.current_player_index = 0
            game.draw_pile = [Card("yellow", "9"), Card("red", "3")]
            game.has_drawn_this_turn = False
            game.drawn_card = None
            game.status_message = "UNO scenario ready."
            await session._broadcast_state()
            await self.wait_until(
                lambda: app.state.get("status_message") == "UNO scenario ready.",
                pilot,
                message="uno scenario sync",
            )

            # Step 6 assertion: The first `/uno` reaches the server and is broadcast.
            await app.execute_command("/uno")
            await self.wait_until(
                lambda: "armed UNO" in " ".join(app.state.get("recent_events", [])),
                pilot,
                message="uno armed recent activity",
            )

            # Step 6 assertion: The second `/uno` arms the local intent for the next play.
            await app.execute_command("/uno")
            self.assertTrue(app.say_uno_next)

            # Step 7: Draw once, then pass after the server marks passing as legal.
            await app.execute_command("/draw")
            await self.wait_until(
                lambda: app.state.get("can_pass") is True, pilot, message="draw result"
            )
            self.assertEqual(app.state["players"][0]["card_count"], 3)

            # Step 7 assertion: Passing advances away from the local player's turn.
            await app.execute_command("/pass")
            await self.wait_until(
                lambda: app.state.get("your_turn") is False, pilot, message="pass resolution"
            )
            self.assertIn("passed", app.state.get("status_message", ""))

        await self.close_clients(app, guest)
