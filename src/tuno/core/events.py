"""User-facing event and status text helpers for the game engine."""

from __future__ import annotations


def escape(text: str) -> str:
    """Escape user text for Rich markup without importing Rich at module load time."""
    return text.replace("\\", "\\\\").replace("[", "\\[").replace("]", "\\]")


def lobby_waiting() -> str:
    """Return the default lobby status before players join."""
    return "Waiting for players."


def lobby_joined(name: str) -> str:
    """Return the event text for a player joining the lobby."""
    return f"{escape(name)} joined the lobby."


def lobby_left(name: str) -> str:
    """Return the event text for a player leaving the lobby."""
    return f"{escape(name)} left the lobby."


def game_started() -> str:
    """Return the canonical event marking the start of a round."""
    return "Game started."


def played_card(name: str, card_markup: str) -> str:
    """Return the event text for a successful card play."""
    return f"{escape(name)} played {card_markup}."


def forgot_uno(name: str) -> str:
    """Return the suffix appended when a player forgets to call UNO."""
    return f" {escape(name)} forgot UNO and drew 2."


def uno_armed(name: str) -> str:
    """Return the event text when a player arms UNO for the next play."""
    return f"{escape(name)} armed UNO."


def uno_disarmed(name: str) -> str:
    """Return the event text when a player cancels a previously armed UNO."""
    return f"{escape(name)} canceled UNO."


def round_won(name: str) -> str:
    """Return the event text for a round winner."""
    return f"{escape(name)} wins the round!"


def drew_card(name: str) -> str:
    """Return the event text for drawing a single card."""
    return f"{escape(name)} drew a card."


def passed(name: str) -> str:
    """Return the event text for passing after a draw."""
    return f"{escape(name)} passed."


def effect_drew_cards(name: str, amount: int) -> str:
    """Return the suffix appended when a card effect forces extra draws."""
    return f" {escape(name)} drew {amount}."


def disconnect_wins_by_default(disconnected_name: str, winner_name: str) -> str:
    """Return the event text when a disconnect leaves one player as default winner."""
    return f"{escape(disconnected_name)} disconnected. {escape(winner_name)} wins by default!"


def disconnect_game_ended(name: str) -> str:
    """Return the event text when a disconnect ends the game with no players left."""
    return f"{escape(name)} disconnected. Game ended."


def disconnect_turn_passed(disconnected_name: str, current_name: str) -> str:
    """Return the event text when a disconnect leaves the round in progress."""
    return f"{escape(disconnected_name)} disconnected. {escape(current_name)}'s turn."
