import unittest

from tuno.core.cards import build_classic_deck


class DeckTests(unittest.TestCase):
    """Cover deck construction rules."""

    def test_standard_deck_has_108_cards(self) -> None:
        """Build the classic UNO deck with the standard 108-card size."""
        self.assertEqual(len(build_classic_deck()), 108)
