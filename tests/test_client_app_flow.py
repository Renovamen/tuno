from __future__ import annotations

from tests._client_app_support import (
    Card,
    ClientAPI,
    ClientAppHarness,
    Static,
    TunoApp,
    render_to_text,
)


class ClientAppFlowTests(ClientAppHarness):
    """Cover end-to-end gameplay flow in the Textual client."""

    async def test_app_can_connect_start_play_draw_and_pass(self) -> None:
        """Exercise the main happy path from connect through draw/pass resolution."""
        app = TunoApp(self.url, initial_name="alice")
        guest = ClientAPI(self.url)
        async with app.run_test() as pilot:
            suggestions = app.query_one("#command-suggestions", Static)
            self.assertFalse(suggestions.display)
            self.assertFalse(app.query_one("#hand-section").display)
            self.assertTrue(app.query_one("#tuno-logo", Static).display)
            self.assertTrue(render_to_text(app.query_one("#tuno-logo", Static).renderable).strip())
            self.assertIn(
                "Join the game: /connect <name>",
                render_to_text(app.query_one("#command-meta", Static).renderable),
            )
            self.assertIn(
                "[bold]Phase:[/] Lobby",
                render_to_text(app.query_one("#local-status-body", Static).renderable),
            )
            self.assertNotIn(
                "Available", render_to_text(app.query_one("#players-body", Static).renderable)
            )

            await app.execute_command("/connect")
            await self.wait_until(lambda: app.player_id is not None, pilot, message="host join")
            self.assertFalse(app.query_one("#command-meta", Static).display)
            self.assertIn(
                "[bold]Role:[/] Host",
                render_to_text(app.query_one("#local-status-body", Static).renderable),
            )

            await self.connect_guest(guest, pilot)

            command_input = app.query_one("#command-input")
            command_input.value = "/"
            await self.wait_until(
                lambda: "/start" in str(app.query_one("#command-suggestions", Static).renderable),
                pilot,
                message="host start help",
            )

            await app.execute_command("/start")
            await self.wait_until(
                lambda: app.state.get("started") is True, pilot, message="game start"
            )
            self.assertFalse(app.query_one("#tuno-logo", Static).display)
            self.assertTrue(app.query_one("#hand-section").display)
            self.assertIn(
                "[bold]Phase:[/] Game",
                render_to_text(app.query_one("#local-status-body", Static).renderable),
            )
            self.assertNotIn(
                "/play <n> [color]",
                render_to_text(app.query_one("#players-body", Static).renderable),
            )
            command_input.value = "/"
            await pilot.pause(0.05)
            self.assertIn(
                "/play <n> [color]", str(app.query_one("#command-suggestions", Static).renderable)
            )

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

            hand_before = render_to_text(app.query_one("#hand-body", Static).renderable)
            self.assertIn("[01]", hand_before)
            self.assertIn("R:5", hand_before)
            await self.session._broadcast_state()
            await self.wait_until(
                lambda: (
                    render_to_text(app.query_one("#hand-body", Static).renderable) == hand_before
                ),
                pilot,
                message="stable hand numbering",
            )

            await app.execute_command("/play 1")
            await self.wait_until(
                lambda: "played" in app.state.get("status_message", ""),
                pilot,
                message="play resolution",
            )
            self.assertEqual(app.state["players"][0]["card_count"], 2)
            self.assertFalse(app.state["your_turn"])
            self.assertTrue(app.query_one("#recent-top-card-body", Static).display)
            self.assertIn(
                "Top card:",
                render_to_text(app.query_one("#recent-top-card-body", Static).renderable),
            )
            self.assertIn(
                "played",
                render_to_text(app.query_one("#recent-activity-body", Static).renderable).lower(),
            )
            self.assertNotIn(
                "Top card:",
                render_to_text(app.query_one("#recent-activity-body", Static).renderable),
            )

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
            self.assertNotIn(
                "UNO: armed", render_to_text(app.query_one("#hand-body", Static).renderable)
            )
            await self.wait_until(
                lambda: (
                    "[bold]alice armed UNO.[/]"
                    in render_to_text(app.query_one("#recent-activity-body", Static).renderable)
                ),
                pilot,
                message="uno armed recent activity",
            )

            await app.execute_command("/uno")
            self.assertTrue(app.say_uno_next)
            self.assertIn(
                "[bold]alice armed UNO.[/]",
                render_to_text(app.query_one("#recent-activity-body", Static).renderable),
            )

            await app.execute_command("/draw")
            await self.wait_until(
                lambda: app.state.get("can_pass") is True, pilot, message="draw result"
            )
            command_input.value = "/"
            await pilot.pause(0.05)
            self.assertIn("/pass", str(app.query_one("#command-suggestions", Static).renderable))
            self.assertEqual(app.state["players"][0]["card_count"], 3)

            await app.execute_command("/pass")
            await self.wait_until(
                lambda: app.state.get("your_turn") is False, pilot, message="pass resolution"
            )
            self.assertIn("passed", app.state.get("status_message", ""))

        await self.close_clients(app, guest)
