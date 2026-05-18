"""Pure body-rendering helpers shared by the Textual client widgets."""

from __future__ import annotations

from typing import Any, Dict, Iterable, List, Optional, Sequence

from rich.console import RenderableType
from rich.markup import escape
from rich.table import Table

from tuno.client.state import my_hand
from tuno.core.cards import Card, Color
from tuno.core.snapshot import GameSnapshot

_LOBBY_EVENT_SUBSTRINGS = ("joined the lobby", "left the lobby")
_IMPORTANT_ACTIVITY_SUFFIXES = (
    "armed UNO.",
    "wins the round!",
    "wins by default!",
)


def role_label(state: GameSnapshot, *, in_room: bool) -> str:
    """Derive the local player's lobby/game role label from a snapshot."""
    your_id = state.your_player_id
    host_id = state.host_player_id

    if not your_id:
        return "spectator" if in_room else "not joined"
    if your_id == host_id:
        return "host"

    return "player"


def _phase_label(state: GameSnapshot) -> str:
    """Derive the current room phase label from a snapshot."""
    if state.started and not state.finished:
        return "game"
    if state.finished:
        return "finished"
    return "lobby"


def _local_player_name(state: GameSnapshot) -> str:
    """Return the local player's name from the player snapshot, or '?' before join."""
    your_id = state.your_player_id
    for player in state.players:
        if player.get("player_id") == your_id:
            return str(player.get("name") or "?")
    return "?"


def card_markup(card: Dict[str, Any]) -> str:
    """Render a card payload as Rich markup using its short label."""
    return Card.from_dict(card).event_markup()


def top_card_markup(card: Dict[str, Any], current_color: Optional[str]) -> str:
    """Render the top card, using the chosen color for wild cards in play."""
    parsed = Card.from_dict(card)
    display_color = current_color if parsed.is_wild() and Color.parse(current_color) else None
    return parsed.event_markup(display_color=display_color)


def recent_activity_markup(event: str) -> str:
    """Add light presentation formatting to recent activity without changing semantics."""
    if event.endswith(_IMPORTANT_ACTIVITY_SUFFIXES):
        return f"[bold]{event}[/]"
    return event


def _is_lobby_event(event: str) -> bool:
    """Return whether an activity event belongs to the lobby feed."""
    return any(substring in event for substring in _LOBBY_EVENT_SUBSTRINGS)


def _game_activity_events(events: Iterable[Any]) -> List[str]:
    """Return activity events that should appear in the in-game feed."""
    return [event for event in map(str, events) if not _is_lobby_event(event)]


def player_table(state: GameSnapshot) -> RenderableType:
    """Render the player roster as a table, or a placeholder when empty."""
    players = state.players
    if not players:
        return "No players yet."

    table = Table(
        box=None,
        padding=(0, 2, 0, 0),
        show_header=True,
        header_style="dim",
        expand=False,
    )
    table.add_column("")
    table.add_column("Name")
    table.add_column("#Cards")

    for player in players:
        is_current = player.get("player_id") == state.current_player_id
        prefix = "❯" if is_current else " "

        name = escape(str(player["name"]))
        host = " [host]" if player.get("player_id") == state.host_player_id else ""
        me = " (you)" if player.get("player_id") == state.your_player_id else ""

        table.add_row(
            prefix,
            f"{name}{host}{me}",
            str(player["card_count"]),
            style="bold" if is_current else None,
        )

    return table


def render_tuno_logo() -> str:
    return r"""
 _   _____ _____ _____
| |_|  |  |   | |     |
|  _|  |  | | | |  |  |
|_| |_____|_|___|_____|
"""


def render_command_feedback(message: Optional[str]) -> str:
    """Render the command feedback banner shown above the input box."""
    return "" if not message else escape(message)


def render_local_status_body(state: GameSnapshot, *, room_name: Optional[str]) -> str:
    """Render the local-status section body."""
    player_name = escape(_local_player_name(state))
    room_label = escape(room_name or "?")
    return "\n".join(
        [
            f"[bold]Name:[/] {player_name} ({role_label(state, in_room=bool(room_name))})",
            f"[bold]Room:[/] {room_label} ({_phase_label(state)})",
        ]
    )


def render_hand_body(state: GameSnapshot, *, say_uno_next: bool) -> str:
    """Render the hand section body."""
    hand = my_hand(state)
    hand_lines: List[str] = []

    for index, card in enumerate(hand, start=1):
        hand_lines.append(f"[{index:02d}] {card_markup(card)}")

    if not hand:
        hand_lines.append("(empty)")

    return "\n".join(hand_lines)


def render_players_title(state: GameSnapshot) -> str:
    """Render the dynamic players section title."""
    return f"Players ({len(state.players)}/5)"


def render_players_body(state: GameSnapshot) -> RenderableType:
    """Render the players section body."""
    return player_table(state)


def render_rooms_title(rooms: Sequence[Dict[str, Any]]) -> str:
    """Render the dynamic room-list section title."""
    return f"Room List ({len(rooms)})"


def render_rooms_body(rooms: Iterable[Dict[str, Any]]) -> RenderableType:
    """Render available rooms as a table, or a placeholder when none exist."""
    room_items = list(rooms)
    if not room_items:
        return "No rooms yet."

    table = Table(
        box=None,
        padding=(0, 2, 0, 0),
        show_header=True,
        header_style="dim",
        expand=False,
    )
    table.add_column("Name")
    table.add_column("Status")
    table.add_column("Players")

    for room in room_items:
        count = room.get("player_count", 0)
        max_players = room.get("max_players", 5)
        table.add_row(
            escape(str(room.get("name", ""))),
            escape(str(room.get("status", "Lobby"))),
            f"{count}/{max_players}",
        )

    return table


def render_top_card_body(state: GameSnapshot) -> str:
    """Render the standalone top-card line shown above recent activity items."""
    top = state.top_card or {}
    if not top or not state.started:
        return ""
    return f"Top card: {top_card_markup(top, state.current_color)}"


def render_recent_activity_body(state: GameSnapshot) -> str:
    """Render the recent-activity section body."""
    events = state.recent_events or []

    game_events = _game_activity_events(events)
    recent = [recent_activity_markup(event) for event in game_events[-20:][::-1]]
    recent_lines = recent or ["No game events yet."]
    return "\n".join(recent_lines)
