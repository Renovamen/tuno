from __future__ import annotations

from tests._client_app_support import (
    Card,
    ClientAPI,
    ClientAppHarness,
    TunoApp,
)


class ClientAppFlowTests(ClientAppHarness):
    """Cover end-to-end gameplay flow in the Textual client."""

    async def test_app_can_connect_start_play_draw_and_pass(self) -> None:
        """Exercise the full gameplay happy path across lobby, game, and turn actions.

        Flow:
        1. Start from the unjoined state and connect the local player as host.
        2. Connect the local player as host and join a second player.
        3. Start a round and verify the session enters gameplay state.
        4. Seed a normal play scenario and verify `/play 1` updates card counts and turn state.
        5. Seed a wild-card scenario and verify `/play 1 red` updates the chosen color.
        6. Seed an UNO scenario, arm UNO, and verify the UNO intent sticks.
        7. Draw a card, confirm `/pass` becomes available, then pass and verify turn/state reset.
        """
        app = TunoApp(self.url, initial_name="alice")
        guest = ClientAPI(self.url)
        async with app.run_test() as pilot:
            await app.execute_command("/connect")
            await self.wait_until(lambda: app.player_id is not None, pilot, message="host join")
            self.assertEqual(len(self.session.state.players), 1)

            await self.connect_guest(guest, pilot)

            await app.execute_command("/start")
            await self.wait_until(
                lambda: app.state.get("started") is True, pilot, message="game start"
            )
            self.assertTrue(self.session.state.started)

            self.session.state.players[0].hand = [
                Card("red", "5"),
                Card("blue", "7"),
                Card("green", "1"),
            ]
            self.session.state.players[1].hand = [Card("yellow", "2"), Card("green", "4")]
            self.session.state.discard_pile = [Card("red", "1")]
            self.session.state.current_color = "red"
            self.session.state.current_player_index = 0
            self.session.state.draw_pile = [Card("blue", "9"), Card("yellow", "8")]
            self.session.state.has_drawn_this_turn = False
            self.session.state.drawn_card = None
            self.session.state.status_message = "Play scenario ready."
            await self.session._broadcast_state()
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

            self.session.state.current_player_index = 0
            self.session.state.players[0].hand = [Card(None, "wild"), Card("green", "1")]
            self.session.state.players[1].hand = [Card("yellow", "2"), Card("green", "4")]
            self.session.state.discard_pile = [Card("blue", "9")]
            self.session.state.current_color = "blue"
            self.session.state.draw_pile = [Card("red", "3"), Card("yellow", "9")]
            self.session.state.has_drawn_this_turn = False
            self.session.state.drawn_card = None
            self.session.state.status_message = "Wild scenario ready."
            await self.session._broadcast_state()
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

            self.session.state.current_player_index = 0
            self.session.state.players[0].hand = [Card("blue", "7"), Card("green", "1")]
            self.session.state.players[1].hand = [Card("yellow", "2"), Card("green", "4")]
            self.session.state.discard_pile = [Card("yellow", "1")]
            self.session.state.current_color = "yellow"
            self.session.state.draw_pile = [Card("red", "3"), Card("yellow", "9")]
            self.session.state.has_drawn_this_turn = False
            self.session.state.drawn_card = None
            self.session.state.status_message = "Draw scenario ready."
            await self.session._broadcast_state()
            await self.wait_until(
                lambda: app.state.get("status_message") == "Draw scenario ready.",
                pilot,
                message="draw scenario sync",
            )

            self.session.state.players[0].hand = [Card("red", "5"), Card("green", "2")]
            self.session.state.players[1].hand = [Card("yellow", "2"), Card("green", "4")]
            self.session.state.discard_pile = [Card("red", "1")]
            self.session.state.current_color = "red"
            self.session.state.current_player_index = 0
            self.session.state.draw_pile = [Card("yellow", "9"), Card("red", "3")]
            self.session.state.has_drawn_this_turn = False
            self.session.state.drawn_card = None
            self.session.state.status_message = "UNO scenario ready."
            await self.session._broadcast_state()
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
            await self.wait_until(
                lambda: app.state.get("can_pass") is True, pilot, message="draw result"
            )
            self.assertEqual(app.state["players"][0]["card_count"], 3)

            await app.execute_command("/pass")
            await self.wait_until(
                lambda: app.state.get("your_turn") is False, pilot, message="pass resolution"
            )
            self.assertIn("passed", app.state.get("status_message", ""))

        await self.close_clients(app, guest)
