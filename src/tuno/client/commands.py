from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List


class CommandError(ValueError):
    """Raised when a user enters an invalid command."""


@dataclass(frozen=True)
class ParsedCommand:
    name: str
    args: List[str]


CANONICAL_COMMANDS = {
    "connect",
    "start",
    "play",
    "draw",
    "pass",
    "uno",
    "help",
    "exit",
}
VALID_PLAY_COLORS = {
    "red",
    "yellow",
    "green",
    "blue",
}


def parse_command(raw: str) -> ParsedCommand:
    text = raw.strip()
    if not text:
        raise CommandError("Command is empty.")
    if not text.startswith("/"):
        raise CommandError("Commands must start with '/'.")

    parts = text[1:].split()
    if not parts:
        raise CommandError("Command is empty.")

    name = parts[0].lower()
    args = parts[1:]

    if name not in CANONICAL_COMMANDS:
        raise CommandError(f"Unknown command: /{name}")
    if name == "play":
        if len(args) not in {1, 2}:
            raise CommandError("Usage: /play <n> [color]")
        if not args[0].isdigit():
            raise CommandError("/play requires a numeric card index.")
        if len(args) == 2 and args[1].lower() not in VALID_PLAY_COLORS:
            raise CommandError("/play color must be one of: red, yellow, green, blue.")
    elif name in {"start", "draw", "pass", "uno", "help", "exit"} and args:
        raise CommandError(f"/{name} does not take arguments.")
    elif name == "connect" and len(args) > 1:
        raise CommandError("Usage: /connect [name]")

    return ParsedCommand(name=name, args=args)


def derive_available_commands(
    state: Dict[str, object], *, connected: bool, joined: bool, uno_armed: bool
) -> List[str]:
    if not connected or not joined:
        return ["/connect <name>", "/help", "/exit"]

    if state.get("finished"):
        commands = ["/help", "/exit"]
        if state.get("can_start"):
            commands.insert(0, "/start")
        return commands
    if not state.get("started"):
        commands = ["/help", "/exit"]
        if state.get("can_start"):
            commands.insert(0, "/start")
        return commands
    if not state.get("your_turn"):
        return ["/help", "/exit"]

    commands: List[str] = ["/play <n> [color]"]

    if state.get("can_draw"):
        commands.append("/draw")
    if state.get("can_pass"):
        commands.append("/pass")
    if state.get("uno_hint") or uno_armed:
        commands.append("/uno")

    commands.append("/help")
    commands.append("/exit")

    return commands
