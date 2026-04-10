"""Theme helpers for the Textual client."""

from __future__ import annotations

from textual.app import App
from textual.theme import BUILTIN_THEMES, Theme


def build_tuno_theme() -> Theme:
    """Build the custom client theme from built-in Textual themes."""
    base = BUILTIN_THEMES["textual-ansi"]
    palette = BUILTIN_THEMES["catppuccin-latte"]

    return Theme(
        name="tuno",
        primary=palette.primary,
        secondary=palette.secondary,
        warning=palette.warning,
        error=palette.error,
        success=palette.success,
        accent=palette.accent,
        foreground=base.foreground,
        background=base.background,
        surface=base.surface,
        panel=base.panel,
        boost=base.boost,
        dark=base.dark,
        variables={**base.variables, **palette.variables},
    )


def activate_tuno_theme(app: App) -> None:
    """Register and activate the project's custom theme."""
    app.register_theme(build_tuno_theme())
    app.theme = "tuno"
    # Textual special-cases `textual-ansi` by theme name. Re-enable ANSI mode after activation.
    app.ansi_color = True
