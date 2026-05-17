import json
import unittest

from tuno.core.cards import CARD_TYPES_BY_RANK, WILD_CARD_TYPES, Card, CardKind, Color, Deck
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
        deck = Deck(LcgRandom())
        deck.reset()
        self.assertTrue(deck.draw_pile)
        self.assertTrue(all(isinstance(card, Card) for card in deck.draw_pile))

    def test_card_type_metadata_drives_labels_and_effects(self) -> None:
        """Keep card type labels and rule metadata in one maintained table."""
        draw_two = CARD_TYPES_BY_RANK["draw_two"]
        wild_draw_four = CARD_TYPES_BY_RANK["wild_draw_four"]

        self.assertEqual(Card("red", draw_two.rank).short_label(), "R:+2")
        self.assertEqual(Card(None, wild_draw_four.rank).display_name(), "Wild Draw Four")
        self.assertEqual(wild_draw_four.effect.draw_count, 4)
        self.assertEqual(wild_draw_four.kind, CardKind.WILD_DRAW_FOUR)
        self.assertTrue(wild_draw_four.is_wild)
        self.assertTrue(wild_draw_four.requires_no_current_color_match)
        self.assertTrue(draw_two.effect.skips_next)
        self.assertFalse(draw_two.is_wild)

    def test_card_construction_rejects_invalid_rank_color_combinations(self) -> None:
        """Keep invalid card states from reaching rule checks."""
        with self.assertRaisesRegex(ValueError, "Colored cards require a color"):
            Card(None, "5")
        with self.assertRaisesRegex(ValueError, "Wild cards must not have a color"):
            Card("red", "wild")
        with self.assertRaisesRegex(ValueError, "Unknown card rank"):
            Card("red", "bogus")
        with self.assertRaises(ValueError):
            Card.from_dict({"color": "purple", "rank": "5"})

    def test_card_payload_uses_plain_json_values(self) -> None:
        """Serialize cards with primitive values at the protocol boundary."""
        payload = Card("red", "5").to_dict()

        self.assertEqual(payload, {"color": "red", "rank": "5"})
        self.assertIs(Card.from_dict(payload).color, Color.RED)
        self.assertEqual(json.loads(json.dumps(payload)), payload)

    def test_deck_builds_wild_cards_from_type_table(self) -> None:
        """Use the maintained wild type table when building the classic deck."""
        deck = Deck(LcgRandom())
        deck.reset()

        wild_ranks = {card_type.rank for card_type in WILD_CARD_TYPES}
        wild_cards = [card for card in deck.draw_pile if card.rank in wild_ranks]

        self.assertEqual(len(wild_cards), 8)
        self.assertEqual({card.rank for card in wild_cards}, wild_ranks)

    def test_color_parse_round_trips_and_rejects_garbage(self) -> None:
        """Color.parse must accept str/Color/None and return None for unknown values."""
        self.assertIs(Color.parse("red"), Color.RED)
        self.assertIs(Color.parse(Color.GREEN), Color.GREEN)
        self.assertIsNone(Color.parse(None))
        self.assertIsNone(Color.parse("purple"))
        self.assertIsNone(Color.parse(123))
