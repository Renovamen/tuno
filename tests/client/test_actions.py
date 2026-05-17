from __future__ import annotations

import unittest

from tuno.client.actions import dispatch_command, play_card_by_number
from tuno.client.tui.commands import parse_command


class ClientActionTests(unittest.IsolatedAsyncioTestCase):
    """Cover command dispatch and local action validation."""

    async def test_dispatch_command_routes_by_command_spec(self) -> None:
        """Route each parsed command to its runtime callback or protocol send."""
        recorder = CommandDispatchRecorder()

        await self.dispatch_user_commands(recorder)

        self.assertEqual(recorder.connected_servers, ["ws://example.test"])
        self.assertEqual(recorder.created_rooms, ["main"])
        self.assertEqual(recorder.joined_rooms, ["main"])
        self.assertEqual(recorder.joined_names, ["alice"])
        self.assertEqual(
            recorder.sent,
            [
                ("start", {}),
                ("draw_card", {}),
                ("pass_turn", {}),
                ("set_uno", {"armed": True}),
                ("exit_room", {}),
            ],
        )
        self.assertEqual(recorder.exited_servers, [True])
        self.assertEqual(recorder.exited, [True])

    async def dispatch_user_commands(self, recorder: "CommandDispatchRecorder") -> None:
        """Dispatch command shapes that users can submit through the command input."""
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
            "/exit_server",
            "/exit",
        ):
            await dispatch_command(
                parse_command(raw),
                preferred_name="default",
                say_uno_next=False,
                state={},
                connect=recorder.connect,
                connect_server=recorder.connect_server,
                join_room=recorder.join_room,
                create_room=recorder.create_room,
                send=recorder.send,
                exit_client=recorder.exit_client,
                exit_server=recorder.exit_server,
                set_command_feedback=recorder.set_feedback,
                render_state=recorder.render_state,
            )

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


class CommandDispatchRecorder:
    """Capture callback effects without constructing a full Textual app."""

    def __init__(self) -> None:
        self.connected_servers: list[str] = []
        self.joined_rooms: list[str] = []
        self.created_rooms: list[str] = []
        self.joined_names: list[str | None] = []
        self.sent: list[tuple[str, dict[str, object]]] = []
        self.exited: list[bool] = []
        self.exited_servers: list[bool] = []

    async def connect(self, player_name=None, url=None) -> None:
        self.joined_names.append(player_name)

    async def connect_server(self, url: str) -> None:
        self.connected_servers.append(url)

    async def join_room(self, name: str) -> None:
        self.joined_rooms.append(name)

    async def create_room(self, name: str) -> None:
        self.created_rooms.append(name)

    async def send(self, kind: str, **payload) -> None:
        self.sent.append((kind, payload))

    async def exit_client(self) -> None:
        self.exited.append(True)

    async def exit_server(self) -> None:
        self.exited_servers.append(True)

    def set_feedback(self, message: str) -> None:
        raise AssertionError(message)

    def render_state(self) -> None:
        return None
