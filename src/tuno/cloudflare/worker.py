"""Cloudflare Worker adapter.

This module targets Cloudflare's Python Worker + Durable Object runtime. It mirrors
local-server semantics at a high level: one Durable Object instance owns one game.
The pure Python game engine remains the source of truth for rules.
"""

from __future__ import annotations

import json
from typing import Optional
from urllib.parse import parse_qs, urlparse

from workers import DurableObject, Response, WorkerEntrypoint

from tuno.core.cards import Card
from tuno.core.game import MAX_PLAYERS, GameError, GameState, PlayerState
from tuno.protocol.messages import MAX_MESSAGE_SIZE, ProtocolError, decode_client_message
from tuno.server.actions import apply_action


class TunoGame(DurableObject):
    MAX_CONNECTIONS = MAX_PLAYERS + 3
    STORAGE_KEY = "game-state"

    def __init__(self, ctx, env):
        super().__init__(ctx, env)
        # This is only the live in-memory copy for the current Durable Object instance.
        # A Worker restart / wake-up can recreate the object at any time, so the real
        # cross-request game state must be restored from and persisted back to storage.
        self.game = GameState()
        self._loaded = False

    async def fetch(self, request):
        from js import WebSocketPair

        await self._ensure_loaded()

        upgrade = request.headers.get("Upgrade", "")
        if upgrade.lower() != "websocket":
            return Response("Expected websocket upgrade.", status=426)
        if len(self._open_websockets()) >= self.MAX_CONNECTIONS:
            return Response("Server is at capacity.", status=503)

        client_socket, server_socket = WebSocketPair.new().object_values()
        self.ctx.acceptWebSocket(server_socket)
        # Attach only a cloneable player_id string to the websocket. This is connection
        # metadata for hibernation/reconnect handling, not the authoritative game state.
        server_socket.serializeAttachment("")

        self._send_json(
            server_socket,
            {
                "type": "info",
                "message": "Connected. Join with your player name.",
            },
        )

        await self._broadcast_state()
        return Response(status=101, web_socket=client_socket)

    async def webSocketMessage(self, ws, message):
        await self._ensure_loaded()

        if len(message) > MAX_MESSAGE_SIZE:
            self._send_json(ws, {"type": "error", "message": "Message is too large."})
            return

        try:
            await self._apply_client_message(ws, str(message))
            await self._save_game()
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

        await self._broadcast_state()

    async def webSocketClose(self, ws, code, reason, wasClean):
        await self._ensure_loaded()

        player_id = self._player_id_for(ws)

        if player_id:
            try:
                self.game.remove_player(player_id)
                await self._save_game()
            except GameError:
                pass

        await self._broadcast_state()

    async def _broadcast_state(self):
        for websocket in self._open_websockets():
            player_id = self._player_id_for(websocket)
            try:
                self._send_json(
                    websocket,
                    {
                        "type": "state",
                        "state": self.game.snapshot_for(player_id),
                    },
                )
            except Exception:
                continue

    def _player_id_for(self, websocket) -> Optional[str]:
        """Look up the player id stored on a hibernatable websocket attachment."""
        attachment = websocket.deserializeAttachment()
        if not attachment:
            return None
        return str(attachment)

    async def _apply_client_message(self, websocket, message: str) -> None:
        """Decode one client message, apply it to game state, and update socket attachment."""
        payload = decode_client_message(message)
        result = apply_action(self.game, self._player_id_for(websocket), payload)
        websocket.serializeAttachment(result.player_id or "")
        if result.welcome_player_id:
            self._send_json(
                websocket,
                {
                    "type": "welcome",
                    "player_id": result.welcome_player_id,
                },
            )

    def _send_json(self, websocket, payload: dict) -> None:
        """Serialize and send one JSON payload to a worker websocket."""
        websocket.send(json.dumps(payload))

    async def _ensure_loaded(self) -> None:
        """Load durable game state once after object creation or wake-up.

        Durable Objects preserve identity, but not Python process memory. If this object is
        re-created mid-game, self.game would otherwise fall back to a blank GameState().
        """
        if self._loaded:
            return

        payload = await self.ctx.storage.get(self.STORAGE_KEY)
        if payload:
            self.game = self._deserialize_game(json.loads(str(payload)))

        await self._reset_stale_session_if_needed()
        self._loaded = True

    async def _save_game(self) -> None:
        """Persist the current authoritative game state to Durable Object storage.

        Use JSON rather than raw Python dicts because the Cloudflare Python runtime only
        accepts cloneable storage values.
        """
        await self.ctx.storage.put(self.STORAGE_KEY, json.dumps(self._serialize_game()))

    def _serialize_game(self) -> dict:
        """Convert the authoritative game state into a storage-friendly payload."""
        return {
            "seed": self.game.seed,
            "players": [
                {
                    "player_id": player.player_id,
                    "name": player.name,
                    "hand": [card.to_dict() for card in player.hand],
                }
                for player in self.game.players
            ],
            "started": self.game.started,
            "finished": self.game.finished,
            "winner_id": self.game.winner_id,
            "current_player_index": self.game.current_player_index,
            "direction": self.game.direction,
            "draw_pile": [card.to_dict() for card in self.game.draw_pile],
            "discard_pile": [card.to_dict() for card in self.game.discard_pile],
            "current_color": self.game.current_color,
            "status_message": self.game.status_message,
            "recent_events": list(self.game.recent_events),
            "has_drawn_this_turn": self.game.has_drawn_this_turn,
            "drawn_card": self.game.drawn_card.to_dict() if self.game.drawn_card else None,
            "next_player_serial": self.game._next_player_serial,
            "rng_state": self.game._rng.state,
        }

    def _deserialize_game(self, payload: dict) -> GameState:
        """Rebuild a GameState from a payload previously stored in Durable Object storage."""
        game = GameState(seed=payload["seed"])

        game.players = [
            PlayerState(
                player_id=player["player_id"],
                name=player["name"],
                hand=[Card.from_dict(card) for card in player.get("hand", [])],
            )
            for player in payload.get("players", [])
        ]

        game.started = payload.get("started", False)
        game.finished = payload.get("finished", False)
        game.winner_id = payload.get("winner_id")

        game.current_player_index = payload.get("current_player_index", 0)
        game.direction = payload.get("direction", 1)
        game.draw_pile = [Card.from_dict(card) for card in payload.get("draw_pile", [])]
        game.discard_pile = [Card.from_dict(card) for card in payload.get("discard_pile", [])]
        game.current_color = payload.get("current_color")

        game.status_message = payload.get("status_message", game.status_message)
        game.recent_events = list(payload.get("recent_events", game.recent_events))

        drawn_card = payload.get("drawn_card")
        game.drawn_card = Card.from_dict(drawn_card) if drawn_card else None

        game.has_drawn_this_turn = payload.get("has_drawn_this_turn", False)
        game._next_player_serial = payload.get("next_player_serial", 1)
        game._rng.state = payload.get("rng_state", game._rng.state)

        return game

    async def _reset_stale_session_if_needed(self) -> None:
        """Drop persisted round state when no live websockets remain attached to the object.

        This runs after reloading storage. If no open sockets exist, any recovered round is
        stale and must be reset so new clients do not inherit ghost players or a started game.
        Note that GameState._reset_to_lobby() does not clear players by itself because the
        local-server path removes them before calling it, so the Worker must clear players here.
        """
        if self._open_websockets():
            return

        if not self.game.players and not self.game.started and not self.game.finished:
            return

        self.game.players = []
        self.game._reset_to_lobby()

        await self._save_game()

    def _open_websockets(self) -> list:
        """Return only currently open Durable Object websockets."""
        return [ws for ws in self.ctx.getWebSockets() if getattr(ws, "readyState", 0) == 1]


class Default(WorkerEntrypoint):
    async def fetch(self, request):
        url = request.url if hasattr(request, "url") else str(request)
        query = parse_qs(urlparse(url).query)
        game_id = query.get("game", ["default-game"])[0] or "default-game"
        stub = self.env.TUNO_GAME.get(self.env.TUNO_GAME.idFromName(game_id))
        return await stub.fetch(request)
