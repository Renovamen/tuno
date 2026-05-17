from __future__ import annotations

import unittest

from tuno.client.runtime import ClientRuntime
from tuno.core.snapshot import GameSnapshot


class RuntimeCallbacks:
    """Collect callback side effects so runtime tests can assert them directly."""

    def __init__(self) -> None:
        self.feedback: list[str] = []
        self.clear_count = 0
        self.exit_count = 0

    def set_feedback(self, message: str) -> None:
        self.feedback.append(message)

    def clear_pending(self) -> None:
        self.clear_count += 1

    def render_state(self) -> None:
        return None

    def exit_app(self) -> None:
        self.exit_count += 1


class FakeApi:
    """Small transport double that records runtime calls without opening websockets."""

    def __init__(self, url: str = "") -> None:
        self.url = url
        self.closed = False

    async def close(self) -> None:
        self.closed = True

    async def send(self, kind: str, **payload) -> None:
        self.sent = (kind, payload)


class ClientRuntimeTests(unittest.IsolatedAsyncioTestCase):
    """Cover non-widget client runtime behavior extracted from the Textual app."""

    def build_runtime(self, callbacks: RuntimeCallbacks) -> ClientRuntime:
        """Build a runtime wired to observable callbacks for isolated unit tests."""
        return ClientRuntime(
            set_feedback=callbacks.set_feedback,
            clear_pending_server_response=callbacks.clear_pending,
            render_state=callbacks.render_state,
            exit_app=callbacks.exit_app,
        )

    async def test_invalid_server_url_surfaces_feedback(self) -> None:
        """Reject non-websocket server URLs before opening a transport."""
        callbacks = RuntimeCallbacks()
        runtime = self.build_runtime(callbacks)

        # Step 1: Attempt to connect with an HTTP URL.
        await runtime.connect_server("http://example.test")

        # Step 2: The runtime should surface command feedback and leave transport closed.
        self.assertEqual(
            callbacks.feedback,
            ["Command error: /server requires a ws:// or wss:// URL."],
        )

    async def test_send_without_connection_surfaces_feedback(self) -> None:
        """Reject gameplay sends when no server websocket is connected."""
        callbacks = RuntimeCallbacks()
        runtime = self.build_runtime(callbacks)

        # Step 1: Send an action without installing an API transport.
        await runtime.send("start")

        # Step 2: The command layer should receive a local connection error.
        self.assertEqual(callbacks.feedback, ["Command error: Connect first."])

    async def test_exit_room_requires_selected_room(self) -> None:
        """Reject `/exit_room` before the websocket has selected a room."""
        callbacks = RuntimeCallbacks()
        runtime = self.build_runtime(callbacks)
        runtime.api = FakeApi()  # type: ignore[assignment]

        await runtime.send("exit_room")

        self.assertEqual(
            callbacks.feedback,
            ["Command error: Connect to a room first with /connect <room>."],
        )

    async def test_join_game_requires_selected_room(self) -> None:
        """Require room selection before `/join <player_name>` sends a join action."""
        callbacks = RuntimeCallbacks()
        runtime = self.build_runtime(callbacks)
        runtime.api = FakeApi()  # type: ignore[assignment]

        # Step 1: Try to join a player while connected but still in room selection.
        await runtime.connect(player_name="alice")

        # Step 2: The runtime should block the join before sending to the server.
        self.assertEqual(
            callbacks.feedback,
            ["Command error: Choose a room first with /connect or /create."],
        )

    async def test_room_commands_send_protocol_messages(self) -> None:
        """Map `/create` and room `/connect` commands to room protocol messages."""
        callbacks = RuntimeCallbacks()
        runtime = self.build_runtime(callbacks)
        api = FakeApi()
        runtime.api = api  # type: ignore[assignment]

        # Step 1: Creating a room should send the create_room protocol envelope.
        await runtime.create_room("main")
        self.assertEqual(api.sent, ("create_room", {"name": "main"}))

        # Step 2: Joining a room should send the join_room protocol envelope.
        await runtime.join_room("main")
        self.assertEqual(api.sent, ("join_room", {"name": "main"}))

    async def test_handle_messages_updates_state_and_feedback(self) -> None:
        """Apply core server messages to player id, snapshot state, and feedback."""
        callbacks = RuntimeCallbacks()
        runtime = self.build_runtime(callbacks)
        runtime.state = GameSnapshot(current_color="red", top_card={"short": "R:5"})

        # Step 1: Welcome should bind this client to the server-assigned player id.
        await runtime.handle_message({"type": "welcome", "player_id": "p1"})

        # Step 2: State should replace the current snapshot and clear pending feedback.
        await runtime.handle_message({"type": "state", "state": {"started": True}})

        # Step 3: Error should be formatted with the previous snapshot context.
        await runtime.handle_message(
            {
                "type": "error",
                "code": "illegal_play",
                "message": "That card cannot be played.",
            }
        )

        self.assertEqual(runtime.player_id, "p1")
        self.assertEqual(runtime.state, GameSnapshot(started=True))
        self.assertEqual(callbacks.clear_count, 2)
        self.assertIn("Illegal play:", callbacks.feedback[-1])

    async def test_handle_room_messages_updates_room_state(self) -> None:
        """Apply lobby messages that list rooms and select the active room."""
        callbacks = RuntimeCallbacks()
        runtime = self.build_runtime(callbacks)

        # Step 1: Room list messages update the local lobby table.
        await runtime.handle_message(
            {
                "type": "room_list",
                "rooms": [{"name": "main", "status": "Lobby", "player_count": 0}],
            }
        )

        # Step 2: Room joined messages select the room but do not create a player.
        await runtime.handle_message({"type": "room_joined", "name": "main"})

        self.assertEqual(runtime.rooms[0]["name"], "main")
        self.assertEqual(runtime.selected_room_name, "main")
        self.assertIsNone(runtime.player_id)
        self.assertEqual(runtime.state, GameSnapshot())

    async def test_room_closed_message_returns_to_room_lobby(self) -> None:
        """Clear room-scoped player and game state after leaving or closing a room."""
        callbacks = RuntimeCallbacks()
        runtime = self.build_runtime(callbacks)
        runtime.selected_room_name = "main"
        runtime.player_id = "p1"
        runtime.state = GameSnapshot(started=True)
        runtime.say_uno_next = True

        # Step 1: Simulate the server closing the selected room.
        await runtime.handle_message({"type": "room_left", "message": "Left room."})

        # Step 2: The client should return to room-selection state.
        self.assertIsNone(runtime.selected_room_name)
        self.assertIsNone(runtime.player_id)
        self.assertEqual(runtime.state, GameSnapshot())
        self.assertFalse(runtime.say_uno_next)

    async def test_close_current_server_resets_runtime_state(self) -> None:
        """Close the active transport and clear all server-scoped runtime state."""
        callbacks = RuntimeCallbacks()
        runtime = self.build_runtime(callbacks)
        api = FakeApi()
        runtime.api = api  # type: ignore[assignment]
        runtime.player_id = "p1"
        runtime.state = GameSnapshot(started=True)
        runtime.say_uno_next = True

        # Step 1: Close the current server connection.
        await runtime.close_current_server()

        # Step 2: Runtime state and the fake transport should both show cleanup.
        self.assertIsNone(runtime.api)
        self.assertIsNone(runtime.player_id)
        self.assertEqual(runtime.state, GameSnapshot())
        self.assertFalse(runtime.say_uno_next)
        self.assertTrue(api.closed)

    async def test_exit_game_leaves_round_but_keeps_room(self) -> None:
        """Send leave and clear local player identity while keeping the room connection."""
        callbacks = RuntimeCallbacks()
        runtime = self.build_runtime(callbacks)
        api = FakeApi()
        runtime.api = api  # type: ignore[assignment]
        runtime.selected_room_name = "main"
        runtime.player_id = "p1"
        runtime.state = GameSnapshot(started=True, finished=False)
        runtime.say_uno_next = True

        await runtime.exit_game()

        self.assertEqual(api.sent, ("leave", {}))
        self.assertIsNone(runtime.player_id)
        self.assertFalse(runtime.say_uno_next)
        self.assertEqual(runtime.selected_room_name, "main")
        self.assertIs(runtime.api, api)
        self.assertFalse(api.closed)

    async def test_exit_game_rejected_outside_active_round(self) -> None:
        """Reject /exit_game in the lobby or after the round has finished."""
        callbacks = RuntimeCallbacks()
        runtime = self.build_runtime(callbacks)
        api = FakeApi()
        runtime.api = api  # type: ignore[assignment]
        runtime.selected_room_name = "main"
        runtime.player_id = "p1"
        runtime.state = GameSnapshot(started=True, finished=True)

        await runtime.exit_game()

        self.assertEqual(
            callbacks.feedback[-1],
            "Command error: /exit_game is only allowed during an active game.",
        )
        self.assertEqual(runtime.player_id, "p1")
        self.assertFalse(hasattr(api, "sent"))
