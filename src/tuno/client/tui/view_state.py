"""Pure helpers that translate client runtime state into widget-facing view state."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Sequence

from rich.console import RenderableType

from tuno.client.tui.commands import default_command_meta_text
from tuno.client.tui.rendering import (
    render_command_feedback,
    render_hand_body,
    render_local_status_body,
    render_players_body,
    render_players_title,
    render_recent_activity_body,
    render_rooms_body,
    render_rooms_title,
    render_server_history_body,
    render_server_history_title,
    render_top_card_body,
)
from tuno.core.snapshot import GameSnapshot


@dataclass(frozen=True)
class ClientViewState:
    """Widget-facing snapshot assembled from app runtime state."""

    border_title: str
    local_status_body: str
    hand_visible: bool
    hand_body: str
    right_list_title: str
    right_list_body: RenderableType
    recent_activity_visible: bool
    top_card_visible: bool
    top_card_body: str
    recent_activity_body: str
    command_meta_visible: bool
    command_meta_text: str
    input_placeholder: str


def build_view_state(
    *,
    app_version: str,
    server_target: str,
    state: GameSnapshot,
    rooms: Sequence[Dict[str, Any]],
    server_history: Sequence[str],
    connected: bool,
    room_selected: bool,
    selected_room_name: str | None,
    player_id: str | None,
    command_feedback_message: str | None,
    say_uno_next: bool,
    available_commands: Sequence[str],
) -> ClientViewState:
    """Convert client runtime state into the strings/renderables needed by widgets."""
    command_meta_text = _command_meta_text(
        connected=connected,
        room_selected=room_selected,
        player_id=player_id,
        command_feedback_message=command_feedback_message,
    )
    right_list_title, right_list_body, recent_activity_visible = _right_panel_content(
        state,
        rooms=rooms,
        server_history=server_history,
        connected=connected,
        room_selected=room_selected,
    )

    return ClientViewState(
        border_title=f"Tuno v{app_version} ({server_target})",
        local_status_body=render_local_status_body(state, room_name=selected_room_name),
        hand_visible=bool(state.started and not state.finished and player_id is not None),
        hand_body=render_hand_body(state, say_uno_next=say_uno_next),
        right_list_title=right_list_title,
        right_list_body=right_list_body,
        recent_activity_visible=recent_activity_visible,
        top_card_visible=bool(recent_activity_visible and state.started and state.top_card),
        top_card_body=render_top_card_body(state),
        recent_activity_body=render_recent_activity_body(state),
        command_meta_visible=bool(command_feedback_message or player_id is None),
        command_meta_text=command_meta_text,
        input_placeholder=available_commands[0] if available_commands else "/help",
    )


def _right_panel_content(
    state: GameSnapshot,
    *,
    rooms: Sequence[Dict[str, Any]],
    server_history: Sequence[str],
    connected: bool,
    room_selected: bool,
) -> tuple[str, RenderableType, bool]:
    if not connected:
        return (
            render_server_history_title(server_history),
            render_server_history_body(server_history),
            False,
        )

    if not room_selected:
        return render_rooms_title(rooms), render_rooms_body(rooms), False

    return render_players_title(state), render_players_body(state), True


def _command_meta_text(
    *,
    connected: bool,
    room_selected: bool,
    player_id: str | None,
    command_feedback_message: str | None,
) -> str:
    if command_feedback_message:
        return render_command_feedback(command_feedback_message)
    if player_id is not None:
        return ""
    return default_command_meta_text(connected=connected, room_selected=room_selected)
