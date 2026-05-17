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
        """Exercise the full gameplay happy path across lobby, game, and turn actions."""
        app = TunoApp()
        guest = ClientAPI(self.url)
        async with app.run_test() as pilot:
            await self.connect_host_and_guest(app, guest, pilot)
            game = self.session.rooms["main"].state
            session = self.session.rooms["main"]

            await self.verify_normal_play(app, game, session, pilot)
            await self.verify_wild_play(app, game, session, pilot)
            await self.verify_uno_draw_and_pass(app, game, session, pilot)

        await self.close_clients(app, guest)

    async def connect_host_and_guest(self, app: TunoApp, guest: ClientAPI, pilot) -> None:
        """Create a room, join as host, attach a guest, and start gameplay."""
        await app.execute_command(f"/server {self.url}")
        await self.wait_until(lambda: app.api is not None, pilot, message="server connect")
        await app.execute_command("/create main")
        await self.wait_until(
            lambda: app.selected_room_name == "main", pilot, message="room create"
        )

        await app.execute_command("/join alice")
        await self.wait_until(lambda: app.player_id is not None, pilot, message="host join")
        self.assertEqual(len(self.session.rooms["main"].state.players), 1)

        await self.connect_guest(guest, pilot)
        await app.execute_command("/start")
        await self.wait_until(lambda: app.state.get("started") is True, pilot, message="game start")
        self.assertTrue(self.session.rooms["main"].state.started)

    async def verify_normal_play(self, app: TunoApp, game, session, pilot) -> None:
        """Seed and verify a legal numbered play from the local hand."""
        game.players[0].hand = [Card("red", "5"), Card("blue", "7"), Card("green", "1")]
        game.players[1].hand = [Card("yellow", "2"), Card("green", "4")]
        game._deck.discard_pile = [Card("red", "1")]
        game.current_color = "red"
        game.current_player_index = 0
        game._deck.draw_pile = [Card("blue", "9"), Card("yellow", "8")]
        game.has_drawn_this_turn = False
        game.drawn_card = None
        game.status_message = "Play scenario ready."
        await session._broadcast_state()
        await self.wait_until(
            lambda: app.state.get("status_message") == "Play scenario ready.",
            pilot,
            message="play scenario sync",
        )

        await app.execute_command("/play 1")
        await self.wait_until(
            lambda: "played" in app.state.get("status_message", ""),
            pilot,
            message="play resolution",
        )
        self.assertEqual(app.state["players"][0]["card_count"], 2)
        self.assertFalse(app.state["your_turn"])
        self.assertEqual(app.state["top_card"]["short"], "R:5")

    async def verify_wild_play(self, app: TunoApp, game, session, pilot) -> None:
        """Seed and verify a wild-card play with the chosen color."""
        game.current_player_index = 0
        game.players[0].hand = [Card(None, "wild"), Card("green", "1")]
        game.players[1].hand = [Card("yellow", "2"), Card("green", "4")]
        game._deck.discard_pile = [Card("blue", "9")]
        game.current_color = "blue"
        game._deck.draw_pile = [Card("red", "3"), Card("yellow", "9")]
        game.has_drawn_this_turn = False
        game.drawn_card = None
        game.status_message = "Wild scenario ready."
        await session._broadcast_state()
        await self.wait_until(
            lambda: app.state.get("status_message") == "Wild scenario ready.",
            pilot,
            message="wild scenario sync",
        )

        await app.execute_command("/play 1 red")
        await self.wait_until(
            lambda: app.state.get("current_color") == "red", pilot, message="wild resolution"
        )
        self.assertIn("played", app.state.get("status_message", ""))
        self.assertEqual(app.state["top_card"]["rank"], "wild")

    async def verify_uno_draw_and_pass(self, app: TunoApp, game, session, pilot) -> None:
        """Seed UNO and draw/pass states, then verify the client receives each transition."""
        game.current_player_index = 0
        game.players[0].hand = [Card("red", "5"), Card("green", "2")]
        game.players[1].hand = [Card("yellow", "2"), Card("green", "4")]
        game._deck.discard_pile = [Card("red", "1")]
        game.current_color = "red"
        game._deck.draw_pile = [Card("yellow", "9"), Card("red", "3")]
        game.has_drawn_this_turn = False
        game.drawn_card = None
        game.status_message = "UNO scenario ready."
        await session._broadcast_state()
        await self.wait_until(
            lambda: app.state.get("status_message") == "UNO scenario ready.",
            pilot,
            message="uno scenario sync",
        )

        await app.execute_command("/uno")
        await self.wait_until(
            lambda: "armed UNO" in " ".join(app.state.get("recent_events", [])),
            pilot,
            message="uno armed recent activity",
        )
        await app.execute_command("/uno")
        self.assertTrue(app.say_uno_next)

        await app.execute_command("/draw")
        await self.wait_until(lambda: app.state.get("can_pass") is True, pilot, message="draw")
        self.assertEqual(app.state["players"][0]["card_count"], 3)
        await app.execute_command("/pass")
        await self.wait_until(
            lambda: app.state.get("your_turn") is False, pilot, message="pass resolution"
        )
        self.assertIn("passed", app.state.get("status_message", ""))
