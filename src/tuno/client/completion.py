"""Pure helpers for slash-command suggestions, selection, and tab completion."""

from __future__ import annotations

from dataclasses import dataclass, field
from os.path import commonprefix
from typing import Any, Dict, List, Optional, Sequence

from tuno.core.cards import WILD_RANKS

SUGGESTION_ACTIVE_STYLE = "bold #7aa2f7"
SUGGESTION_DEFAULT_STYLE = "white"
SUGGESTION_EMPTY_STYLE = "dim"


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


def _is_legal_to_play(
    card: Dict[str, Any], current_color: Optional[str], top_card: Optional[Dict[str, Any]]
) -> bool:
    """Return True if the card is playable given the current game state."""
    if card.get("rank") in WILD_RANKS:
        return True
    if not current_color or not top_card:
        return True  # game hasn't started yet; cannot determine legality
    return card.get("color") == current_color or card.get("rank") == top_card.get("rank")


def command_candidates(
    raw: str,
    *,
    available_commands: Sequence[str],
    hand: Sequence[Dict[str, Any]],
    current_color: Optional[str] = None,
    top_card: Optional[Dict[str, Any]] = None,
) -> List[Dict[str, str]]:
    """Build suggestions for the current raw input and game-visible state."""
    text = raw.strip()
    if not text:
        return [command_template_candidate(template) for template in available_commands]
    if not text.startswith("/"):
        return []

    trailing_space = raw.endswith(" ")
    parts = text.split()
    command = parts[0].lower()

    if len(parts) == 1 and not trailing_space:
        return [
            command_template_candidate(template)
            for template in available_commands
            if template.split()[0].startswith(command)
        ]

    if command == "/play" and any(item.startswith("/play") for item in available_commands):
        # `/play` suggestions are stateful: candidate numbers mirror the visible hand order.
        if (len(parts) == 1 and trailing_space) or (len(parts) == 2 and not trailing_space):
            prefix = "" if len(parts) == 1 else parts[1]
            matches = []

            for index, card in enumerate(hand, start=1):
                token = str(index)
                if token.startswith(prefix) and _is_legal_to_play(card, current_color, top_card):
                    suffix = " <color>" if card.get("rank") in WILD_RANKS else ""
                    matches.append(
                        {
                            "insert": f"/play {token}" + (" " if suffix else ""),
                            "display": f"/play {token}{suffix} — {card.get('short') or card.get('label')}",
                        }
                    )
            return matches

        if len(parts) >= 2:
            try:
                hand_index = int(parts[1]) - 1
            except ValueError:
                return []

            if 0 <= hand_index < len(hand) and hand[hand_index].get("rank") in WILD_RANKS:
                if (len(parts) == 2 and trailing_space) or (len(parts) == 3 and not trailing_space):
                    prefix = "" if len(parts) == 2 else parts[2].lower()
                    return [
                        {
                            "insert": f"/play {parts[1]} {color}",
                            "display": f"/play {parts[1]} {color}",
                        }
                        for color in ("red", "yellow", "green", "blue")
                        if color.startswith(prefix)
                    ]
    return []


def render_suggestions(candidates: Sequence[Dict[str, str]], state: CompletionState) -> str:
    """Render the suggestion dropdown as Textual/Rich markup."""
    if not candidates:
        return f"[{SUGGESTION_EMPTY_STYLE}]  (No suggestions)[/]"

    lines = []
    for index, candidate in enumerate(candidates[:8]):
        is_selected = index == state.suggestion_index
        style = SUGGESTION_ACTIVE_STYLE if is_selected else SUGGESTION_DEFAULT_STYLE
        prefix = "❯ " if is_selected else "  "
        lines.append(f"[{style}]{prefix}{candidate['display']}[/]")
    return "\n".join(lines)


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


def command_template_candidate(template: str) -> Dict[str, str]:
    """Turn a canonical command template into insert/display suggestion data."""
    base = template.split()[0]
    insert = base + " " if base in {"/connect", "/play"} else base
    return {
        "insert": insert,
        "display": template,
    }
