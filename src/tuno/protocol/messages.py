"""JSON protocol helpers shared by the client, server, and worker adapter."""

from __future__ import annotations

import json
from enum import StrEnum
from typing import Any, Dict


class ProtocolError(Exception):
    """Raised when a protocol message is malformed."""


MAX_MESSAGE_SIZE = 4096


class ClientMsg(StrEnum):
    """Client-originated protocol message types.

    Members are plain ``str`` subclasses (``StrEnum``), so they serialize on the
    wire exactly as their value and remain comparable to raw strings during the
    decode path.
    """

    CREATE_ROOM = "create_room"
    JOIN_ROOM = "join_room"
    JOIN = "join"
    START = "start"
    PLAY_CARD = "play_card"
    DRAW_CARD = "draw_card"
    PASS_TURN = "pass_turn"
    LEAVE = "leave"
    EXIT_ROOM = "exit_room"
    SET_UNO = "set_uno"


class ServerMsg(StrEnum):
    """Server-originated protocol message types."""

    INFO = "info"
    ROOM_CLOSED = "room_closed"
    ROOM_LEFT = "room_left"
    ROOM_JOINED = "room_joined"
    ROOM_LIST = "room_list"
    WELCOME = "welcome"
    STATE = "state"
    ERROR = "error"


def decode_json_message(raw: str) -> Dict[str, Any]:
    """Decode a raw JSON message and validate the outer payload shape."""
    if len(raw) > MAX_MESSAGE_SIZE:
        raise ProtocolError("Message is too large.")

    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ProtocolError("Message must be valid JSON.") from exc

    if not isinstance(payload, dict):
        raise ProtocolError("Message payload must be an object.")

    return payload


def decode_client_message(raw: str) -> Dict[str, Any]:
    """Decode and validate a client-originated protocol message."""
    payload = decode_json_message(raw)

    kind = payload.get("type")
    try:
        ClientMsg(kind)
    except ValueError as exc:
        raise ProtocolError(f"Unsupported message type: {kind!r}") from exc

    return payload


def decode_server_message(raw: str) -> Dict[str, Any]:
    """Decode and validate a server-originated protocol message."""
    payload = decode_json_message(raw)

    kind = payload.get("type")
    try:
        ServerMsg(kind)
    except ValueError as exc:
        raise ProtocolError(f"Unsupported server message type: {kind!r}") from exc

    return payload


def encode_message(kind: ClientMsg | ServerMsg, **payload: Any) -> str:
    """Encode a protocol message with its `type` envelope."""
    data = {"type": str(kind)}
    data.update(payload)
    return json.dumps(data)
