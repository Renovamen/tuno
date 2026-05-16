"""Cloudflare Worker adapter.

This module targets Cloudflare's Python Worker + Durable Object runtime. It mirrors
local-server semantics while accounting for Worker-specific persistence and
WebSocket hibernation:

``TunoLobby`` is the room-aware Durable Object. It owns the room list and a
``GameState`` per room, so clients can create or join rooms before joining a game.

The pure Python game engine remains the source of truth for UNO rules.
"""

from __future__ import annotations

import json

from workers import DurableObject, Response, WorkerEntrypoint

from tuno.core.game import GameError, GameState
from tuno.core.game_storage import deserialize_game, serialize_game
from tuno.protocol.messages import MAX_MESSAGE_SIZE, ProtocolError, decode_client_message
from tuno.server.actions import apply_action
from tuno.server.rooms import (
    ROOM_MESSAGES,
    room_list_from_states,
    validate_room_selection_payload,
)

DEFAULT_LOBBY_ID = "default-lobby"
OPEN_WEBSOCKET_STATE = 1
WORKER_GAME_STORAGE_KEYS = (
    "seed",
    "players",
    "started",
    "finished",
    "winner_id",
    "current_player_index",
    "direction",
    "current_color",
    "status_message",
    "recent_events",
    "has_drawn_this_turn",
    "draw_pile",
    "discard_pile",
    "drawn_card",
    "next_player_serial",
    "rng_state",
)


