from __future__ import annotations

import unittest

from tuno.client.commands import CommandError, derive_available_commands, parse_command


class ClientCommandParsingTests(unittest.TestCase):
    """Cover command parsing rules for the command-first client."""

    def test_accepts_canonical_commands(self) -> None:
        """Parse every canonical command shape accepted by the client."""
        self.assertEqual(parse_command("/connect alice").name, "connect")
        self.assertEqual(parse_command("/start").name, "start")
        self.assertEqual(parse_command("/play 3").args, ["3"])
        self.assertEqual(parse_command("/play 3 red").args, ["3", "red"])
        self.assertEqual(parse_command("/draw").name, "draw")
        self.assertEqual(parse_command("/pass").name, "pass")
        self.assertEqual(parse_command("/uno").name, "uno")
        self.assertEqual(parse_command("/help").name, "help")
        self.assertEqual(parse_command("/exit").name, "exit")

    def test_rejects_malformed_commands(self) -> None:
        """Reject malformed command strings before any network call is made."""
        bad_inputs = ["", "play 3", "/unknown", "/play", "/play x", "/play 2 purple", "/start now"]
        for raw in bad_inputs:
            with self.assertRaises(CommandError, msg=raw):
                parse_command(raw)


class AvailableCommandsTests(unittest.TestCase):
    """Cover state-derived available-command policies."""

    def test_disconnected_help(self) -> None:
        """Offer connect and help before a player joins a server."""
        cmds = derive_available_commands({}, connected=False, joined=False, uno_armed=False)
        self.assertEqual(cmds, ["/connect <name>", "/help", "/exit"])

    def test_lobby_host_help(self) -> None:
        """Expose `/start` only when the joined player can start the lobby."""
        cmds = derive_available_commands(
            {"started": False, "can_start": True}, connected=True, joined=True, uno_armed=False
        )
        self.assertEqual(cmds, ["/start", "/help", "/exit"])

    def test_lobby_non_host_help(self) -> None:
        """Hide `/start` from lobby players who are not allowed to start."""
        cmds = derive_available_commands(
            {"started": False, "can_start": False}, connected=True, joined=True, uno_armed=False
        )
        self.assertEqual(cmds, ["/help", "/exit"])

    def test_game_your_turn_help(self) -> None:
        """Show only the legal turn actions for the current player."""
        cmds = derive_available_commands(
            {
                "started": True,
                "your_turn": True,
                "can_draw": True,
                "can_pass": False,
                "uno_hint": True,
            },
            connected=True,
            joined=True,
            uno_armed=False,
        )
        self.assertEqual(cmds, ["/play <n> [color]", "/draw", "/uno", "/help", "/exit"])

    def test_game_waiting_help(self) -> None:
        """Collapse the command list to help while waiting for another player."""
        cmds = derive_available_commands(
            {"started": True, "your_turn": False}, connected=True, joined=True, uno_armed=False
        )
        self.assertEqual(cmds, ["/help", "/exit"])

    def test_finished_help(self) -> None:
        """Expose `/start` again to the host after a finished round."""
        cmds = derive_available_commands(
            {"finished": True, "can_start": True}, connected=True, joined=True, uno_armed=False
        )
        self.assertEqual(cmds, ["/start", "/help", "/exit"])

    def test_finished_non_host_hides_restart(self) -> None:
        """Do not expose `/start` to non-host players after a finished round."""
        cmds = derive_available_commands(
            {"finished": True, "can_start": False}, connected=True, joined=True, uno_armed=False
        )
        self.assertEqual(cmds, ["/help", "/exit"])
