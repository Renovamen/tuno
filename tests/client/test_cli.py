from __future__ import annotations

import unittest
from unittest.mock import Mock, patch

from tuno.client import __main__ as client_main
from tuno.client.cli.update import cli_self_update


class ClientCliEntrypointTests(unittest.TestCase):
    """Cover CLI dispatch without starting the Textual app or installer."""

    @patch("tuno.client.__main__.run_client")
    def test_main_launches_client_with_optional_server(self, run_client) -> None:
        client_main.main(["--server", "wss://example.test"])

        run_client.assert_called_once_with(server_url="wss://example.test")

    @patch("tuno.client.__main__.run_client")
    def test_main_supports_short_server_flag(self, run_client) -> None:
        client_main.main(["-s", "ws://example.test"])

        run_client.assert_called_once_with(server_url="ws://example.test")

    @patch("tuno.client.__main__.cli_self_update")
    @patch("tuno.client.__main__.run_client")
    def test_main_dispatches_update_command(self, run_client, cli_self_update) -> None:
        client_main.main(["update"])

        cli_self_update.assert_called_once_with(client_main.__version__)
        run_client.assert_not_called()


class ClientSelfUpdateCommandTests(unittest.TestCase):
    """Cover installer behavior for the `tuno update` command."""

    def test_cli_self_update_runs_installer_when_newer_version_exists(self) -> None:
        fetch_install_script = Mock(return_value="echo install")
        run_install_script = Mock()
        echo = Mock()

        updated = cli_self_update(
            "1.0.0",
            fetch_latest_version=lambda: "1.1.0",
            fetch_install_script_fn=fetch_install_script,
            run_install_script_fn=run_install_script,
            echo=echo,
        )

        self.assertTrue(updated)
        fetch_install_script.assert_called_once_with()
        run_install_script.assert_called_once_with("echo install")

    def test_cli_self_update_skips_install_when_already_current(self) -> None:
        fetch_install_script = Mock()
        run_install_script = Mock()
        echo = Mock()

        updated = cli_self_update(
            "1.1.0",
            fetch_latest_version=lambda: "1.1.0",
            fetch_install_script_fn=fetch_install_script,
            run_install_script_fn=run_install_script,
            echo=echo,
        )

        self.assertFalse(updated)
        fetch_install_script.assert_not_called()
        run_install_script.assert_not_called()
