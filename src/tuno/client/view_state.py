"""Pure helpers that translate client runtime state into widget-facing view state."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Sequence

from rich.console import RenderableType

from tuno.client.rendering import (
    render_command_feedback,
    render_hand_body,
    render_local_status_body,
    render_players_body,
    render_players_title,
    render_recent_activity_body,
    render_top_card_body,
)


@dataclass(frozen=True)
class ClientViewState:
    """Widget-facing snapshot assembled from app runtime state."""

    border_title: str
    local_status_body: str
    hand_visible: bool
    hand_body: str
    players_title: str
    players_body: RenderableType
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
    state: Dict[str, Any],
    player_id: str | None,
    command_feedback_message: str | None,
    say_uno_next: bool,
    available_commands: Sequence[str],
) -> ClientViewState:
    """Convert client runtime state into the strings/renderables needed by widgets."""
    return ClientViewState(
        border_title=f"tUNO v{app_version} ({server_target})",
        local_status_body=render_local_status_body(state),
        hand_visible=bool(state.get("started") and not state.get("finished")),
        hand_body=render_hand_body(state, say_uno_next=say_uno_next),
        players_title=render_players_title(state),
        players_body=render_players_body(state),
        top_card_visible=bool(state.get("started") and state.get("top_card")),
        top_card_body=render_top_card_body(state),
        recent_activity_body=render_recent_activity_body(state),
        command_meta_visible=bool(command_feedback_message or player_id is None),
        command_meta_text=(
            render_command_feedback(command_feedback_message)
            if command_feedback_message
            else "Join the game: /connect <name>"
            if player_id is None
            else ""
        ),
        input_placeholder=available_commands[0] if available_commands else "/help",
    )
