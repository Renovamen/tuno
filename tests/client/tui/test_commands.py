from __future__ import annotations

import unittest

from tuno.client.tui.commands import CommandError, derive_available_commands, parse_command
from tuno.core.snapshot import GameSnapshot


class ClientCommandParsingTests(unittest.TestCase):
    """Cover command parsing rules for the command-first client."""

    def test_accepts_canonical_commands(self) -> None:
        """Parse every canonical command shape accepted by the client."""
        self.assertEqual(parse_command("/server").name, "server")
        self.assertEqual(parse_command("/server ws://127.0.0.1:8765").args, ["ws://127.0.0.1:8765"])
        self.assertEqual(parse_command("/connect main").args, ["main"])
        self.assertEqual(parse_command("/create main").args, ["main"])
        self.assertEqual(parse_command("/join alice").name, "join")
        self.assertEqual(parse_command("/start").name, "start")
        self.assertEqual(parse_command("/play 3").args, ["3"])
        self.assertEqual(parse_command("/play 3 red").args, ["3", "red"])
        self.assertEqual(parse_command("/draw").name, "draw")
        self.assertEqual(parse_command("/pass").name, "pass")
        self.assertEqual(parse_command("/uno").name, "uno")
        self.assertEqual(parse_command("/exit_game").name, "exit_game")
        self.assertEqual(parse_command("/exit_room").name, "exit_room")
        self.assertEqual(parse_command("/help").name, "help")
        self.assertEqual(parse_command("/exit_server").name, "exit_server")
        self.assertEqual(parse_command("/exit").name, "exit")

    def test_rejects_malformed_commands(self) -> None:
        """Reject malformed command strings before any network call is made."""
        bad_inputs = [
            "",
            "play 3",
            "/unknown",
            "/play",
            "/play x",
            "/play 2 purple",
            "/start now",
            "/server ws://one ws://two",
            "/join",
            "/connect",
            "/create",
        ]
        for raw in bad_inputs:
            with self.assertRaises(CommandError, msg=raw):
                parse_command(raw)


class AvailableCommandsTests(unittest.TestCase):
    """Cover state-derived available-command policies."""

    def test_disconnected_help(self) -> None:
        """Offer connect and help before a player joins a server."""
        cmds = derive_available_commands(
            GameSnapshot(),
            connected=False,
            room_selected=False,
            joined=False,
            uno_armed=False,
        )
        self.assertEqual(cmds, ["/server <server>", "/help", "/exit"])

    def test_room_selection_help(self) -> None:
        """Offer room commands after server connect and before room selection."""
        cmds = derive_available_commands(
            GameSnapshot(),
            connected=True,
            room_selected=False,
            joined=False,
            uno_armed=False,
        )
        self.assertEqual(
            cmds, ["/connect <room>", "/create <room>", "/help", "/exit_server", "/exit"]
        )

    def test_selected_room_before_join_help(self) -> None:
        """Offer player join and room exit commands after a room is selected."""
        cmds = derive_available_commands(
            GameSnapshot(),
            connected=True,
            room_selected=True,
            joined=False,
            uno_armed=False,
        )
        self.assertEqual(
            cmds, ["/join <player_name>", "/help", "/exit_room", "/exit_server", "/exit"]
        )

    def test_lobby_host_help(self) -> None:
        """Expose `/start` only when the joined player can start the lobby."""
        cmds = derive_available_commands(
            GameSnapshot(started=False, can_start=True),
            connected=True,
            room_selected=True,
            joined=True,
            uno_armed=False,
        )
        self.assertEqual(
            cmds, ["/start", "/help", "/exit_game", "/exit_room", "/exit_server", "/exit"]
        )

    def test_lobby_non_host_help(self) -> None:
        """Hide `/start` from lobby players who are not allowed to start."""
        cmds = derive_available_commands(
            GameSnapshot(started=False, can_start=False),
            connected=True,
            room_selected=True,
            joined=True,
            uno_armed=False,
        )
        self.assertEqual(cmds, ["/help", "/exit_game", "/exit_room", "/exit_server", "/exit"])

    def test_game_your_turn_help(self) -> None:
        """Show only the legal turn actions for the current player."""
        cmds = derive_available_commands(
            GameSnapshot(
                started=True,
                your_turn=True,
                can_draw=True,
                can_pass=False,
                uno_hint=True,
            ),
            connected=True,
            room_selected=True,
            joined=True,
            uno_armed=False,
        )
        self.assertEqual(
            cmds,
            [
                "/play <n> [color]",
                "/draw",
                "/uno",
                "/help",
                "/exit_game",
                "/exit_room",
                "/exit_server",
                "/exit",
            ],
        )

    def test_game_waiting_help(self) -> None:
        """Collapse the command list to help while waiting for another player."""
        cmds = derive_available_commands(
            GameSnapshot(started=True, your_turn=False),
            connected=True,
            room_selected=True,
            joined=True,
            uno_armed=False,
        )
        self.assertEqual(
            cmds,
            ["/help", "/exit_game", "/exit_room", "/exit_server", "/exit"],
        )

    def test_finished_help(self) -> None:
        """Expose `/start` again to the host after a finished round."""
        cmds = derive_available_commands(
            GameSnapshot(finished=True, can_start=True),
            connected=True,
            room_selected=True,
            joined=True,
            uno_armed=False,
        )
        self.assertEqual(
            cmds, ["/start", "/help", "/exit_game", "/exit_room", "/exit_server", "/exit"]
        )

    def test_finished_non_host_hides_restart(self) -> None:
        """Do not expose `/start` to non-host players after a finished round."""
        cmds = derive_available_commands(
            GameSnapshot(finished=True, can_start=False),
            connected=True,
            room_selected=True,
            joined=True,
            uno_armed=False,
        )
        self.assertEqual(cmds, ["/help", "/exit_game", "/exit_room", "/exit_server", "/exit"])
