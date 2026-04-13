"""Pure body-rendering helpers shared by the Textual client widgets."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from rich.console import RenderableType
from rich.markup import escape
from rich.table import Table

CARD_COLORS = {
    "red": "red",
    "yellow": "yellow",
    "green": "green",
    "blue": "blue",
}

_LOBBY_EVENT_SUBSTRINGS = ("joined the lobby", "left the lobby")
_UNO_ARMED_SUFFIX = "armed UNO."


def role_label(state: Dict[str, Any]) -> str:
    """Derive the local player's lobby/game role label from a snapshot."""
    your_id = state.get("your_player_id")
    host_id = state.get("host_player_id")

    if not your_id:
        return "Not joined"
    if your_id == host_id:
        return "Host"

    return "Player"


def my_hand(state: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Return the current player's visible hand from a client snapshot."""
    for player in state.get("players", []):
        if player.get("player_id") == state.get("your_player_id"):
            return list(player.get("hand", []))
    return []


def card_markup(card: Dict[str, Any], *, prefer_short: bool = False) -> str:
    """Render a card payload as Rich markup, escaping all untrusted text."""
    color = card.get("color")
    label = card.get("short") if prefer_short else card.get("label")
    label = label or card.get("label") or card.get("short") or "Card"
    if color in CARD_COLORS:
        return f"[bold {CARD_COLORS[color]}]{escape(str(label))}[/]"
    return f"[bold magenta]{escape(str(label))}[/]"


def top_card_markup(card: Dict[str, Any], current_color: Optional[str]) -> str:
    """Render the top card, using the chosen color for wild cards in play."""
    display_card = dict(card)
    if display_card.get("rank") in {"wild", "wild_draw_four"} and current_color in CARD_COLORS:
        display_card["color"] = current_color
    return card_markup(display_card, prefer_short=True)


def recent_activity_markup(event: str) -> str:
    """Add light presentation formatting to recent activity without changing semantics."""
    rendered = event
    if rendered.endswith(_UNO_ARMED_SUFFIX):
        rendered = f"[bold]{rendered}[/]"
    return rendered


def player_table(state: Dict[str, Any]) -> RenderableType:
    """Render the player roster as a table, or a placeholder when empty."""
    players = state.get("players", [])
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
        prefix = "❯" if player.get("player_id") == state.get("current_player_id") else " "
        name = escape(str(player["name"]))
        host = " [host]" if player.get("player_id") == state.get("host_player_id") else ""
        me = " (you)" if player.get("player_id") == state.get("your_player_id") else ""
        table.add_row(prefix, f"{name}{host}{me}", str(player["card_count"]))
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


def render_local_status_body(state: Dict[str, Any]) -> str:
    """Render the local-status section body."""
    current_role = role_label(state)
    phase = (
        "Game"
        if state.get("started") and not state.get("finished")
        else "Finished"
        if state.get("finished")
        else "Lobby"
    )
    return "\n".join([f"[bold]Role:[/] {current_role}", f"[bold]Phase:[/] {phase}"])


def render_hand_body(state: Dict[str, Any], *, say_uno_next: bool) -> str:
    """Render the hand section body."""
    hand = my_hand(state)
    hand_lines: List[str] = []
    for index, card in enumerate(hand, start=1):
        hand_lines.append(f"[{index:02d}] {card_markup(card, prefer_short=True)}")
    if not hand:
        hand_lines.append("(empty)")
    return "\n".join(hand_lines)


def render_players_title(state: Dict[str, Any]) -> str:
    """Render the dynamic players section title."""
    return f"Players ({len(state.get('players', []))}/5)"


def render_players_body(state: Dict[str, Any]) -> RenderableType:
    """Render the players section body."""
    return player_table(state)


def render_top_card_body(state: Dict[str, Any]) -> str:
    """Render the standalone top-card line shown above recent activity items."""
    top = state.get("top_card") or {}
    if not top or not state.get("started"):
        return ""
    return f"Top card: {top_card_markup(top, state.get('current_color'))}"


def render_recent_activity_body(state: Dict[str, Any]) -> str:
    """Render the recent-activity section body."""
    events = state.get("recent_events") or []

    game_events = [str(e) for e in events if not any(kw in e for kw in _LOBBY_EVENT_SUBSTRINGS)]
    recent = [recent_activity_markup(event) for event in game_events[-6:][::-1]]
    recent_lines = recent or ["No game events yet."]
    return "\n".join(recent_lines)


def format_server_error(state: Dict[str, Any], message: str, code: str = "") -> str:
    """Translate server error payloads into client-facing, context-rich text."""
    top_card = state.get("top_card") or {}
    top_label = top_card.get("short") or top_card.get("label") or "-"
    current_color = state.get("current_color") or "-"

    match code:
        case "illegal_play":
            return (
                f"Illegal play: card does not match current color {current_color} "
                f"or top card {top_label}."
            )
        case "wild_needs_color":
            return "Illegal play: wild cards require a color. Example: /play 1 red"
        case "wild_draw_four_restricted":
            return (
                "Illegal play: Wild Draw Four only works when you have no card matching current "
                f"color {current_color}."
            )
        case "invalid_selection":
            return "Illegal play: that card number is not valid for your current hand."
        case _:
            return f"Error: {message}"
