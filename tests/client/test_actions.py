from __future__ import annotations

import unittest

from tuno.client.actions import dispatch_command, play_card_by_number
from tuno.client.tui.commands import parse_command


class ClientActionTests(unittest.IsolatedAsyncioTestCase):
    """Cover command dispatch and local action validation."""

    async def test_dispatch_command_routes_by_command_spec(self) -> None:
        """Route each parsed command to its runtime callback or protocol send."""
        # Capture every callback effect so the command routing table can be asserted
        # without constructing a full Textual app.
        connected_servers: list[str] = []
        joined_rooms: list[str] = []
        created_rooms: list[str] = []
        joined_names: list[str | None] = []
        sent: list[tuple[str, dict[str, object]]] = []
        exited: list[bool] = []

        async def connect(player_name=None, url=None) -> None:
            joined_names.append(player_name)

        async def connect_server(url: str) -> None:
            connected_servers.append(url)

        async def join_room(name: str) -> None:
            joined_rooms.append(name)

        async def create_room(name: str) -> None:
            created_rooms.append(name)

        async def send(kind: str, **payload) -> None:
            sent.append((kind, payload))

        async def exit_client() -> None:
            exited.append(True)

        def set_feedback(message: str) -> None:
            raise AssertionError(message)

        def render_state() -> None:
            return None

        # Step 1: Dispatch the command shapes that the client exposes to users.
        for raw in (
            "/server ws://example.test",
            "/create main",
            "/connect main",
            "/join alice",
            "/start",
            "/draw",
            "/pass",
            "/uno",
            "/exit_room",
            "/exit",
        ):
            await dispatch_command(
                parse_command(raw),
                preferred_name="default",
                say_uno_next=False,
                state={},
                connect=connect,
                connect_server=connect_server,
                join_room=join_room,
                create_room=create_room,
                send=send,
                exit_client=exit_client,
                set_command_feedback=set_feedback,
                render_state=render_state,
            )

        # Step 2: Server, room, player, and exit commands should hit dedicated callbacks.
        self.assertEqual(connected_servers, ["ws://example.test"])
        self.assertEqual(created_rooms, ["main"])
        self.assertEqual(joined_rooms, ["main"])
        self.assertEqual(joined_names, ["alice"])

        # Step 3: Gameplay commands should become protocol action messages.
        self.assertEqual(
            sent,
            [
                ("start", {}),
                ("draw_card", {}),
                ("pass_turn", {}),
                ("set_uno", {"armed": True}),
                ("exit_room", {}),
            ],
        )
        self.assertEqual(exited, [True])

    async def test_play_card_by_number_sends_valid_play_request(self) -> None:
        """Convert a locally legal numbered card selection into a play_card send."""
        sent: list[tuple[str, dict[str, object]]] = []

        async def send(kind: str, **payload) -> None:
            sent.append((kind, payload))

        # Step 1: Play hand slot 1 when it matches the discard rank.
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
            render_state=lambda: None,
        )

        # Step 2: The helper should consume the local UNO intent and send zero-based index.
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

    async def test_play_card_by_number_rejects_invalid_local_play(self) -> None:
        """Reject an obviously illegal card before sending anything to the server."""
        feedback: list[str] = []
        sent: list[tuple[str, dict[str, object]]] = []

        async def send(kind: str, **payload) -> None:
            sent.append((kind, payload))

        # Step 1: Try to play a card that matches neither current color nor rank.
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

        # Step 2: Local validation should block the send and explain the mismatch.
        self.assertFalse(result)
        self.assertEqual(sent, [])
        self.assertIn("does not match current color", feedback[-1])
