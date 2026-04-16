from __future__ import annotations

import unittest
from unittest.mock import Mock

from tuno.client.updates import (
    build_update_notice,
    is_newer_version,
    normalize_version,
    perform_self_update,
)


class ClientUpdateTests(unittest.TestCase):
    """Cover pure version-check helpers for the client update notice."""

    def test_normalize_version_strips_leading_v(self) -> None:
        # Normalize GitHub-style tags like `v1.2.3` into plain semantic versions.
        self.assertEqual(normalize_version("v1.2.3"), "1.2.3")

    def test_is_newer_version_compares_semantic_parts(self) -> None:
        # Treat dotted numeric parts as ordered version components during comparison.
        self.assertTrue(is_newer_version("v1.2.0", "1.1.9"))
        self.assertFalse(is_newer_version("v1.2.0", "1.2.0"))

    def test_build_update_notice_points_to_install_section(self) -> None:
        # Build the bottom-bar notice text with the inline self-update instruction.
        notice = build_update_notice("v9.9.9")
        self.assertIn("v9.9.9", notice)
        self.assertIn("tuno update", notice)

    def test_perform_self_update_runs_installer_when_newer_version_exists(self) -> None:
        # When a newer release exists, fetch the install script and execute it once.
        fetch_install_script = Mock(return_value="echo install")
        run_install_script = Mock()
        echo = Mock()

        updated = perform_self_update(
            "1.0.0",
            fetch_latest_version=lambda: "1.1.0",
            fetch_install_script_fn=fetch_install_script,
            run_install_script_fn=run_install_script,
            echo=echo,
        )

        self.assertTrue(updated)
        fetch_install_script.assert_called_once_with()
        run_install_script.assert_called_once_with("echo install")

    def test_perform_self_update_skips_install_when_already_current(self) -> None:
        # Skip any installer work when the local client is already at the latest version.
        fetch_install_script = Mock()
        run_install_script = Mock()
        echo = Mock()

        updated = perform_self_update(
            "1.1.0",
            fetch_latest_version=lambda: "1.1.0",
            fetch_install_script_fn=fetch_install_script,
            run_install_script_fn=run_install_script,
            echo=echo,
        )

        self.assertFalse(updated)
        fetch_install_script.assert_not_called()
        run_install_script.assert_not_called()
