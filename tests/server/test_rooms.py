from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from tuno.server.session import RoomServer

OPEN_WEBSOCKET_STATE = 1


class FakeWebSocket:
    def __init__(self) -> None:
        self.messages: list[dict] = []
        self.closed = False
        self.readyState = OPEN_WEBSOCKET_STATE
        self._attachment = ""

    async def send(self, raw: str) -> None:
        self.messages.append(json.loads(raw))

    async def close(self) -> None:
        self.closed = True
        self.readyState = 3

    def serializeAttachment(self, attachment: str) -> None:
        self._attachment = attachment

    def deserializeAttachment(self) -> str:
        return self._attachment


class FakeStorage:
    def __init__(self) -> None:
        self.values: dict[str, str] = {}

    async def get(self, key: str) -> str | None:
        return self.values.get(key)

    async def put(self, key: str, value: str) -> None:
        self.values[key] = value


class FakeDurableObjectContext:
    def __init__(self, websockets: list[FakeWebSocket]) -> None:
        self.websockets = websockets
        self.storage = FakeStorage()

    def getWebSockets(self) -> list[FakeWebSocket]:
        return self.websockets


class RoomServerTests(unittest.IsolatedAsyncioTestCase):
    """Cover standalone room selection and room lifecycle behavior."""

    async def test_create_room_enters_room_and_rejects_duplicate(self) -> None:
        server = RoomServer()
        first = FakeWebSocket()
        second = FakeWebSocket()

        await server.attach(first)
        await server.attach(second)
        await server.handle(first, {"type": "create_room", "name": "main"})
        await server.handle(second, {"type": "create_room", "name": "main"})

        self.assertIn("main", server.rooms)
        self.assertEqual(server.connections[first].room_name, "main")
        self.assertTrue(any(message["type"] == "room_joined" for message in first.messages))
        self.assertEqual(second.messages[-1]["type"], "error")
        self.assertEqual(second.messages[-1]["message"], "Room name already exists.")

    async def test_join_missing_room_is_rejected(self) -> None:
        server = RoomServer()
        websocket = FakeWebSocket()

        await server.attach(websocket)
        await server.handle(websocket, {"type": "join_room", "name": "missing"})

        self.assertIsNone(server.connections[websocket].room_name)
        self.assertEqual(websocket.messages[-1]["type"], "error")
        self.assertEqual(websocket.messages[-1]["message"], "Room does not exist.")

    async def test_room_is_deleted_after_last_player_leaves(self) -> None:
        server = RoomServer()
        websocket = FakeWebSocket()

        await server.attach(websocket)
        await server.handle(websocket, {"type": "create_room", "name": "main"})
        await server.handle(websocket, {"type": "join", "name": "alice"})
        self.assertIn("main", server.rooms)

        await server.handle(websocket, {"type": "leave"})

        self.assertNotIn("main", server.rooms)
        self.assertIsNone(server.connections[websocket].room_name)
        self.assertTrue(any(message["type"] == "room_closed" for message in websocket.messages))
        self.assertEqual(websocket.messages[-1]["type"], "room_list")

    async def test_room_capacity_rejects_without_room_joined_ack(self) -> None:
        server = RoomServer()
        first = FakeWebSocket()
        second = FakeWebSocket()

        await server.attach(first)
        await server.handle(first, {"type": "create_room", "name": "main"})
        server.rooms["main"].MAX_CONNECTIONS = 1

        await server.attach(second)
        await server.handle(second, {"type": "join_room", "name": "main"})

        self.assertIsNone(server.connections[second].room_name)
        self.assertFalse(any(message["type"] == "room_joined" for message in second.messages))
        self.assertEqual(second.messages[-1]["type"], "error")
        self.assertEqual(second.messages[-1]["message"], "Room is at capacity.")
        self.assertTrue(second.closed)


class WorkerLobbyLifecycleTests(unittest.IsolatedAsyncioTestCase):
    """Cover Worker room deletion decisions with lightweight fake sockets."""

    async def test_closing_one_non_player_socket_keeps_room_for_other_socket(self) -> None:
        from tuno.core.game import GameState
        from tuno.server.worker import TunoLobby

        closing = FakeWebSocket()
        staying = FakeWebSocket()
        closing.serializeAttachment(json.dumps({"room": "main", "player_id": ""}))
        staying.serializeAttachment(json.dumps({"room": "main", "player_id": ""}))
        closing.readyState = 3

        lobby = TunoLobby(FakeDurableObjectContext([closing, staying]), object())
        lobby.rooms = {"main": GameState()}
        lobby._loaded = True

        await lobby.webSocketClose(closing, 1000, "", True)

        self.assertIn("main", lobby.rooms)
