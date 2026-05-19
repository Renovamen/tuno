"""Pure helpers for slash-command suggestions, selection, and tab completion."""

from __future__ import annotations

from dataclasses import dataclass, field
from os.path import commonprefix
from typing import Any, Callable, Dict, List, Optional, Sequence

from tuno.core.cards import Card


@dataclass
class CompletionState:
    """Track the visible suggestion list and the current completion cursor."""

    completion_candidates: List[str] = field(default_factory=list)
    completion_index: int = 0
    suggestion_index: int = 0
    suggestion_navigated: bool = False


def hidden_completion_state() -> CompletionState:
    """Return the empty completion state used when no suggestions are visible."""
    return CompletionState()


def sync_completion_state(
    state: CompletionState, candidates: Sequence[Dict[str, str]]
) -> CompletionState:
    """Align cached completion state with the latest candidate list."""
    inserts = [candidate["insert"] for candidate in candidates]

    if inserts != state.completion_candidates:
        state.completion_candidates = inserts
        state.completion_index = 0
        state.suggestion_index = 0
        state.suggestion_navigated = False
    elif inserts:
        state.suggestion_index = min(state.suggestion_index, len(inserts) - 1)

    return state


def is_legal_to_play(
    card: Dict[str, Any], current_color: Optional[str], top_card: Optional[Dict[str, Any]]
) -> bool:
    """Return True if the card is playable given the current game state."""
    if Card.from_dict(card).is_wild():
        return True
    if not current_color or not top_card:
        return True  # game hasn't started yet; cannot determine legality
    return card.get("color") == current_color or card.get("rank") == top_card.get("rank")


def command_candidates(
    raw: str,
    *,
    available_commands: Sequence[str],
    card_command_token: str | None = None,
    connect_command_token: str | None = None,
    command_template_candidate: Callable[[str], Dict[str, str]] | None = None,
    valid_play_colors: Sequence[str] = (),
    hand: Sequence[Dict[str, Any]],
    rooms: Sequence[Dict[str, Any]] = (),
    current_color: Optional[str] = None,
    top_card: Optional[Dict[str, Any]] = None,
) -> List[Dict[str, str]]:
    """Build suggestions for the current raw input and game-visible state."""
    template_candidate = command_template_candidate or default_command_template_candidate
    text = raw.strip()
    if not text:
        return [template_candidate(template) for template in available_commands]
    if not text.startswith("/"):
        return []

    # Keep trailing-space information separate because stripped text loses argument position.
    trailing_space = raw.endswith(" ")
    parts = text.split()
    command = parts[0].lower()

    if len(parts) == 1 and not trailing_space:
        return _matching_command_candidates(command, available_commands, template_candidate)

    return _stateful_candidates(
        command=command,
        parts=parts,
        trailing_space=trailing_space,
        available_commands=available_commands,
        card_command_token=card_command_token,
        connect_command_token=connect_command_token,
        valid_play_colors=valid_play_colors,
        hand=hand,
        rooms=rooms,
        current_color=current_color,
        top_card=top_card,
    )


def _stateful_candidates(
    *,
    command: str,
    parts: Sequence[str],
    trailing_space: bool,
    available_commands: Sequence[str],
    card_command_token: str | None,
    connect_command_token: str | None,
    valid_play_colors: Sequence[str],
    hand: Sequence[Dict[str, Any]],
    rooms: Sequence[Dict[str, Any]],
    current_color: Optional[str],
    top_card: Optional[Dict[str, Any]],
) -> List[Dict[str, str]]:
    play_candidates = _play_candidates(
        command=command,
        parts=parts,
        trailing_space=trailing_space,
        available_commands=available_commands,
        card_command_token=card_command_token,
        valid_play_colors=valid_play_colors,
        hand=hand,
        current_color=current_color,
        top_card=top_card,
    )
    if play_candidates is not None:
        return play_candidates

    connect_candidates = _connect_candidates(
        command=command,
        parts=parts,
        trailing_space=trailing_space,
        available_commands=available_commands,
        connect_command_token=connect_command_token,
        rooms=rooms,
    )
    if connect_candidates is not None:
        return connect_candidates

    return []


def _matching_command_candidates(
    command: str,
    available_commands: Sequence[str],
    template_candidate: Callable[[str], Dict[str, str]],
) -> List[Dict[str, str]]:
    return [
        template_candidate(template)
        for template in available_commands
        if template.split()[0].startswith(command)
    ]


