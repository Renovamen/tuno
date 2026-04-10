"""JSON protocol helpers shared by the client, server, and worker adapter."""

from __future__ import annotations

import json
from typing import Any, Dict


class ProtocolError(Exception):
    """Raised when a protocol message is malformed."""


MAX_MESSAGE_SIZE = 4096

CLIENT_MESSAGE_TYPES = {
    "join",
    "start",
    "play_card",
    "draw_card",
    "pass_turn",
    "leave",
    "set_uno",
}

SERVER_MESSAGE_TYPES = {
    "info",
    "welcome",
    "state",
    "error",
}


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
    if kind not in CLIENT_MESSAGE_TYPES:
        raise ProtocolError(f"Unsupported message type: {kind!r}")

    return payload


def decode_server_message(raw: str) -> Dict[str, Any]:
    """Decode and validate a server-originated protocol message."""
    payload = decode_json_message(raw)

    kind = payload.get("type")
    if kind not in SERVER_MESSAGE_TYPES:
        raise ProtocolError(f"Unsupported server message type: {kind!r}")

    return payload


def encode_message(kind: str, **payload: Any) -> str:
    """Encode a protocol message with its `type` envelope."""
    data = {"type": kind}
    data.update(payload)
    return json.dumps(data)
