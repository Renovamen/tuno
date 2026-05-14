import unittest

from tuno.core.cards import Deck
from tuno.core.prng import LcgRandom


class DeckTests(unittest.TestCase):
    """Cover deck construction rules."""

    def test_standard_deck_has_108_cards(self) -> None:
        """Build the classic UNO deck with the standard 108-card size."""
        deck = Deck(LcgRandom())
        deck.reset()
        self.assertEqual(len(deck.draw_pile), 108)

    def test_deck_reset_builds_card_instances(self) -> None:
        """Return concrete `Card` instances after resetting the deck."""
        from tuno.core.cards import Card

        deck = Deck(LcgRandom())
        deck.reset()
        self.assertTrue(deck.draw_pile)
        self.assertTrue(all(isinstance(card, Card) for card in deck.draw_pile))
