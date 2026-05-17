"""Card primitives and deck management for the UNO rule engine."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum, StrEnum
from typing import TYPE_CHECKING, List, Optional

from tuno.core.prng import LcgRandom

if TYPE_CHECKING:
    from tuno.core.game import PlayerState


class Color(StrEnum):
    """The four playable colors. Inherits from str so it serializes to JSON natively."""

    RED = "red"
    YELLOW = "yellow"
    GREEN = "green"
    BLUE = "blue"

    @classmethod
    def parse(cls, value: object) -> Optional["Color"]:
        """Return the matching Color for a str/Color value, or None for anything else."""
        if isinstance(value, cls):
            return value
        if not isinstance(value, str):
            return None

        try:
            return cls(value)
        except ValueError:
            return None


class CardKind(Enum):
    """The exhaustive set of UNO card kinds. Drives all rule-derived properties."""

    NUMBER = "number"
    SKIP = "skip"
    REVERSE = "reverse"
    DRAW_TWO = "draw_two"
    WILD = "wild"
    WILD_DRAW_FOUR = "wild_draw_four"


_WILD_KINDS = frozenset({CardKind.WILD, CardKind.WILD_DRAW_FOUR})


@dataclass(frozen=True)
class CardEffect:
    """Pure side-effect of playing a card on the next turn order and draws."""

    draw_count: int = 0
    skips_next: bool = False
    reverses_direction: bool = False


_NO_EFFECT = CardEffect()


@dataclass(frozen=True)
class CardType:
    """Static rank metadata: identity, label dictionary entries, and rule effect."""

    rank: str
    kind: CardKind
    short_name: str
    display_name: str
    effect: CardEffect = _NO_EFFECT

    @property
    def is_wild(self) -> bool:
        return self.kind in _WILD_KINDS

    @property
    def requires_no_current_color_match(self) -> bool:
        return self.kind is CardKind.WILD_DRAW_FOUR


NUMBER_CARD_TYPES = tuple(
    CardType(str(value), CardKind.NUMBER, str(value), str(value)) for value in range(10)
)
SKIP_CARD_TYPE = CardType("skip", CardKind.SKIP, "SKIP", "Skip", effect=CardEffect(skips_next=True))
REVERSE_CARD_TYPE = CardType(
    "reverse", CardKind.REVERSE, "REV", "Reverse", effect=CardEffect(reverses_direction=True)
)
DRAW_TWO_CARD_TYPE = CardType(
    "draw_two",
    CardKind.DRAW_TWO,
    "+2",
    "Draw Two",
    effect=CardEffect(skips_next=True, draw_count=2),
)
WILD_CARD_TYPE = CardType("wild", CardKind.WILD, "WILD", "Wild")
WILD_DRAW_FOUR_CARD_TYPE = CardType(
    "wild_draw_four",
    CardKind.WILD_DRAW_FOUR,
    "W+4",
    "Wild Draw Four",
    effect=CardEffect(skips_next=True, draw_count=4),
)

_ACTION_CARD_TYPES = (SKIP_CARD_TYPE, REVERSE_CARD_TYPE, DRAW_TWO_CARD_TYPE)
WILD_CARD_TYPES = (WILD_CARD_TYPE, WILD_DRAW_FOUR_CARD_TYPE)

CARD_TYPES_BY_RANK = {
    card_type.rank: card_type
    for card_type in (*NUMBER_CARD_TYPES, *_ACTION_CARD_TYPES, *WILD_CARD_TYPES)
}


def card_type_for_rank(rank: str) -> CardType:
    """Return metadata for a known card rank."""
    try:
        return CARD_TYPES_BY_RANK[rank]
    except KeyError as exc:
        raise ValueError(f"Unknown card rank: {rank}") from exc


@dataclass(frozen=True)
class Card:
    """Immutable value object representing a single UNO card."""

    color: Optional[Color | str]
    rank: str

    def __post_init__(self) -> None:
        # Accept raw strings ("red") for ergonomic construction; normalize to Color enum.
        color = self.color
        if color is not None and not isinstance(color, Color):
            color = Color(color)
            object.__setattr__(self, "color", color)

        card_type = card_type_for_rank(self.rank)
        if card_type.is_wild:
            if color is not None:
                raise ValueError("Wild cards must not have a color.")
            return

        if color is None:
            raise ValueError("Colored cards require a color.")

    @property
    def type(self) -> CardType:
        """Return the static metadata for this card's rank."""
        return card_type_for_rank(self.rank)

    def is_wild(self) -> bool:
        """Return whether the card can be played independent of the current color."""
        return self.type.is_wild

    def short_label(self) -> str:
        """Build the compact label used by the terminal client hand view."""
        if self.type.is_wild:
            return self.type.short_name
        prefix = (self.color.value if self.color else "?")[0].upper()
        return f"{prefix}:{self.type.short_name}"

    def display_name(self) -> str:
        """Build the human-readable label used in status and history text."""
        if self.type.is_wild:
            return self.type.display_name
        color_name = self.color.value if self.color else ""
        return f"{color_name.title()} {self.type.display_name}"

    def event_markup(self, display_color: Optional[str] = None) -> str:
        """Return a colored bold Rich markup string for use in event history."""
        label = self.short_label()
        color = Color.parse(display_color) if display_color is not None else self.color
        if color is not None:
            return f"[bold {color.value}]{label}[/]"
        return f"[bold magenta]{label}[/]"

    def to_dict(self) -> dict:
        """Serialize the card into the payload shape shared with clients."""
        return {"color": self.color.value if self.color else None, "rank": self.rank}

    @classmethod
    def from_dict(cls, payload: dict) -> "Card":
        """Reconstruct a card from a serialized payload."""
        return cls(color=payload.get("color"), rank=payload["rank"])


