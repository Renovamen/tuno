"""Authoritative single-round UNO game state and rule transitions."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import List, Optional

from tuno.core.cards import Card, Color, Deck
from tuno.core.events import (
    disconnect_game_ended,
    disconnect_turn_passed,
    disconnect_wins_by_default,
    drew_card,
    effect_drew_cards,
    forgot_uno,
    game_started,
    initial_card,
    lobby_joined,
    lobby_left,
    lobby_waiting,
    passed,
    played_card,
    round_won,
    uno_armed,
    uno_disarmed,
)
from tuno.core.game_storage import public_player_payload
from tuno.core.prng import LcgRandom
from tuno.core.snapshot import GameSnapshot, build_snapshot

MAX_PLAYERS = 5
MIN_PLAYERS = 2


class GameError(Exception):
    """Domain error for game/session actions."""

    def __init__(self, message: str, code: Optional[str] = None) -> None:
        super().__init__(message)
        self.code = code


@dataclass
class PlayerState:
    """Mutable per-player state stored inside the authoritative game."""

    player_id: str
    name: str
    hand: List[Card] = field(default_factory=list)

    def to_public_dict(self, is_self: bool) -> dict:
        """Serialize a player, exposing cards only to the owning player."""
        return public_player_payload(self, is_self)


@dataclass
class GameState:
    """Own the full authoritative state for one local UNO round."""

    seed: int = field(default_factory=lambda: int(time.time_ns() & 0x7FFFFFFF))
    players: List[PlayerState] = field(default_factory=list)
    started: bool = False
    finished: bool = False
    winner_id: Optional[str] = None
    current_player_index: int = 0
    direction: int = 1
    current_color: Optional[str] = None
    status_message: str = lobby_waiting()
    recent_events: List[str] = field(default_factory=lambda: [lobby_waiting()])
    has_drawn_this_turn: bool = False
    drawn_card: Optional[Card] = None
    _next_player_serial: int = 1

    def __post_init__(self) -> None:
        """Initialize the deck with a seeded PRNG after dataclass construction."""
        self._deck = Deck(LcgRandom(self.seed))

    @property
    def top_card(self) -> Optional[Card]:
        """Expose the visible discard top for rule checks and snapshots."""
        return self._deck.top_card

    @property
    def current_player(self) -> Optional[PlayerState]:
        """Return the active player, if the lobby has any players."""
        if not self.players:
            return None
        return self.players[self.current_player_index]

    def add_player(self, name: str) -> str:
        """Add a player to the lobby and return the stable player identifier."""
        if self.started and not self.finished:
            raise GameError("Game already started.")

        if len(self.players) >= MAX_PLAYERS:
            raise GameError("Game is full.")

        clean_name = name.strip() or f"Player {len(self.players) + 1}"
        if len(clean_name) > 24:
            raise GameError("Player name must be 24 characters or fewer.")
        if any(player.name.lower() == clean_name.lower() for player in self.players):
            raise GameError("Player name already exists.")

        player_id = "p%04d" % self._next_player_serial

        self._next_player_serial += 1
        self.players.append(PlayerState(player_id=player_id, name=clean_name))
        self.status_message = lobby_joined(clean_name)
        self._record_event(self.status_message)

        return player_id

    def remove_player(self, player_id: str) -> None:
        """Remove a player, continuing or ending the round based on players remaining."""
        index = self._player_index(player_id)
        player = self.players[index]
        del self.players[index]

        if not self.players:
            self._reset_to_lobby()
            return
        if not self.started or self.finished:
            self._record_lobby_departure(player)
            return

        if len(self.players) <= 1:
            self._finish_after_disconnect(player)
            return

        self._continue_after_disconnect(index, player)

    def start(self, player_id: str) -> None:
        """Start a new round, deal hands, and reveal the first playable discard."""
        if self.started and not self.finished:
            raise GameError("Game already started.")

        if len(self.players) < MIN_PLAYERS:
            raise GameError("Need at least 2 players to start.")

        if not self.players or self.players[0].player_id != player_id:
            raise GameError("Only the host can start the game.")

        self.winner_id = None
        self._deck.reset()
        self._deck.deal(self.players)
        self.current_color = self._deck.setup_opening_discard()

        self.started = True
        self.finished = False
        self.current_player_index = 0
        self.direction = 1
        self.has_drawn_this_turn = False
        self.drawn_card = None
        self.status_message = game_started()
        self.recent_events = [
            self.status_message,
            initial_card(self.top_card.event_markup()),
        ]

    def play_card(
        self,
        player_id: str,
        hand_index: int,
        chosen_color: Optional[str] = None,
        say_uno: bool = False,
    ) -> None:
        """Play a card for the active player, enforcing turn and card legality."""
        self._ensure_active_player(player_id)
        player = self.current_player
        assert player is not None

        card = self._card_for_play(player, hand_index)
        chosen_color = self._resolve_play_color(card, chosen_color)
        self._validate_card_type_restrictions(player, hand_index, card)
        played = self._commit_play(player, hand_index, chosen_color, say_uno)

        if not player.hand:
            self.finished = True
            self.winner_id = player.player_id
            self.status_message = round_won(player.name)
            self._record_event(self.status_message)
            return

        skip_steps = self._apply_card_effect(played)
        self._advance_turn(skip_steps)
        self._record_event(self.status_message)

    def _record_lobby_departure(self, player: PlayerState) -> None:
        self.status_message = lobby_left(player.name)
        self._record_event(self.status_message)

        if self.current_player_index >= len(self.players):
            self.current_player_index = 0

    def _finish_after_disconnect(self, player: PlayerState) -> None:
        self.finished = True
        self.has_drawn_this_turn = False
        self.drawn_card = None
        self.current_player_index = 0

        if self.players:
            winner = self.players[0]
            self.winner_id = winner.player_id
            self.status_message = disconnect_wins_by_default(player.name, winner.name)
        else:
            self.winner_id = None
            self.status_message = disconnect_game_ended(player.name)

        self._record_event(self.status_message)

    def _continue_after_disconnect(self, removed_index: int, player: PlayerState) -> None:
        self.winner_id = None
        self._move_turn_after_disconnect(removed_index)
        self.status_message = disconnect_turn_passed(player.name, self.current_player.name)
        self._record_event(self.status_message)

    def _move_turn_after_disconnect(self, removed_index: int) -> None:
        if removed_index < self.current_player_index:
            self.current_player_index -= 1
        elif removed_index == self.current_player_index:
            if self.direction < 0:
                self.current_player_index = (self.current_player_index - 1) % len(self.players)
            else:
                self.current_player_index %= len(self.players)
            self.has_drawn_this_turn = False
            self.drawn_card = None
        else:
            self.current_player_index %= len(self.players)

    def _card_for_play(self, player: PlayerState, hand_index: int) -> Card:
        if hand_index < 0 or hand_index >= len(player.hand):
            raise GameError("Invalid card selection.", code="invalid_selection")

        card = player.hand[hand_index]
        if self._violates_drawn_card_rule(player, hand_index, card):
            raise GameError("After drawing, you may only play the card you just drew.")
        if not self._is_play_legal(player, card):
            raise GameError("That card can't be played right now.", code="illegal_play")
        return card

    def _violates_drawn_card_rule(self, player: PlayerState, hand_index: int, card: Card) -> bool:
        return bool(
            self.has_drawn_this_turn
            and self.drawn_card is not None
            and (hand_index != len(player.hand) - 1 or card != self.drawn_card)
        )

    def _resolve_play_color(self, card: Card, chosen_color: Optional[str]) -> Optional[str]:
        if not card.type.is_wild:
            return card.color.value if card.color else None
        color = Color.parse(chosen_color)
        if color is not None:
            return color.value
        raise GameError("Wild cards require a chosen color.", code="wild_needs_color")

    def _validate_card_type_restrictions(
        self, player: PlayerState, hand_index: int, card: Card
    ) -> None:
        if not card.type.requires_no_current_color_match:
            return
        if any(
            other.color == self.current_color
            for i, other in enumerate(player.hand)
            if i != hand_index
        ):
            raise GameError(
                "Wild Draw Four can only be played when you have no card matching the current color.",
                code="wild_draw_four_restricted",
            )

    def _commit_play(
        self,
        player: PlayerState,
        hand_index: int,
        chosen_color: Optional[str],
        say_uno: bool,
    ) -> Card:
        played = player.hand.pop(hand_index)
        self._deck.discard_pile.append(played)
        self.current_color = chosen_color
        self.status_message = played_card(
            player.name, played.event_markup(display_color=chosen_color)
        )

        if len(player.hand) == 1 and not say_uno:
            self._deck.draw_to_hand(player, 2)
            self.status_message += forgot_uno(player.name)
        return played

    def draw_card(self, player_id: str) -> None:
        """Draw one card for the active player and auto-pass if it cannot be played."""
        self._ensure_active_player(player_id)

        if self.has_drawn_this_turn:
            raise GameError("You already drew this turn.")

        player = self.current_player
        assert player is not None

        card = self._deck.draw_one()
        player.hand.append(card)
        self.status_message = drew_card(player.name)

        # Match the current product rule: an unplayable draw ends the turn immediately.
        if not self._is_play_legal(player, card):
            self.drawn_card = None
            self._advance_turn(0)
        else:
            self.has_drawn_this_turn = True
            self.drawn_card = card

        self._record_event(self.status_message)

    def pass_turn(self, player_id: str) -> None:
        """Pass after drawing when the drawn card is playable but declined."""
        self._ensure_active_player(player_id)

        if not self.has_drawn_this_turn:
            raise GameError("You can only pass after drawing.")

        player = self.current_player
        assert player is not None

        self.status_message = passed(player.name)
        self._advance_turn(0)
        self._record_event(self.status_message)

    def set_uno_intent(self, player_id: str, armed: bool) -> None:
        """Record that the active player armed UNO for the next play."""
        self._ensure_active_player(player_id)

        player = self.current_player
        assert player is not None

        self.status_message = uno_armed(player.name) if armed else uno_disarmed(player.name)
        self._record_event(self.status_message)

    def _apply_card_effect(self, card: Card) -> int:
        """Apply the played card's side effect and return extra turns to skip."""
        effect = card.type.effect
        if effect.reverses_direction:
            self.direction *= -1

        if effect.draw_count:
            target = self._peek_next_player(steps=1)
            self._deck.draw_to_hand(target, effect.draw_count)
            self.status_message += effect_drew_cards(target.name, effect.draw_count)

        return 1 if effect.skips_next else 0

    def _advance_turn(self, extra_skip: int) -> None:
        """Advance turn order, resetting per-turn draw state on the way out."""
        if self.finished:
            return
        self.has_drawn_this_turn = False
        self.drawn_card = None
        steps = 1 + extra_skip
        self.current_player_index = (self.current_player_index + self.direction * steps) % len(
            self.players
        )

    def _peek_next_player(self, steps: int) -> PlayerState:
        """Look ahead in turn order without mutating the active player pointer."""
        index = (self.current_player_index + self.direction * steps) % len(self.players)
        return self.players[index]

    def _ensure_active_player(self, player_id: str) -> None:
        """Reject actions that do not come from the current legal actor."""
        if not self.started:
            raise GameError("Game hasn't started yet.")
        if self.finished:
            raise GameError("Game is over.")

        player = self.current_player
        if player is None or player.player_id != player_id:
            raise GameError("It's not your turn.")

    def _player_index(self, player_id: str) -> int:
        """Return the list index for a known player identifier."""
        for index, player in enumerate(self.players):
            if player.player_id == player_id:
                return index
        raise GameError("Unknown player.")

    def _is_play_legal(self, player: PlayerState, card: Card) -> bool:
        """Check whether a card matches current color/rank or is wild."""
        top = self.top_card

        if top is None:
            return True
        if card.is_wild():
            return True

        return card.color == self.current_color or card.rank == top.rank

    def _record_event(self, message: str) -> None:
        """Append a recent event capped to the latest few entries."""
        self.recent_events.append(message)
        self.recent_events = self.recent_events[-8:]

    def _reset_to_lobby(self) -> None:
        """Reset round state once the last connected player has left."""
        self.started = False
        self.finished = False
        self.winner_id = None
        self.current_player_index = 0
        self.direction = 1
        self._deck.clear()
        self.current_color = None
        self.has_drawn_this_turn = False
        self.drawn_card = None
        self.status_message = lobby_waiting()
        self.recent_events = [lobby_waiting()]

    def snapshot_for(self, player_id: Optional[str]) -> GameSnapshot:
        """Build the client-facing state payload for one connected player."""
        return build_snapshot(self, player_id)
