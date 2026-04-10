from __future__ import annotations

import unittest
from unittest.mock import Mock

from tuno.client.theme import activate_tuno_theme, build_tuno_theme


class ClientThemeTests(unittest.TestCase):
    """Cover the extracted client theme helpers."""

    def test_build_tuno_theme_uses_project_name_and_palette(self) -> None:
        """Create the expected custom theme object for the client."""
        theme = build_tuno_theme()
        self.assertEqual(theme.name, "tuno")
        self.assertTrue(theme.accent)
        self.assertTrue(theme.primary)

    def test_activate_tuno_theme_registers_and_enables_ansi_mode(self) -> None:
        """Register the project theme, activate it, and force ANSI mode back on."""
        app = Mock()

        activate_tuno_theme(app)

        app.register_theme.assert_called_once()
        self.assertEqual(app.theme, "tuno")
        self.assertTrue(app.ansi_color)