class Deck:
    """Manages draw and discard piles, shuffling, dealing, and exhaustion recycling."""

    def __init__(self, rng: LcgRandom) -> None:
        self._rng = rng
        self.draw_pile: List[Card] = []
        self.discard_pile: List[Card] = []

    @property
    def top_card(self) -> Optional[Card]:
        return self.discard_pile[-1] if self.discard_pile else None

    def reset(self) -> None:
        """Build a fresh shuffled classic deck and clear the discard pile."""
        self.draw_pile = self._build_classic_deck()
        self.discard_pile = []

    def _build_classic_deck(self) -> List[Card]:
        """Build the standard 108-card UNO deck and shuffle it."""
        deck: List[Card] = []

        for color in Color:
            deck.append(Card(color=color, rank=NUMBER_CARD_TYPES[0].rank))
            for card_type in (*NUMBER_CARD_TYPES[1:], *_ACTION_CARD_TYPES):
                deck.append(Card(color=color, rank=card_type.rank))
                deck.append(Card(color=color, rank=card_type.rank))

        for _ in range(4):
            for card_type in WILD_CARD_TYPES:
                deck.append(Card(color=None, rank=card_type.rank))

        self._rng.shuffle(deck)
        return deck

    def deal(self, players: List[PlayerState], count: int = 7) -> None:
        """Deal `count` cards from the draw pile to each player."""
        for player in players:
            player.hand = [self.draw_pile.pop() for _ in range(count)]

    def setup_opening_discard(self) -> Optional[str]:
        """Flip the first non-wild card onto the discard pile and return its color."""
        while self.draw_pile:
            card = self.draw_pile.pop()

            if not card.is_wild():
                self.discard_pile.append(card)
                return card.color.value if card.color else None

            self.draw_pile.insert(0, card)

        return None

    def draw_one(self) -> Card:
        """Draw one card, recycling the discard pile when the draw pile is exhausted."""
        if not self.draw_pile:
            if len(self.discard_pile) <= 1:
                from tuno.core.game import GameError  # lazy import to avoid circular dependency

                raise GameError("No cards left to draw.")

            top = self.discard_pile.pop()
            self.draw_pile = self.discard_pile[:]
            self.discard_pile = [top]
            self._rng.shuffle(self.draw_pile)

        return self.draw_pile.pop()

    def draw_to_hand(self, player: PlayerState, amount: int) -> None:
        """Append multiple freshly drawn cards to a player's hand."""
        for _ in range(amount):
            player.hand.append(self.draw_one())

    def clear(self) -> None:
        """Empty both piles without rebuilding the deck (used when resetting to lobby)."""
        self.draw_pile = []
        self.discard_pile = []
