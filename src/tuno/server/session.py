"""Server-side coordinator that binds websocket connections to one GameState."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Dict, Optional

from tuno.core.game import GameError, GameState
from tuno.protocol.messages import encode_message
from tuno.server.actions import apply_action


@dataclass
class Connection:
    """Track one websocket and the player currently associated with it."""

    websocket: object
    player_id: Optional[str] = None


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

        await self._send(websocket, "info", message="Connected. Join with your player name.")
        await self._broadcast_state()

        return True

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
                    websocket, "state", state=self.state.snapshot_for(connection.player_id)
                )
            except Exception:
                stale.append(websocket)
        for websocket in stale:
            self.connections.pop(websocket, None)

    async def _send(self, websocket: object, kind: str, **payload: object) -> None:
        """Encode and send one server message to a websocket."""
        await websocket.send(encode_message(kind, **payload))
