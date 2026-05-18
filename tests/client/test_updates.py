from __future__ import annotations

import unittest
from io import StringIO
from unittest.mock import Mock, patch

from tuno.client.updates import fetch_latest_release_version, is_newer_version, normalize_version


class ClientUpdateTests(unittest.TestCase):
    """Cover pure version-check helpers for the client update notice."""

    def test_normalize_version_strips_leading_v(self) -> None:
        # Normalize GitHub-style tags like `v1.2.3` into plain semantic versions.
        self.assertEqual(normalize_version("v1.2.3"), "1.2.3")

    def test_is_newer_version_compares_semantic_parts(self) -> None:
        # Treat dotted numeric parts as ordered version components during comparison.
        self.assertTrue(is_newer_version("v1.2.0", "1.1.9"))
        self.assertFalse(is_newer_version("v1.2.0", "1.2.0"))

    @patch("tuno.client.updates.urlopen")
    @patch("tuno.client.updates.build_client_ssl_context")
    def test_fetch_latest_release_version_uses_client_ssl_context(
        self, build_ssl_context: Mock, urlopen: Mock
    ) -> None:
        ssl_context = object()
        build_ssl_context.return_value = ssl_context
        urlopen.return_value.__enter__.return_value = StringIO('{"tag_name": "v1.2.3"}')

        latest = fetch_latest_release_version(timeout=2.0)

        self.assertEqual(latest, "1.2.3")
        urlopen.assert_called_once()
        self.assertEqual(urlopen.call_args.kwargs["timeout"], 2.0)
        self.assertIs(urlopen.call_args.kwargs["context"], ssl_context)
