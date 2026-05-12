from __future__ import annotations

import unittest

from tuno.client.updates import is_newer_version, normalize_version


class ClientUpdateTests(unittest.TestCase):
    """Cover pure version-check helpers for the client update notice."""

    def test_normalize_version_strips_leading_v(self) -> None:
        # Normalize GitHub-style tags like `v1.2.3` into plain semantic versions.
        self.assertEqual(normalize_version("v1.2.3"), "1.2.3")

    def test_is_newer_version_compares_semantic_parts(self) -> None:
        # Treat dotted numeric parts as ordered version components during comparison.
        self.assertTrue(is_newer_version("v1.2.0", "1.1.9"))
        self.assertFalse(is_newer_version("v1.2.0", "1.2.0"))
