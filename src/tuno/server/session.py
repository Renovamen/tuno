"""Server-side coordinators that bind websocket connections to UNO rooms."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Dict, Optional

from tuno.core.game import GameError, GameState
from tuno.protocol.messages import encode_message
from tuno.server.actions import apply_action
from tuno.server.rooms import (
    ROOM_MESSAGES,
    room_list_from_states,
    validate_room_selection_payload,
)


@dataclass
class Connection:
    """Track one websocket and the player currently associated with it."""

    websocket: object
    player_id: Optional[str] = None


@dataclass
class RoomConnection:
    """Track one websocket before and after it selects a room."""

    websocket: object
    room_name: Optional[str] = None


class GameSession:
    """Wrap the authoritative game with websocket-oriented session behavior."""

    MAX_CONNECTIONS = 8

    def __init__(self) -> None:
        self.state = GameState()
        self.connections: Dict[object, Connection] = {}
        self._lock = asyncio.Lock()

    async def attach(self, websocket: object) -> bool:
        """Register a websocket and send its first info/state payloads."""
        if len(self.connections) >= self.MAX_CONNECTIONS:
            await self._send(websocket, "error", message="Server is at capacity.")

            close = getattr(websocket, "close", None)
            if callable(close):
                await close()

            return False

        self.connections[websocket] = Connection(websocket=websocket)

        await self.send_initial_state(websocket)
        return True

    async def send_initial_state(self, websocket: object) -> None:
        """Send the first info/state payloads for an already registered websocket."""
        await self._send(websocket, "info", message=ROOM_MESSAGES.connected_join)
        await self._broadcast_state()

    async def detach(self, websocket: object) -> None:
        """Remove a websocket and update game state if it owned a player slot."""
        async with self._lock:
            connection = self.connections.pop(websocket, None)
            if connection and connection.player_id:
                try:
                    self.state.remove_player(connection.player_id)
                except GameError:
                    pass
        await self._broadcast_state()

    async def handle(self, websocket: object, payload: dict) -> None:
        """Apply one validated client action to the authoritative game session."""
        async with self._lock:
            connection = self.connections[websocket]
            try:
                result = apply_action(self.state, connection.player_id, payload)
                connection.player_id = result.player_id
                if result.welcome_player_id:
                    await self._send(websocket, "welcome", player_id=result.welcome_player_id)
            except GameError as exc:
                await self._send(websocket, "error", message=str(exc), code=exc.code or "")
        await self._broadcast_state()

    async def _broadcast_state(self) -> None:
        """Push the latest snapshot to every live websocket, pruning stale peers."""
        stale = []
        for websocket, connection in list(self.connections.items()):
            try:
                await self._send(
                    websocket,
                    "state",
                    state=self.state.snapshot_for(connection.player_id).to_dict(),
                )
            except Exception:
                stale.append(websocket)
        for websocket in stale:
            self.connections.pop(websocket, None)

    async def _send(self, websocket: object, kind: str, **payload: object) -> None:
        """Encode and send one server message to a websocket."""
        await websocket.send(encode_message(kind, **payload))


class RoomServer:
    """Coordinate room selection before routing connections into game sessions."""

    MAX_ROOMS = 50

    def __init__(self) -> None:
        self.rooms: Dict[str, GameSession] = {}
        self.connections: Dict[object, RoomConnection] = {}
        self._lock = asyncio.Lock()

    async def attach(self, websocket: object) -> bool:
        """Register a websocket in room-selection mode."""
        self.connections[websocket] = RoomConnection(websocket=websocket)
        await self._send(websocket, "info", message=ROOM_MESSAGES.connected_choose)
        await self._send_room_list(websocket)
        return True

    async def detach(self, websocket: object) -> None:
        """Detach a websocket from its selected room or the room lobby."""
        room_name: Optional[str] = None
        async with self._lock:
            connection = self.connections.pop(websocket, None)
            if connection:
                room_name = connection.room_name

        if room_name:
            session = self.rooms.get(room_name)
            if session is not None:
                await session.detach(websocket)
                await self._delete_room_if_empty(room_name)

        await self._broadcast_room_list()

    async def handle(self, websocket: object, payload: dict) -> None:
        """Route room commands or in-room game actions for one websocket."""
        connection = self.connections[websocket]
        if connection.room_name is None:
            await self._handle_room_selection(websocket, payload)
            return

        if payload["type"] == "exit_room":
            await self._exit_room(websocket, connection)
            return

        session = self.rooms.get(connection.room_name)
        if session is None:
            connection.room_name = None
            await self._send(websocket, "info", message=ROOM_MESSAGES.closed)
            await self._send_room_list(websocket)
            return

        await session.handle(websocket, payload)
        if payload["type"] == "leave" and not session.state.players:
            await self._delete_room(connection.room_name)
            await self._broadcast_room_list()

    async def _handle_room_selection(self, websocket: object, payload: dict) -> None:
        validation = validate_room_selection_payload(payload)
        if validation.error_message:
            await self._send(websocket, "error", message=validation.error_message)
            return
        kind = validation.command
        room_name = validation.room_name

        async with self._lock:
            if kind == "create_room":
                if room_name in self.rooms:
                    await self._send(websocket, "error", message=ROOM_MESSAGES.name_exists)
                    return
                if len(self.rooms) >= self.MAX_ROOMS:
                    await self._send(websocket, "error", message=ROOM_MESSAGES.too_many)
                    return
                self.rooms[room_name] = GameSession()
            elif room_name not in self.rooms:
                await self._send(websocket, "error", message=ROOM_MESSAGES.not_found)
                return

            session = self.rooms[room_name]
            if len(session.connections) >= session.MAX_CONNECTIONS:
                if kind == "create_room" and not session.connections:
                    self.rooms.pop(room_name, None)
                await self._send(websocket, "error", message=ROOM_MESSAGES.at_capacity)
                close = getattr(websocket, "close", None)
                if callable(close):
                    await close()
                return

            self.connections[websocket].room_name = room_name
            session.connections[websocket] = Connection(websocket=websocket)

        await self._send(websocket, "room_joined", name=room_name)
        await session.send_initial_state(websocket)
        await self._broadcast_room_list()

    async def _exit_room(self, websocket: object, connection: RoomConnection) -> None:
        """Return one websocket to room-selection mode without closing it."""
        room_name = connection.room_name
        if room_name is None:
            await self._send(websocket, "error", message=ROOM_MESSAGES.choose_first)
            return

        session = self.rooms.get(room_name)
        connection.room_name = None
        if session is not None:
            await session.detach(websocket)
            await self._delete_room_if_empty(room_name)

        await self._send(websocket, "room_left", message=ROOM_MESSAGES.left)
        await self._send_room_list(websocket)
        await self._broadcast_room_list()

    async def _delete_room_if_empty(self, room_name: str) -> None:
        session = self.rooms.get(room_name)
        if session is not None and not session.connections:
            await self._delete_room(room_name)

    async def _delete_room(self, room_name: str) -> None:
        self.rooms.pop(room_name, None)
        for connection in self.connections.values():
            if connection.room_name == room_name:
                connection.room_name = None
                await self._send(
                    connection.websocket,
                    "room_closed",
                    message=ROOM_MESSAGES.closed,
                )
                await self._send_room_list(connection.websocket)

    async def _broadcast_room_list(self) -> None:
        for connection in list(self.connections.values()):
            if connection.room_name is None:
                await self._send_room_list(connection.websocket)

    async def _send_room_list(self, websocket: object) -> None:
        await self._send(websocket, "room_list", rooms=self.room_list())

    def room_list(self) -> list[dict[str, object]]:
        """Return public room metadata sorted by room name."""
        return room_list_from_states({name: session.state for name, session in self.rooms.items()})

    async def _send(self, websocket: object, kind: str, **payload: object) -> None:
        await websocket.send(encode_message(kind, **payload))
