from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from tuno.client.config import load_server_history, remember_server, save_server_history


class ClientConfigTests(unittest.TestCase):
    """Cover local YAML-backed client config helpers."""

    def test_server_history_round_trips_through_yaml(self) -> None:
        """Write server history to YAML, then load the same ordered values back."""
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "config.yaml"

            # Save multiple server URLs so the test covers YAML list serialization.
            save_server_history(
                ["ws://127.0.0.1:8765", "wss://example.test/game"],
                path,
            )

            # The loader should preserve order and expose the expected top-level key.
            self.assertEqual(
                load_server_history(path),
                ["ws://127.0.0.1:8765", "wss://example.test/game"],
            )
            self.assertIn("server_history:", path.read_text(encoding="utf-8"))

    def test_remember_server_deduplicates_and_keeps_most_recent_first(self) -> None:
        """Move repeated servers to the front instead of storing duplicate history rows."""
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "config.yaml"

            # Re-enter the first server after another one to simulate user recency.
            remember_server("ws://one.test", path)
            remember_server("ws://two.test", path)
            history = remember_server("ws://one.test", path)

            # The repeated URL should become most recent, with one stored copy.
            self.assertEqual(history, ["ws://one.test", "ws://two.test"])
            self.assertEqual(load_server_history(path), history)

    def test_save_server_history_preserves_other_config_keys(self) -> None:
        """Update only server history while preserving future unrelated config fields."""
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "config.yaml"
            path.write_text("theme: dark\nserver_history:\n  - ws://old.test\n", encoding="utf-8")

            # Replace server history in a config file that already has another setting.
            save_server_history(["ws://new.test"], path)

            # Future settings should survive history updates, and history should change.
            text = path.read_text(encoding="utf-8")
            self.assertIn("theme: dark", text)
            self.assertEqual(load_server_history(path), ["ws://new.test"])
