from __future__ import annotations

import json
import sys
import types
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from tuno.server.session import RoomServer

OPEN_WEBSOCKET_STATE = 1


class AwaitableNone:
    """No-op awaitable returned by FakeWebSocket.send for sync and async callers."""

    def __await__(self):
        if False:
            yield None
        return None


class FakeWebSocket:
    """Test double shared by standalone websocket tests and Worker hibernation tests."""

    def __init__(self) -> None:
        # Standalone tests inspect decoded outbound protocol messages.
        self.messages: list[dict] = []
        self.closed = False
        # Worker tests use readyState to decide whether a socket is still open.
        self.readyState = OPEN_WEBSOCKET_STATE
        # Worker tests use serialized attachments to model hibernatable socket metadata.
        self._attachment = ""

    def send(self, raw: str) -> AwaitableNone:
        """Record one JSON protocol message and remain awaitable for standalone code."""
        self.messages.append(json.loads(raw))
        return AwaitableNone()

    async def close(self) -> None:
        """Mark the fake socket closed when capacity checks reject a connection."""
        self.closed = True
        self.readyState = 3

    def serializeAttachment(self, attachment: str) -> None:
        """Store Worker-style websocket attachment metadata."""
        self._attachment = attachment

    def deserializeAttachment(self) -> str:
        """Return Worker-style websocket attachment metadata."""
        return self._attachment


class FakeStorage:
    """Minimal Durable Object storage double used by Worker lobby tests."""

    def __init__(self) -> None:
        self.values: dict[str, str] = {}

    async def get(self, key: str) -> str | None:
        """Return a stored value or None, matching the async Worker storage API."""
        return self.values.get(key)

    async def put(self, key: str, value: str) -> None:
        """Persist a value in memory for Worker storage tests."""
        self.values[key] = value


class FakeDurableObjectContext:
    """Minimal Durable Object context exposing storage and hibernated websockets."""

    def __init__(self, websockets: list[FakeWebSocket]) -> None:
        self.websockets = websockets
        self.storage = FakeStorage()

    def getWebSockets(self) -> list[FakeWebSocket]:
        """Return sockets that the Worker lobby should consider for broadcasts/cleanup."""
        return self.websockets


def install_worker_runtime_stub() -> None:
    """Provide the minimal workers runtime surface needed by Worker unit tests."""
    workers_module = types.ModuleType("workers")

    class DurableObject:
        def __init__(self, ctx, env):
            self.ctx = ctx
            self.env = env

    class Response:
        def __init__(self, body=None, *, status=200, web_socket=None):
            self.body = body
            self.status = status
            self.web_socket = web_socket

    class WorkerEntrypoint:
        pass

    workers_module.DurableObject = DurableObject
    workers_module.Response = Response
    workers_module.WorkerEntrypoint = WorkerEntrypoint
    sys.modules["workers"] = workers_module