class TunoLobby(DurableObject):
    """Own room selection and room-scoped game state for the default Worker endpoint.

    A single lobby Durable Object tracks room metadata and one ``GameState`` per room.
    Websocket attachments store the selected room and player id so hibernated sockets
    can resume without relying on process memory.
    """

    MAX_ROOMS = 50
    STORAGE_KEY = "rooms"

    def __init__(self, ctx, env):
        """Create the in-memory room map for this lobby Durable Object instance."""
        super().__init__(ctx, env)
        self.rooms: dict[str, GameState] = {}
        self._loaded = False

    async def fetch(self, request):
        """Accept a lobby websocket upgrade and send the current room list."""
        from js import WebSocketPair

        await self._ensure_loaded()

        # The lobby endpoint is websocket-only because all room selection happens over
        # the shared JSON websocket protocol.
        upgrade = request.headers.get("Upgrade", "")
        if upgrade.lower() != "websocket":
            return Response("Expected websocket upgrade.", status=426)

        # Store both room and player_id in the attachment. Empty strings mean the client
        # is connected to the lobby but has not selected a room or joined a game yet.
        client_socket, server_socket = WebSocketPair.new().object_values()
        self.ctx.acceptWebSocket(server_socket)
        server_socket.serializeAttachment(json.dumps({"room": "", "player_id": ""}))

        self._send_json(server_socket, {"type": "info", "message": ROOM_MESSAGES.connected_choose})
        await self._send_room_list(server_socket)
        return Response(status=101, web_socket=client_socket)

    async def webSocketMessage(self, ws, message):
        """Route one lobby websocket message to room selection or in-room game play."""
        await self._ensure_loaded()

        if len(message) > MAX_MESSAGE_SIZE:
            self._send_json(ws, {"type": "error", "message": "Message is too large."})
            return

        try:
            payload = decode_client_message(str(message))
            attachment = self._attachment_for(ws)
            # Before a room is selected, only room commands are legal. After selection,
            # the same websocket carries normal game actions for that room.
            if not attachment.get("room"):
                await self._handle_room_selection(ws, payload)
            else:
                await self._handle_room_action(ws, payload, attachment)
        except ProtocolError as exc:
            self._send_json(ws, {"type": "error", "message": str(exc)})
        except GameError as exc:
            self._send_json(
                ws,
                {
                    "type": "error",
                    "message": str(exc),
                    "code": exc.code or "",
                },
            )

        await self._save_rooms()
        await self._broadcast_room_list()

    async def webSocketClose(self, ws, code, reason, wasClean):
        """Remove the closing websocket's player and delete the room if it is empty."""
        await self._ensure_loaded()

        attachment = self._attachment_for(ws)
        room_name = attachment.get("room")
        player_id = attachment.get("player_id")
        game = self.rooms.get(room_name or "")

        if game is not None and player_id:
            try:
                game.remove_player(player_id)
            except GameError:
                # The socket may contain stale hibernation metadata. Ignore the stale
                # leave but still run room cleanup and room-list broadcast below.
                pass

        if room_name:
            await self._delete_room_if_empty(room_name)

        await self._save_rooms()
        await self._broadcast_room_list()

    async def _handle_room_selection(self, ws, payload: dict) -> None:
        """Create or join a room before the websocket can send game actions."""
        validation = validate_room_selection_payload(payload)
        if validation.error_message:
            self._send_json(ws, {"type": "error", "message": validation.error_message})
            return
        kind = validation.command
        room_name = validation.room_name

        if kind == "create_room":
            # Room names are the unique keys in the lobby's persisted room map.
            if room_name in self.rooms:
                self._send_json(ws, {"type": "error", "message": ROOM_MESSAGES.name_exists})
                return
            if len(self.rooms) >= self.MAX_ROOMS:
                self._send_json(ws, {"type": "error", "message": ROOM_MESSAGES.too_many})
                return
            self.rooms[room_name] = GameState()
        elif room_name not in self.rooms:
            self._send_json(ws, {"type": "error", "message": ROOM_MESSAGES.not_found})
            return

        # Selecting a room does not create a player. The user still runs /join <name>
        # afterward, matching the standalone server flow.
        ws.serializeAttachment(json.dumps({"room": room_name, "player_id": ""}))
        self._send_json(ws, {"type": "room_joined", "name": room_name})
        self._send_json(ws, {"type": "info", "message": ROOM_MESSAGES.connected_join})
        await self._send_state(ws)

    async def _handle_room_action(self, ws, payload: dict, attachment: dict) -> None:
        """Apply one normal game action inside the selected room."""
        room_name = str(attachment["room"])
        game = self.rooms.get(room_name)
        if game is None:
            # The room may have been deleted because everyone left. Return this socket to
            # room-selection mode instead of allowing it to keep sending game actions.
            ws.serializeAttachment(json.dumps({"room": "", "player_id": ""}))
            self._send_json(ws, {"type": "info", "message": ROOM_MESSAGES.closed})
            await self._send_room_list(ws)
            return

        if payload["type"] == "exit_room":
            await self._exit_room(ws, room_name, game, attachment)
            return

        result = apply_action(game, attachment.get("player_id") or None, payload)
        # Persist the player id in the socket attachment so future messages and
        # hibernation wake-ups can identify the same player.
        ws.serializeAttachment(json.dumps({"room": room_name, "player_id": result.player_id or ""}))
        if result.welcome_player_id:
            self._send_json(ws, {"type": "welcome", "player_id": result.welcome_player_id})

        await self._broadcast_state(room_name)
        if payload["type"] == "leave" and not game.players:
            # A deliberate /leave by the last player closes the room immediately and
            # returns any remaining room sockets to the room list.
            await self._delete_room(room_name)

    async def _exit_room(self, ws, room_name: str, game: GameState, attachment: dict) -> None:
        """Return one websocket to room-selection mode without closing it."""
        player_id = attachment.get("player_id")
        if player_id:
            try:
                game.remove_player(player_id)
            except GameError:
                # The attachment may be stale after hibernation; leaving the room should
                # still return the socket to room-selection mode.
                pass

        ws.serializeAttachment(json.dumps({"room": "", "player_id": ""}))
        self._send_json(ws, {"type": "room_left", "message": ROOM_MESSAGES.left})
        await self._send_room_list(ws)
        await self._broadcast_state(room_name)
        await self._delete_room_if_empty(room_name)

    async def _broadcast_state(self, room_name: str) -> None:
        """Send fresh game snapshots to every open websocket in one room."""
        for websocket in self._open_websockets():
            attachment = self._attachment_for(websocket)
            if attachment.get("room") == room_name:
                await self._send_state(websocket)

    async def _send_state(self, websocket) -> None:
        """Send one player-specific room game snapshot to a websocket."""
        attachment = self._attachment_for(websocket)
        game = self.rooms.get(str(attachment.get("room", "")))
        if game is None:
            return
        self._send_json(
            websocket,
            {
                "type": "state",
                "state": game.snapshot_for(attachment.get("player_id") or None),
            },
        )

    async def _delete_room_if_empty(self, room_name: str) -> None:
        """Delete a room only after no open websocket remains attached to it."""
        has_socket = any(
            self._attachment_for(ws).get("room") == room_name for ws in self._open_websockets()
        )
        if room_name in self.rooms and not has_socket:
            await self._delete_room(room_name)

    async def _delete_room(self, room_name: str) -> None:
        """Remove a room and notify any remaining sockets that were attached to it."""
        self.rooms.pop(room_name, None)
        for websocket in self._open_websockets():
            attachment = self._attachment_for(websocket)
            if attachment.get("room") != room_name:
                continue
            websocket.serializeAttachment(json.dumps({"room": "", "player_id": ""}))
            self._send_json(
                websocket,
                {
                    "type": "room_closed",
                    "message": ROOM_MESSAGES.closed,
                },
            )
            await self._send_room_list(websocket)

    async def _broadcast_room_list(self) -> None:
        """Send room-list updates to sockets that are still in room-selection mode."""
        for websocket in self._open_websockets():
            if not self._attachment_for(websocket).get("room"):
                await self._send_room_list(websocket)

    async def _send_room_list(self, websocket) -> None:
        """Send the current public room list to one websocket."""
        self._send_json(websocket, {"type": "room_list", "rooms": self._room_list()})

    def _room_list(self) -> list[dict]:
        """Build sorted public room metadata for lobby clients."""
        return room_list_from_states(self.rooms)

    def _attachment_for(self, websocket) -> dict:
        """Read room/player metadata from a hibernatable websocket attachment."""
        attachment = websocket.deserializeAttachment()
        if not attachment:
            return {"room": "", "player_id": ""}
        try:
            payload = json.loads(str(attachment))
        except json.JSONDecodeError:
            # Malformed or obsolete attachments cannot identify a selected room, so keep
            # the socket in room-selection mode and preserve the raw player token.
            return {"room": "", "player_id": str(attachment)}
        return {
            "room": str(payload.get("room", "")),
            "player_id": str(payload.get("player_id", "")),
        }

    def _send_json(self, websocket, payload: dict) -> None:
        """Serialize and send one JSON payload to a lobby websocket."""
        websocket.send(json.dumps(payload))

    async def _ensure_loaded(self) -> None:
        """Load the persisted room map once after object creation or wake-up."""
        if self._loaded:
            return

        payload = await self.ctx.storage.get(self.STORAGE_KEY)
        if payload:
            # Storage contains a JSON object keyed by room name. Each value is the same
            # GameState payload format this lobby writes in _save_rooms.
            serialized = json.loads(str(payload))
            self.rooms = {
                name: deserialize_game(game_payload, WORKER_GAME_STORAGE_KEYS)
                for name, game_payload in serialized.get("rooms", {}).items()
            }
        await self._reset_stale_rooms_if_needed()
        self._loaded = True

    async def _save_rooms(self) -> None:
        """Persist every room's authoritative game state to Durable Object storage."""
        await self.ctx.storage.put(
            self.STORAGE_KEY,
            json.dumps(
                {
                    "rooms": {
                        name: serialize_game(game, WORKER_GAME_STORAGE_KEYS)
                        for name, game in self.rooms.items()
                    }
                }
            ),
        )

    async def _reset_stale_rooms_if_needed(self) -> None:
        """Clear persisted rooms when the lobby wakes up with no live websockets."""
        if self._open_websockets():
            return
        if not self.rooms:
            return
        self.rooms = {}
        await self._save_rooms()

    def _open_websockets(self) -> list:
        """Return only currently open lobby Durable Object websockets."""
        return [
            ws
            for ws in self.ctx.getWebSockets()
            if getattr(ws, "readyState", 0) == OPEN_WEBSOCKET_STATE
        ]


class Default(WorkerEntrypoint):
    """Top-level Worker entrypoint that routes all requests to the room lobby."""

    async def fetch(self, request):
        """Route every Worker request to the room-aware lobby Durable Object."""
        stub = self.env.TUNO_LOBBY.getByName(DEFAULT_LOBBY_ID)
        return await stub.fetch(request)
