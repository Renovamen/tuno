from __future__ import annotations

import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from typer.testing import CliRunner

from tuno import __version__
from tuno.client.cli.app import app
from tuno.client.cli.uninstall import cli_uninstall
from tuno.client.cli.update import cli_self_update

runner = CliRunner()


class ClientCliEntrypointTests(unittest.TestCase):
    """Cover CLI dispatch without starting the Textual app or installer."""

    @patch("tuno.client.cli.app.run_client")
    def test_main_launches_client_without_server(self, run_client) -> None:
        result = runner.invoke(app, [])

        self.assertEqual(result.exit_code, 0)
        run_client.assert_called_once_with(server_url="")

    @patch("tuno.client.cli.app.run_client")
    def test_main_launches_client_with_optional_server(self, run_client) -> None:
        result = runner.invoke(app, ["--server", "wss://example.test"])

        self.assertEqual(result.exit_code, 0)
        run_client.assert_called_once_with(server_url="wss://example.test")

    @patch("tuno.client.cli.app.run_client")
    def test_main_supports_short_server_flag(self, run_client) -> None:
        result = runner.invoke(app, ["-s", "ws://example.test"])

        self.assertEqual(result.exit_code, 0)
        run_client.assert_called_once_with(server_url="ws://example.test")

    @patch("tuno.client.cli.app.cli_self_update")
    @patch("tuno.client.cli.app.run_client")
    def test_main_dispatches_update_command(self, run_client, mock_self_update) -> None:
        result = runner.invoke(app, ["update"])

        self.assertEqual(result.exit_code, 0)
        mock_self_update.assert_called_once_with(__version__)
        run_client.assert_not_called()

    @patch("tuno.client.cli.app.cli_uninstall")
    @patch("tuno.client.cli.app.run_client")
    def test_main_dispatches_uninstall_command(self, run_client, mock_uninstall) -> None:
        result = runner.invoke(app, ["uninstall"])

        self.assertEqual(result.exit_code, 0)
        mock_uninstall.assert_called_once_with()
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

    @patch("tuno.client.cli.update.urlopen")
    @patch("tuno.client.cli.update.build_client_ssl_context")
    def test_fetch_install_script_uses_client_ssl_context(
        self, build_ssl_context: Mock, urlopen: Mock
    ) -> None:
        from tuno.client.cli.update import fetch_install_script

        ssl_context = object()
        build_ssl_context.return_value = ssl_context
        urlopen.return_value.__enter__.return_value.read.return_value = b"echo install"

        script = fetch_install_script(timeout=3.0)

        self.assertEqual(script, "echo install")
        urlopen.assert_called_once()
        self.assertEqual(urlopen.call_args.kwargs["timeout"], 3.0)
        self.assertIs(urlopen.call_args.kwargs["context"], ssl_context)


class ClientUninstallCommandTests(unittest.TestCase):
    """Cover file removal behavior for the `tuno uninstall` command."""

    def test_cli_uninstall_removes_install_files_and_keeps_config_when_declined(self) -> None:
        with runner.isolated_filesystem():
            home = Path.cwd()
            install_dir = home / ".local" / "share" / "tuno"
            bin_file = home / ".local" / "bin" / "tuno"
            config_dir = home / ".config" / "tuno"
            install_dir.mkdir(parents=True)
            bin_file.parent.mkdir(parents=True)
            bin_file.write_text("#!/bin/sh\n", encoding="utf-8")
            config_dir.mkdir(parents=True)

            removed = cli_uninstall(home=home, confirm=lambda _prompt: False, echo=Mock())

            self.assertTrue(removed)
            self.assertFalse(install_dir.exists())
            self.assertFalse(bin_file.exists())
            self.assertTrue(config_dir.exists())

    def test_cli_uninstall_removes_config_when_confirmed(self) -> None:
        with runner.isolated_filesystem():
            home = Path.cwd()
            config_dir = home / ".config" / "tuno"
            config_dir.mkdir(parents=True)

            removed = cli_uninstall(home=home, confirm=lambda _prompt: True, echo=Mock())

            self.assertTrue(removed)
            self.assertFalse(config_dir.exists())
