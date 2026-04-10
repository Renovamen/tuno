"""Cloudflare Worker adapter for tuno.

This module targets Cloudflare's Python Worker + Durable Object runtime. It mirrors
local-server semantics at a high level: one Durable Object instance owns one game.
The pure Python game engine remains the source of truth for rules.

The exact deployment/runtime semantics should be verified inside a Cloudflare project.
"""

from __future__ import annotations

import json
from typing import Dict, Optional

from workers import DurableObject, Response, WorkerEntrypoint

from tuno.core.game import MAX_PLAYERS, GameError, GameState
from tuno.protocol.messages import MAX_MESSAGE_SIZE
from tuno.server.actions import apply_action


class TunoGame(DurableObject):
    MAX_CONNECTIONS = MAX_PLAYERS + 3

    def __init__(self, ctx, env):
        super().__init__(ctx, env)
        self.game = GameState()
        self.clients: Dict[object, Optional[str]] = {}

    async def fetch(self, request):
        upgrade = request.headers.get("Upgrade", "")
        if upgrade.lower() != "websocket":
            return Response("Expected websocket upgrade.", status=426)
        if len(self.clients) >= self.MAX_CONNECTIONS:
            return Response("Server is at capacity.", status=503)

        pair = self.ctx.new_websocket_pair()
        client_socket = pair[0]
        server_socket = pair[1]
        self.ctx.accept_websocket(server_socket)
        self.clients[server_socket] = None
        server_socket.send(
            json.dumps({"type": "info", "message": "Connected. Join with your player name."})
        )
        await self._broadcast_state()
        return Response(status=101, web_socket=client_socket)

    async def webSocketMessage(self, ws, message):
        if len(message) > MAX_MESSAGE_SIZE:
            ws.send(json.dumps({"type": "error", "message": "Message is too large."}))
            return
        payload = json.loads(message)
        try:
            result = apply_action(self.game, self.clients.get(ws), payload)
            self.clients[ws] = result.player_id
            if result.welcome_player_id:
                ws.send(json.dumps({"type": "welcome", "player_id": result.welcome_player_id}))
        except GameError as exc:
            ws.send(json.dumps({"type": "error", "message": str(exc), "code": exc.code or ""}))
        await self._broadcast_state()

    async def webSocketClose(self, ws, code, reason, wasClean):
        player_id = self.clients.pop(ws, None)
        if player_id:
            try:
                self.game.remove_player(player_id)
            except GameError:
                pass
        ws.close(code, reason)
        await self._broadcast_state()

    async def _broadcast_state(self):
        for websocket, player_id in list(self.clients.items()):
            websocket.send(
                json.dumps({"type": "state", "state": self.game.snapshot_for(player_id)})
            )


class Default(WorkerEntrypoint):
    async def fetch(self, request):
        url = request.url if hasattr(request, "url") else str(request)
        game_id = "default-game"
        if "?game=" in url:
            game_id = url.split("?game=", 1)[1].split("&", 1)[0] or game_id
        stub = self.env.TUNO_GAME.get(self.env.TUNO_GAME.id_from_name(game_id))
        return await stub.fetch(request)