class RoomServerTests(unittest.IsolatedAsyncioTestCase):
    """Cover standalone room selection and room lifecycle behavior."""

    async def test_create_room_enters_room_and_rejects_duplicate(self) -> None:
        """Create one room, enter it, and reject a second room with the same name."""
        server = RoomServer()
        first = FakeWebSocket()
        second = FakeWebSocket()

        # Step 1: Attach two clients that are both still in room-selection mode.
        await server.attach(first)
        await server.attach(second)

        # Step 2: The first client creates/selects the room; the second collides by name.
        await server.handle(first, {"type": "create_room", "name": "main"})
        await server.handle(second, {"type": "create_room", "name": "main"})

        # Step 3: Only the first client should enter the room; the second gets an error.
        self.assertIn("main", server.rooms)
        self.assertEqual(server.connections[first].room_name, "main")
        self.assertTrue(any(message["type"] == "room_joined" for message in first.messages))
        self.assertEqual(second.messages[-1]["type"], "error")
        self.assertEqual(second.messages[-1]["message"], "Room name already exists.")

    async def test_join_missing_room_is_rejected(self) -> None:
        """Reject joining a room name that does not exist."""
        server = RoomServer()
        websocket = FakeWebSocket()

        # Step 1: Attach one client and ask it to select an absent room.
        await server.attach(websocket)
        await server.handle(websocket, {"type": "join_room", "name": "missing"})

        # Step 2: The client should remain in room-selection mode and receive an error.
        self.assertIsNone(server.connections[websocket].room_name)
        self.assertEqual(websocket.messages[-1]["type"], "error")
        self.assertEqual(websocket.messages[-1]["message"], "Room does not exist.")

    async def test_room_is_deleted_after_last_player_leaves(self) -> None:
        """Delete a room when its only player leaves through the game leave action."""
        server = RoomServer()
        websocket = FakeWebSocket()

        # Step 1: Create a room and join its game as the only player.
        await server.attach(websocket)
        await server.handle(websocket, {"type": "create_room", "name": "main"})
        await server.handle(websocket, {"type": "join", "name": "alice"})
        self.assertIn("main", server.rooms)

        # Step 2: The player's normal game leave action should empty the room.
        await server.handle(websocket, {"type": "leave"})

        # Step 3: Empty rooms are removed and the socket returns to the room list.
        self.assertNotIn("main", server.rooms)
        self.assertIsNone(server.connections[websocket].room_name)
        self.assertTrue(any(message["type"] == "room_closed" for message in websocket.messages))
        self.assertEqual(websocket.messages[-1]["type"], "room_list")

    async def test_room_capacity_rejects_without_room_joined_ack(self) -> None:
        """Reject room selection when the target GameSession has no connection slots."""
        server = RoomServer()
        first = FakeWebSocket()
        second = FakeWebSocket()

        # Step 1: Create a room and force its capacity down to the existing connection.
        await server.attach(first)
        await server.handle(first, {"type": "create_room", "name": "main"})
        server.rooms["main"].MAX_CONNECTIONS = 1

        # Step 2: A second client tries to select the full room.
        await server.attach(second)
        await server.handle(second, {"type": "join_room", "name": "main"})

        # Step 3: The second client must not receive room_joined and should be closed.
        self.assertIsNone(server.connections[second].room_name)
        self.assertFalse(any(message["type"] == "room_joined" for message in second.messages))
        self.assertEqual(second.messages[-1]["type"], "error")
        self.assertEqual(second.messages[-1]["message"], "Room is at capacity.")
        self.assertTrue(second.closed)

    async def test_exit_room_returns_socket_to_room_lobby(self) -> None:
        """Leave one populated room with /exit_room without closing the websocket."""
        server = RoomServer()
        first = FakeWebSocket()
        second = FakeWebSocket()

        # Step 1: Put two players into the same room so it should survive one exit.
        await server.attach(first)
        await server.handle(first, {"type": "create_room", "name": "main"})
        await server.handle(first, {"type": "join", "name": "alice"})
        await server.attach(second)
        await server.handle(second, {"type": "join_room", "name": "main"})
        await server.handle(second, {"type": "join", "name": "bob"})

        # Step 2: The first socket leaves the room but keeps the server connection open.
        await server.handle(first, {"type": "exit_room"})

        # Step 3: The room remains for Bob, while Alice returns to the room lobby.
        self.assertIn("main", server.rooms)
        self.assertIsNone(server.connections[first].room_name)
        self.assertEqual(len(server.rooms["main"].state.players), 1)
        self.assertTrue(any(message["type"] == "room_left" for message in first.messages))
        self.assertEqual(first.messages[-1]["type"], "room_list")

    async def test_exit_room_deletes_empty_room(self) -> None:
        """Delete a selected room when /exit_room leaves it with no sockets."""
        server = RoomServer()
        websocket = FakeWebSocket()

        # Step 1: Create/select a room but do not add any other sockets to it.
        await server.attach(websocket)
        await server.handle(websocket, {"type": "create_room", "name": "main"})

        # Step 2: Leaving the selected room makes it empty.
        await server.handle(websocket, {"type": "exit_room"})

        # Step 3: The room is removed and the socket is back in room-selection mode.
        self.assertNotIn("main", server.rooms)
        self.assertIsNone(server.connections[websocket].room_name)
        self.assertTrue(any(message["type"] == "room_left" for message in websocket.messages))


class WorkerLobbyLifecycleTests(unittest.IsolatedAsyncioTestCase):
    """Cover Worker room deletion decisions with lightweight fake sockets."""

    async def test_closing_one_non_player_socket_keeps_room_for_other_socket(self) -> None:
        """Keep a Worker room alive when a closing spectator socket is not the last socket."""
        from tuno.core.game import GameState

        install_worker_runtime_stub()
        from tuno.server.worker import TunoLobby

        # Step 1: Model two hibernated Worker sockets attached to the same room.
        closing = FakeWebSocket()
        staying = FakeWebSocket()
        closing.serializeAttachment(json.dumps({"room": "main", "player_id": ""}))
        staying.serializeAttachment(json.dumps({"room": "main", "player_id": ""}))
        closing.readyState = 3

        # Step 2: Seed the Worker lobby with an already-loaded room.
        lobby = TunoLobby(FakeDurableObjectContext([closing, staying]), object())
        lobby.rooms = {"main": GameState()}
        lobby._loaded = True

        # Step 3: Closing one non-player socket should not delete the still-attached room.
        await lobby.webSocketClose(closing, 1000, "", True)

        self.assertIn("main", lobby.rooms)

    async def test_exit_room_returns_worker_socket_to_room_lobby(self) -> None:
        """Handle Worker /exit_room by clearing attachment metadata and removing player."""
        from tuno.core.game import GameState

        install_worker_runtime_stub()
        from tuno.server.worker import TunoLobby

        # Step 1: Seed one Worker room with two players and two attached sockets.
        leaving = FakeWebSocket()
        staying = FakeWebSocket()
        game = GameState()
        player_id = game.add_player("alice")
        game.add_player("bob")
        leaving.serializeAttachment(json.dumps({"room": "main", "player_id": player_id}))
        staying.serializeAttachment(json.dumps({"room": "main", "player_id": ""}))

        # Step 2: Build an already-loaded Worker lobby around the fake hibernated sockets.
        lobby = TunoLobby(FakeDurableObjectContext([leaving, staying]), object())
        lobby.rooms = {"main": game}
        lobby._loaded = True

        # Step 3: Alice exits the room through the Worker websocket message path.
        await lobby.webSocketMessage(leaving, json.dumps({"type": "exit_room"}))

        # Step 4: The room remains for Bob and Alice's socket returns to room lobby mode.
        self.assertIn("main", lobby.rooms)
        self.assertEqual(json.loads(leaving.deserializeAttachment()), {"room": "", "player_id": ""})
        self.assertEqual(len(lobby.rooms["main"].players), 1)
        self.assertTrue(any(message["type"] == "room_left" for message in leaving.messages))
