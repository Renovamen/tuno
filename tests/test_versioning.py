from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = REPO_ROOT / "src"
SCRIPT_PATH = REPO_ROOT / "scripts" / "bump_version.py"
PYPROJECT_PATH = REPO_ROOT / "pyproject.toml"
APP_PATH = SRC_DIR / "tuno" / "client" / "app.py"

sys.path.insert(0, str(SRC_DIR))


def load_bump_version_module():
    spec = importlib.util.spec_from_file_location("bump_version", SCRIPT_PATH)
    if spec is None or spec.loader is None:
        raise AssertionError(f"Unable to load {SCRIPT_PATH}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class VersioningTests(unittest.TestCase):
    def test_bump_script_supports_increment_and_explicit_targets(self) -> None:
        # Verify the bump helper handles semantic increments and direct version overrides.
        bump_version = load_bump_version_module()
        self.assertEqual(bump_version.resolve_next_version("0.1.1", "patch"), "0.1.2")
        self.assertEqual(bump_version.resolve_next_version("0.1.1", "minor"), "0.2.0")
        self.assertEqual(bump_version.resolve_next_version("0.1.1", "major"), "1.0.0")
        self.assertEqual(bump_version.resolve_next_version("0.1.1", "0.5.0"), "0.5.0")


if __name__ == "__main__":
    unittest.main()
