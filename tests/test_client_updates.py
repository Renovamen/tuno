from __future__ import annotations

import unittest

from tuno.client.updates import build_update_notice, is_newer_version, normalize_version


class ClientUpdateTests(unittest.TestCase):
    """Cover pure version-check helpers for the client update notice."""

    def test_normalize_version_strips_leading_v(self) -> None:
        self.assertEqual(normalize_version("v1.2.3"), "1.2.3")

    def test_is_newer_version_compares_semantic_parts(self) -> None:
        self.assertTrue(is_newer_version("v1.2.0", "1.1.9"))
        self.assertFalse(is_newer_version("v1.2.0", "1.2.0"))

    def test_build_update_notice_points_to_install_section(self) -> None:
        notice = build_update_notice("v9.9.9")
        self.assertIn("v9.9.9", notice)
        self.assertIn("#client-installation", notice)
