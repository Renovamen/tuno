"""Card primitives, game error, and deck management for the UNO rule engine."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, List, Optional

from tuno.core.prng import LcgRandom

if TYPE_CHECKING:
    from tuno.core.game import PlayerState

COLORS = ("red", "yellow", "green", "blue")
ACTION_RANKS = ("skip", "reverse", "draw_two")
WILD_RANKS = ("wild", "wild_draw_four")


@dataclass(frozen=True)
class Card:
    """Immutable value object representing a single UNO card."""

    color: Optional[str]
    rank: str

    def is_wild(self) -> bool:
        """Return whether the card can be played independent of the current color."""
        return self.rank in WILD_RANKS

    def short_label(self) -> str:
        """Build the compact label used by the terminal client hand view."""
        if self.rank == "wild":
            return "WILD"

        if self.rank == "wild_draw_four":
            return "W+4"

        prefix = (self.color or "?")[0].upper()
        rank = self.rank.replace("draw_two", "+2").replace("reverse", "REV").replace("skip", "SKIP")
        return f"{prefix}:{rank}"

    def display_name(self) -> str:
        """Build the human-readable label used in status and history text."""
        if self.rank == "wild":
            return "Wild"

        if self.rank == "wild_draw_four":
            return "Wild Draw Four"

        return f"{(self.color or '').title()} {self.rank.replace('_', ' ').title()}"

    def event_markup(self, display_color: Optional[str] = None) -> str:
        """Return a colored bold Rich markup string for use in event history."""
        label = self.short_label()
        color = display_color or self.color

        if color in COLORS:
            return f"[bold {color}]{label}[/]"

        return f"[bold magenta]{label}[/]"

    def to_dict(self) -> dict:
        """Serialize the card into the payload shape shared with clients."""
        return {
            "color": self.color,
            "rank": self.rank,
            "label": self.display_name(),
            "short": self.short_label(),
        }

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

        for color in COLORS:
            deck.append(Card(color=color, rank="0"))
            for rank in [str(value) for value in range(1, 10)] + list(ACTION_RANKS):
                deck.append(Card(color=color, rank=rank))
                deck.append(Card(color=color, rank=rank))

        for _ in range(4):
            deck.append(Card(color=None, rank="wild"))
            deck.append(Card(color=None, rank="wild_draw_four"))

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
                return card.color

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
