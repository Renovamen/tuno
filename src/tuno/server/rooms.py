"""Shared room policy helpers for server runtimes."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

from tuno.core.game import MAX_PLAYERS, GameState
from tuno.protocol.messages import ClientMsg

ROOM_COMMANDS: frozenset[ClientMsg] = frozenset({ClientMsg.CREATE_ROOM, ClientMsg.JOIN_ROOM})


class RoomMessages:
    """User-visible room protocol messages shared by server runtimes."""

    choose_first: str = "Choose a room first."
    name_required: str = "Room name is required."
    name_exists: str = "Room name already exists."
    not_found: str = "Room does not exist."
    too_many: str = "Server has too many rooms."
    at_capacity: str = "Room is at capacity."
    closed: str = "Room closed. Choose another room."
    left: str = "Left room. Choose another room."
    connected_choose: str = "Connected. Choose a room."
    connected_join: str = "Connected. Join with your player name."


@dataclass(frozen=True)
class RoomSelectionValidation:
    """Pure room-selection payload validation result."""

    command: ClientMsg | None
    room_name: str
    error_message: str | None


def normalize_room_name(value: object) -> str:
    """Normalize a user-entered room name for uniqueness and display."""
    return str(value).strip()


def room_status(state: GameState) -> str:
    """Return a compact room status label for the room list."""
    if state.finished:
        return "Finished"
    if state.started:
        return "In game"
    return "Lobby"


def room_metadata(name: str, state: GameState) -> dict[str, object]:
    """Return public metadata for one room."""
    return {
        "name": name,
        "status": room_status(state),
        "player_count": len(state.players),
        "max_players": MAX_PLAYERS,
    }


def room_list_from_states(rooms: Mapping[str, GameState]) -> list[dict[str, object]]:
    """Return sorted public room metadata for a room-name to game-state mapping."""
    return [room_metadata(name, state) for name, state in sorted(rooms.items())]


def validate_room_selection_payload(payload: dict) -> RoomSelectionValidation:
    """Validate only room command type and name presence, leaving lifecycle local."""
    raw_type = payload["type"]
    try:
        command = ClientMsg(raw_type)
    except ValueError:
        return RoomSelectionValidation(None, "", RoomMessages.choose_first)
    if command not in ROOM_COMMANDS:
        return RoomSelectionValidation(None, "", RoomMessages.choose_first)

    room_name = normalize_room_name(payload.get("name", ""))
    if not room_name:
        return RoomSelectionValidation(command, room_name, RoomMessages.name_required)

    return RoomSelectionValidation(command, room_name, None)
