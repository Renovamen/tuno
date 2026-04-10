"""Card primitives and deck construction helpers for the UNO rule engine."""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional

from tuno.core.prng import LcgRandom

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


def build_classic_deck(rng: Optional[LcgRandom] = None) -> List[Card]:
    """Build and shuffle the standard 108-card UNO deck."""
    deck: List[Card] = []

    for color in COLORS:
        deck.append(Card(color=color, rank="0"))
        for rank in [str(value) for value in range(1, 10)] + list(ACTION_RANKS):
            deck.append(Card(color=color, rank=rank))
            deck.append(Card(color=color, rank=rank))

    for _ in range(4):
        deck.append(Card(color=None, rank="wild"))
        deck.append(Card(color=None, rank="wild_draw_four"))

    shuffler = rng or LcgRandom()
    shuffler.shuffle(deck)

    return deck
