from __future__ import annotations

import unittest

from tuno.client.actions import dispatch_command, play_card_by_number
from tuno.client.tui.commands import parse_command
from tuno.core.snapshot import GameSnapshot
from tuno.protocol.messages import ClientMsg


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
                (ClientMsg.START, {}),
                (ClientMsg.DRAW_CARD, {}),
                (ClientMsg.PASS_TURN, {}),
                (ClientMsg.EXIT_ROOM, {}),
            ],
        )
        self.assertEqual(recorder.exited_games, [True])
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
            "/exit_game",
            "/exit_room",
            "/exit_server",
            "/exit",
        ):
            await dispatch_command(
                parse_command(raw),
                preferred_name="default",
                say_uno_next=False,
                state=GameSnapshot(),
                connect=recorder.connect,
                connect_server=recorder.connect_server,
                join_room=recorder.join_room,
                create_room=recorder.create_room,
                send=recorder.send,
                exit_client=recorder.exit_client,
                exit_server=recorder.exit_server,
                exit_game=recorder.exit_game,
                set_command_feedback=recorder.set_feedback,
                render_state=recorder.render_state,
            )

    async def _dispatch_uno(
        self, *, state: GameSnapshot, say_uno_next: bool
    ) -> tuple[bool, list[tuple[ClientMsg, dict[str, object]]], list[str]]:
        """Dispatch a single /uno and return (result, sent, feedback)."""
        sent: list[tuple[ClientMsg, dict[str, object]]] = []
        feedback: list[str] = []

        async def send(kind: ClientMsg, **payload) -> None:
            sent.append((kind, payload))

        async def noop_room(name: str) -> None:
            return None

        async def noop_connect(player_name=None, url=None) -> None:
            return None

        async def noop_exit() -> None:
            return None

        result = await dispatch_command(
            parse_command("/uno"),
            preferred_name="default",
            say_uno_next=say_uno_next,
            state=state,
            connect=noop_connect,
            connect_server=noop_room,
            join_room=noop_room,
            create_room=noop_room,
            send=send,
            exit_client=noop_exit,
            exit_server=noop_exit,
            exit_game=noop_exit,
            set_command_feedback=feedback.append,
            render_state=lambda: None,
        )
        return result, sent, feedback

    async def test_uno_blocked_when_not_your_turn(self) -> None:
        """Reject /uno locally when it is not the player's active turn."""
        for state in (
            GameSnapshot(),  # not started
            GameSnapshot(started=True, your_turn=False),  # someone else's turn
        ):
            result, sent, feedback = await self._dispatch_uno(state=state, say_uno_next=False)
            self.assertFalse(result)
            self.assertEqual(sent, [])
            self.assertIn("only call UNO on your turn", feedback[-1])

    async def test_uno_preserves_armed_flag_when_blocked(self) -> None:
        """A blocked /uno must not flip an already-armed local flag."""
        result, sent, _ = await self._dispatch_uno(state=GameSnapshot(), say_uno_next=True)
        self.assertTrue(result)
        self.assertEqual(sent, [])

    async def test_uno_arms_on_active_turn(self) -> None:
        """Arm UNO and send SET_UNO when it is the player's turn."""
        result, sent, _ = await self._dispatch_uno(
            state=GameSnapshot(started=True, your_turn=True), say_uno_next=False
        )
        self.assertTrue(result)
        self.assertEqual(sent, [(ClientMsg.SET_UNO, {"armed": True})])

    async def test_uno_is_idempotent_when_already_armed(self) -> None:
        """Do not resend SET_UNO when already armed; surface feedback instead."""
        result, sent, feedback = await self._dispatch_uno(
            state=GameSnapshot(started=True, your_turn=True), say_uno_next=True
        )
        self.assertTrue(result)
        self.assertEqual(sent, [])
        self.assertIn("already armed", feedback[-1])

    async def test_play_card_by_number_sends_valid_play_request(self) -> None:
        """Convert a locally legal numbered card selection into a play_card send."""
        sent: list[tuple[ClientMsg, dict[str, object]]] = []

        async def send(kind: ClientMsg, **payload) -> None:
            sent.append((kind, payload))

        # Step 1: Play hand slot 1 when it matches the discard rank.
        result = await play_card_by_number(
            1,
            state=GameSnapshot(
                current_color="red",
                top_card={"color": "red", "rank": "5"},
                your_player_id="p1",
                players=[
                    {"player_id": "p1", "hand": [{"rank": "5", "color": "blue"}]},
                ],
            ),
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
                    ClientMsg.PLAY_CARD,
                    {"hand_index": 0, "chosen_color": None, "say_uno": True},
                )
            ],
        )

    async def test_play_card_by_number_rejects_invalid_local_play(self) -> None:
        """Reject an obviously illegal card before sending anything to the server."""
        feedback: list[str] = []
        sent: list[tuple[ClientMsg, dict[str, object]]] = []

        async def send(kind: ClientMsg, **payload) -> None:
            sent.append((kind, payload))

        # Step 1: Try to play a card that matches neither current color nor rank.
        result = await play_card_by_number(
            1,
            state=GameSnapshot(
                current_color="red",
                top_card={"color": "red", "rank": "5"},
                your_player_id="p1",
                players=[
                    {"player_id": "p1", "hand": [{"rank": "7", "color": "blue"}]},
                ],
            ),
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
        self.sent: list[tuple[ClientMsg, dict[str, object]]] = []
        self.exited: list[bool] = []
        self.exited_servers: list[bool] = []
        self.exited_games: list[bool] = []

    async def connect(self, player_name=None, url=None) -> None:
        self.joined_names.append(player_name)

    async def connect_server(self, url: str) -> None:
        self.connected_servers.append(url)

    async def join_room(self, name: str) -> None:
        self.joined_rooms.append(name)

    async def create_room(self, name: str) -> None:
        self.created_rooms.append(name)

    async def send(self, kind: ClientMsg, **payload) -> None:
        self.sent.append((kind, payload))

    async def exit_client(self) -> None:
        self.exited.append(True)

    async def exit_server(self) -> None:
        self.exited_servers.append(True)

    async def exit_game(self) -> None:
        self.exited_games.append(True)

    def set_feedback(self, message: str) -> None:
        raise AssertionError(message)

    def render_state(self) -> None:
        return None
