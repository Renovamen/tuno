from __future__ import annotations

import unittest

from tuno.client.actions import dispatch_command, play_card_by_number
from tuno.client.tui.commands import parse_command


class ClientActionTests(unittest.IsolatedAsyncioTestCase):
    """Cover command dispatch and local action validation."""

    async def test_dispatch_command_routes_by_command_spec(self) -> None:
        connected_servers: list[str] = []
        joined_names: list[str | None] = []
        sent: list[tuple[str, dict[str, object]]] = []
        exited: list[bool] = []

        async def connect(player_name=None, url=None) -> None:
            joined_names.append(player_name)

        async def connect_server(url: str) -> None:
            connected_servers.append(url)

        async def send(kind: str, **payload) -> None:
            sent.append((kind, payload))

        async def exit_client() -> None:
            exited.append(True)

        def set_feedback(message: str) -> None:
            raise AssertionError(message)

        def render_state() -> None:
            return None

        for raw in (
            "/server ws://example.test",
            "/connect alice",
            "/start",
            "/draw",
            "/pass",
            "/uno",
            "/exit",
        ):
            await dispatch_command(
                parse_command(raw),
                preferred_name="default",
                say_uno_next=False,
                state={},
                connect=connect,
                connect_server=connect_server,
                send=send,
                exit_client=exit_client,
                set_command_feedback=set_feedback,
                render_state=render_state,
            )

        self.assertEqual(connected_servers, ["ws://example.test"])
        self.assertEqual(joined_names, ["alice"])
        self.assertEqual(
            sent,
            [
                ("start", {}),
                ("draw_card", {}),
                ("pass_turn", {}),
                ("set_uno", {"armed": True}),
            ],
        )
        self.assertEqual(exited, [True])

    async def test_play_card_by_number_sends_valid_play_request(self) -> None:
        sent: list[tuple[str, dict[str, object]]] = []
        rendered: list[bool] = []

        async def send(kind: str, **payload) -> None:
            sent.append((kind, payload))

        result = await play_card_by_number(
            1,
            state={
                "current_color": "red",
                "top_card": {"rank": "5", "short": "R:5"},
                "your_player_id": "p1",
                "players": [
                    {"player_id": "p1", "hand": [{"rank": "5", "color": "blue"}]},
                ],
            },
            chosen_color=None,
            say_uno_next=True,
            send=send,
            set_command_feedback=lambda message: self.fail(message),
            render_state=lambda: rendered.append(True),
        )

        self.assertFalse(result)
        self.assertEqual(
            sent,
            [
                (
                    "play_card",
                    {"hand_index": 0, "chosen_color": None, "say_uno": True},
                )
            ],
        )
        self.assertEqual(rendered, [True])

    async def test_play_card_by_number_rejects_invalid_local_play(self) -> None:
        feedback: list[str] = []
        sent: list[tuple[str, dict[str, object]]] = []

        async def send(kind: str, **payload) -> None:
            sent.append((kind, payload))

        result = await play_card_by_number(
            1,
            state={
                "current_color": "red",
                "top_card": {"rank": "5", "short": "R:5"},
                "your_player_id": "p1",
                "players": [
                    {"player_id": "p1", "hand": [{"rank": "7", "color": "blue"}]},
                ],
            },
            chosen_color=None,
            say_uno_next=False,
            send=send,
            set_command_feedback=feedback.append,
            render_state=lambda: None,
        )

        self.assertFalse(result)
        self.assertEqual(sent, [])
        self.assertIn("does not match current color", feedback[-1])
