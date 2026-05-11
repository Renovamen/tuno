"""Rich markup rendering for command suggestion rows."""

from __future__ import annotations

from typing import Dict, Sequence

from tuno.client.tui.completion import CompletionState

SUGGESTION_ACTIVE_STYLE = "bold #7aa2f7"
SUGGESTION_DEFAULT_STYLE = "white"
SUGGESTION_EMPTY_STYLE = "dim"
MAX_VISIBLE_SUGGESTIONS = 4


def render_suggestions(candidates: Sequence[Dict[str, str]], state: CompletionState) -> str:
    """Render the suggestion dropdown as Textual/Rich markup."""
    if not candidates:
        return f"[{SUGGESTION_EMPTY_STYLE}]  (No suggestions)[/]"

    start = 0
    if len(candidates) > MAX_VISIBLE_SUGGESTIONS:
        start = min(
            max(state.suggestion_index - (MAX_VISIBLE_SUGGESTIONS - 1), 0),
            len(candidates) - MAX_VISIBLE_SUGGESTIONS,
        )

    lines = []
    visible = candidates[start : start + MAX_VISIBLE_SUGGESTIONS]

    for offset, candidate in enumerate(visible):
        index = start + offset
        is_selected = index == state.suggestion_index
        style = SUGGESTION_ACTIVE_STYLE if is_selected else SUGGESTION_DEFAULT_STYLE
        prefix = "❯ " if is_selected else "  "
        lines.append(f"[{style}]{prefix}{candidate['display']}[/]")

    return "\n".join(lines)