def _play_candidates(
    *,
    command: str,
    parts: Sequence[str],
    trailing_space: bool,
    available_commands: Sequence[str],
    card_command_token: str | None,
    valid_play_colors: Sequence[str],
    hand: Sequence[Dict[str, Any]],
    current_color: Optional[str],
    top_card: Optional[Dict[str, Any]],
) -> List[Dict[str, str]] | None:
    if not _command_available(command, card_command_token, available_commands):
        return None

    if (len(parts) == 1 and trailing_space) or (len(parts) == 2 and not trailing_space):
        prefix = "" if len(parts) == 1 else parts[1]
        return _play_card_candidates(card_command_token, prefix, hand, current_color, top_card)

    if len(parts) < 2:
        return []
    return _play_color_candidates(
        card_command_token, parts, trailing_space, hand, valid_play_colors
    )


def _play_card_candidates(
    card_command_token: str,
    prefix: str,
    hand: Sequence[Dict[str, Any]],
    current_color: Optional[str],
    top_card: Optional[Dict[str, Any]],
) -> List[Dict[str, str]]:
    matches = []
    for index, card in enumerate(hand, start=1):
        token = str(index)
        if not token.startswith(prefix) or not is_legal_to_play(card, current_color, top_card):
            continue
        parsed = Card.from_dict(card)
        suffix = " <color>" if parsed.is_wild() else ""
        matches.append(
            {
                "insert": f"{card_command_token} {token}" + (" " if suffix else ""),
                "display": (f"{card_command_token} {token}{suffix} — {parsed.short_label()}"),
            }
        )
    return matches


def _play_color_candidates(
    card_command_token: str,
    parts: Sequence[str],
    trailing_space: bool,
    hand: Sequence[Dict[str, Any]],
    valid_play_colors: Sequence[str],
) -> List[Dict[str, str]]:
    try:
        hand_index = int(parts[1]) - 1
    except ValueError:
        return []

    if not (0 <= hand_index < len(hand) and Card.from_dict(hand[hand_index]).is_wild()):
        return []
    if not ((len(parts) == 2 and trailing_space) or (len(parts) == 3 and not trailing_space)):
        return []

    prefix = "" if len(parts) == 2 else parts[2].lower()
    return [
        {
            "insert": f"{card_command_token} {parts[1]} {color}",
            "display": f"{card_command_token} {parts[1]} {color}",
        }
        for color in valid_play_colors
        if color.startswith(prefix)
    ]


def _connect_candidates(
    *,
    command: str,
    parts: Sequence[str],
    trailing_space: bool,
    available_commands: Sequence[str],
    connect_command_token: str | None,
    rooms: Sequence[Dict[str, Any]],
) -> List[Dict[str, str]] | None:
    if not _command_available(command, connect_command_token, available_commands):
        return None
    if not ((len(parts) == 1 and trailing_space) or (len(parts) == 2 and not trailing_space)):
        return []

    prefix = "" if len(parts) == 1 else parts[1]
    return [
        {
            "insert": f"{connect_command_token} {name}",
            "display": f"{connect_command_token} {name}",
        }
        for room in rooms
        if (name := str(room.get("name", "")).strip()) and name.startswith(prefix)
    ]


def _command_available(
    command: str, command_token: str | None, available_commands: Sequence[str]
) -> bool:
    return bool(
        command_token
        and command == command_token
        and any(item.split()[0] == command_token for item in available_commands)
    )


def apply_completion(
    raw: str, state: CompletionState, candidates: Sequence[Dict[str, str]]
) -> tuple[str, CompletionState]:
    """Resolve the next tab-completion result from the current candidate state."""
    state = sync_completion_state(state, candidates)
    inserts = state.completion_candidates

    if state.suggestion_navigated:
        completed = inserts[state.suggestion_index % len(inserts)]
        state.completion_index = state.suggestion_index
        state.suggestion_navigated = False
        return completed, state

    shared = commonprefix(inserts)
    if shared and shared != raw:
        state.completion_index = 0
        return shared, state

    completed = inserts[state.completion_index % len(inserts)]
    state.completion_index = (state.completion_index + 1) % len(inserts)
    state.suggestion_index = min(state.completion_index, len(inserts) - 1)
    return completed, state


def move_selection(
    state: CompletionState, candidates: Sequence[Dict[str, str]], delta: int
) -> CompletionState:
    """Move the highlighted suggestion up or down within the current list."""
    state = sync_completion_state(state, candidates)
    state.suggestion_index = (state.suggestion_index + delta) % len(candidates)
    state.completion_index = state.suggestion_index
    state.suggestion_navigated = True
    return state


def default_command_template_candidate(template: str) -> Dict[str, str]:
    """Turn a canonical command template into insert/display suggestion data."""
    base = template.split()[0]
    insert = base + " " if len(template.split()) > 1 else base
    return {
        "insert": insert,
        "display": template,
    }
